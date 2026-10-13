import hashlib
import pickle
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import polars as pl

from sports_engine.core.paths import dated_artifact_directory
from sports_engine.evaluation.bookmaker_baseline import bookmaker_baseline_metrics
from sports_engine.evaluation.leakage_audit import audit_temporal_partitions
from sports_engine.evaluation.metrics import probability_metrics
from sports_engine.models.calibration.multiclass import MulticlassProbabilityCalibrator
from sports_engine.models.ml.catboost import CatBoostProbabilityModel
from sports_engine.models.ml.lightgbm import LightGBMProbabilityModel
from sports_engine.models.ml.logistic import LogisticProbabilityModel
from sports_engine.models.registry import ModelRegistry, ModelRun, validate_model_type
from sports_engine.models.serialization import write_artifact_metadata
from sports_engine.models.statistical.dixon_coles import DixonColesModel
from sports_engine.models.statistical.elo import EloModel
from sports_engine.models.statistical.poisson import PoissonModel
from sports_engine.training.dataset_builder import load_training_dataset, prediction_times
from sports_engine.training.evidence import (
    EvidenceState,
    assess_model_evidence,
    load_evidence_policies,
    persist_evidence_assessment,
)
from sports_engine.training.temporal_split import split_by_time
from sports_engine.training.tuning import constrained_probability_search

TARGET_LABELS = {"HOME": 0, "DRAW": 1, "AWAY": 2}
NON_FEATURE_COLUMNS = {
    "fixture_id",
    "prediction_timestamp",
    "home_team_id",
    "away_team_id",
    "source_observation_max",
    "target_home_goals",
    "target_away_goals",
    "target_result",
}


@dataclass(frozen=True, slots=True)
class TrainingResult:
    version: str
    model_type: str
    artifact_path: Path
    metrics: dict[str, Any]
    dataset_id: str
    evidence_state: str = EvidenceState.RESEARCH_TRAINABLE


class ModelTrainer:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        artifacts_dir: Path,
        *,
        random_seed: int,
        cpu_threads: int,
        time_decay_half_life_days: float = 365.0,
    ) -> None:
        self.connection = connection
        self.artifacts_dir = artifacts_dir
        self.random_seed = random_seed
        self.cpu_threads = cpu_threads
        self.time_decay_half_life_days = time_decay_half_life_days

    def train(
        self,
        model_type: str,
        *,
        dataset_name: str | None = None,
        calibration_method: str | None = None,
        training_mode: str = "full_refit",
        parent_model_version: str | None = None,
    ) -> TrainingResult:
        validate_model_type(model_type)
        if calibration_method not in {None, "platt", "isotonic"}:
            raise ValueError("Calibration method must be one of: platt, isotonic")
        dataset = load_training_dataset(self.connection, dataset_name)
        if training_mode not in {"full_refit", "warm_start"}:
            raise ValueError("training_mode must be full_refit or warm_start")
        if training_mode == "warm_start" and parent_model_version is None:
            raise ValueError("Warm-start candidates require a parent model version")
        policy = load_evidence_policies()[model_type]
        evidence_features = (
            []
            if model_type in {"elo", "poisson", "dixon-coles"}
            else self._feature_columns(dataset.frame, maximum_missing_fraction=policy.maximum_missing_fraction)
        )
        initial_evidence = assess_model_evidence(
            model_type,
            dataset.frame,
            policy,
            feature_columns=evidence_features,
        )
        persist_evidence_assessment(
            self.connection,
            initial_evidence,
            dataset_id=dataset.dataset_id,
        )
        if initial_evidence.state == EvidenceState.INSUFFICIENT_DATA:
            raise ValueError(f"{model_type} is not research-trainable: {', '.join(initial_evidence.reasons)}")
        times = prediction_times(dataset)
        fold = split_by_time(times)
        audit_temporal_partitions(
            [times[index] for index in fold.train],
            [times[index] for index in fold.validation],
            [times[index] for index in fold.test],
        )
        parent_model = None
        parent_cutoff = None
        if parent_model_version:
            parent_model, parent_cutoff = self._load_parent(model_type, parent_model_version)
        model, validation_probabilities, probabilities, hyperparameters, feature_columns = self._fit(
            model_type,
            dataset.frame,
            fold,
            parent_model=parent_model,
            parent_cutoff=parent_cutoff,
        )
        validation_targets = self._targets(dataset.frame)[fold.validation]
        targets = self._targets(dataset.frame)[fold.test]
        training_targets = self._targets(dataset.frame)[fold.train]
        uncalibrated_metrics = probability_metrics(targets, probabilities)
        calibrator = None
        if calibration_method:
            calibrator = MulticlassProbabilityCalibrator(calibration_method, random_seed=self.random_seed).fit(
                validation_probabilities, validation_targets
            )
            probabilities = calibrator.transform(probabilities)
        test_metrics: dict[str, Any] = probability_metrics(targets, probabilities)
        test_metrics.update(
            {
                "uncalibrated": uncalibrated_metrics,
                "train_rows": len(fold.train),
                "training_class_counts": {
                    label: int((training_targets == index).sum()) for label, index in TARGET_LABELS.items()
                },
                "validation_rows": len(fold.validation),
                "test_rows": len(fold.test),
                "validation_start": min(times[index] for index in fold.validation).isoformat(),
                "validation_end": max(times[index] for index in fold.validation).isoformat(),
                "test_start": min(times[index] for index in fold.test).isoformat(),
                "test_end": max(times[index] for index in fold.test).isoformat(),
            }
        )
        baseline = self._bookmaker_baseline(dataset.frame, fold.test, targets)
        if baseline is not None:
            test_metrics["bookmaker_baseline"] = baseline
        if model_type in {"poisson", "dixon-coles"}:
            applicability_policy = self._validated_applicability_policy(
                dataset.frame,
                fold,
                validation_probabilities,
                validation_targets,
                probabilities,
                targets,
                maximum_log_loss=policy.maximum_log_loss,
                maximum_brier=policy.maximum_brier,
            )
            if applicability_policy is not None:
                test_metrics["applicability_policy"] = applicability_policy
        evaluation_passed = bool(
            np.isfinite(float(test_metrics["log_loss"]))
            and np.isfinite(float(test_metrics["brier"]))
            and float(test_metrics["log_loss"]) <= policy.maximum_log_loss
            and float(test_metrics["brier"]) <= policy.maximum_brier
        )
        final_evidence = assess_model_evidence(
            model_type,
            dataset.frame,
            policy,
            feature_columns=evidence_features,
            calibrated=bool(calibration_method) or policy.calibration_rows == 0,
            evaluation_passed=evaluation_passed,
        )
        test_metrics["evidence_state"] = final_evidence.state
        test_metrics["evidence_reasons"] = list(final_evidence.reasons)
        test_metrics["calibration_required"] = policy.calibration_rows > 0
        evaluation_training_cutoff = max(times[index] for index in fold.train)
        deployment_training_start = min(times[index] for index in fold.train)
        deployment_training_end = evaluation_training_cutoff
        if training_mode == "full_refit":
            if model_type in {"elo", "poisson", "dixon-coles"}:
                model, deployment_hyperparameters = self._refit_statistical_for_deployment(
                    model_type,
                    dataset.frame,
                    hyperparameters,
                )
            else:
                model, deployment_hyperparameters = self._refit_ml_for_deployment(
                    model_type,
                    dataset.frame,
                    hyperparameters,
                    feature_columns,
                )
            hyperparameters = {**hyperparameters, **deployment_hyperparameters}
            deployment_training_start = min(times)
            deployment_training_end = max(times)
            test_metrics["deployment_refit"] = {
                "performed": True,
                "protocol": "evaluate-on-untouched-holdout-freeze-hyperparameters-then-refit-all-observations",
                "evaluation_training_cutoff": evaluation_training_cutoff.isoformat(),
                "deployment_training_cutoff": deployment_training_end.isoformat(),
                "deployment_rows": dataset.frame.height,
            }
        created_at = datetime.now(UTC)
        version = self._version(model_type, dataset.dataset_hash, created_at)
        artifact_path = dated_artifact_directory(self.artifacts_dir / "models", created_at) / version / "model.pkl"
        model.save(artifact_path)
        if calibrator is not None:
            (artifact_path.parent / "calibrator.pkl").write_bytes(
                pickle.dumps(calibrator, protocol=pickle.HIGHEST_PROTOCOL)
            )
        libraries = self._library_versions()
        run = ModelRun(
            model_type=model_type,
            version=version,
            status="candidate",
            training_start=deployment_training_start,
            training_end=deployment_training_end,
            feature_schema_hash=dataset.schema_hash,
            training_dataset_hash=dataset.dataset_hash,
            hyperparameters=hyperparameters,
            metrics=test_metrics,
            calibration_method=calibration_method,
            artifact_path=artifact_path,
            library_versions=libraries,
            git_commit=self._git_commit(),
            created_at=created_at,
        )
        manifest = {
            **asdict(run),
            "dataset_id": dataset.dataset_id,
            "dataset_name": dataset.name,
            "dataset_config": dataset.config,
            "feature_columns": feature_columns,
            "feature_quality_audit": self._feature_quality_audit(dataset.frame, feature_columns),
            "class_order": ["HOME", "DRAW", "AWAY"],
            "random_seed": self.random_seed,
            "leakage_audit": "passed",
        }
        write_artifact_metadata(artifact_path, manifest)
        try:
            ModelRegistry(self.connection).register(run)
            self.connection.execute(
                "UPDATE model_runs SET evidence_state=?, parent_model_version=?, training_mode=?, "
                "training_cutoff=?, observations_included=? WHERE version=?",
                [
                    final_evidence.state,
                    parent_model_version,
                    training_mode,
                    deployment_training_end,
                    dataset.frame.height,
                    version,
                ],
            )
            persist_evidence_assessment(
                self.connection,
                final_evidence,
                dataset_id=dataset.dataset_id,
                model_version=version,
            )
        except Exception:
            artifact_path.unlink(missing_ok=True)
            artifact_path.with_suffix(artifact_path.suffix + ".json").unlink(missing_ok=True)
            (artifact_path.parent / "calibrator.pkl").unlink(missing_ok=True)
            raise
        return TrainingResult(
            version,
            model_type,
            artifact_path,
            test_metrics,
            dataset.dataset_id,
            final_evidence.state,
        )

    def _validated_applicability_policy(
        self,
        frame: pl.DataFrame,
        fold: Any,
        validation_probabilities: np.ndarray,
        validation_targets: np.ndarray,
        test_probabilities: np.ndarray,
        test_targets: np.ndarray,
        *,
        maximum_log_loss: float,
        maximum_brier: float,
    ) -> dict[str, Any] | None:
        """Validate the configured history floor on validation, then confirm on test."""
        # Five recency-weighted matches is the predeclared shadow/applicability
        # floor. It is selected on validation and must independently pass the
        # untouched test period below; it is not tuned on realized ROI.
        threshold = 5.0
        validation_history = self._effective_team_history(frame, fold.train, fold.validation)
        test_history = self._effective_team_history(frame, fold.train, fold.test)
        validation_mask = validation_history >= threshold
        test_mask = test_history >= threshold
        if validation_mask.sum() < 100 or test_mask.sum() < 100:
            return None
        validation_metrics = probability_metrics(
            validation_targets[validation_mask], validation_probabilities[validation_mask]
        )
        test_metrics = probability_metrics(test_targets[test_mask], test_probabilities[test_mask])
        validated = all(
            (
                float(validation_metrics["log_loss"]) <= maximum_log_loss,
                float(validation_metrics["brier"]) <= maximum_brier,
                float(test_metrics["log_loss"]) <= maximum_log_loss,
                float(test_metrics["brier"]) <= maximum_brier,
                bool(validation_metrics["probability_integrity"]["passed"]),
                bool(test_metrics["probability_integrity"]["passed"]),
            )
        )
        return {
            "validated": validated,
            "version": "effective-history-5-v1",
            "minimum_effective_matches": threshold,
            "selection_protocol": (
                "predeclared threshold; validation selection; untouched chronological test confirmation"
            ),
            "validation_rows": int(validation_mask.sum()),
            "test_rows": int(test_mask.sum()),
            "validation": {
                key: validation_metrics[key] for key in ("log_loss", "brier", "rps", "expected_calibration_error")
            },
            "test": {key: test_metrics[key] for key in ("log_loss", "brier", "rps", "expected_calibration_error")},
        }

    def _effective_team_history(self, frame: pl.DataFrame, train: Any, targets: Any) -> np.ndarray:
        home = frame["home_team_id"].cast(pl.String).to_list()
        away = frame["away_team_id"].cast(pl.String).to_list()
        times = frame["prediction_timestamp"].to_list()
        result: list[float] = []
        decay = np.log(2.0) / self.time_decay_half_life_days
        for target in targets:
            target_time = times[int(target)]
            values = []
            for team in (home[int(target)], away[int(target)]):
                effective = sum(
                    np.exp(-decay * max(0.0, (target_time - times[int(index)]).total_seconds() / 86_400))
                    for index in train
                    if team in {home[int(index)], away[int(index)]}
                )
                values.append(float(effective))
            result.append(min(values))
        return np.asarray(result)

    def _refit_statistical_for_deployment(
        self,
        model_type: str,
        frame: pl.DataFrame,
        selected_hyperparameters: dict[str, Any],
    ) -> tuple[Any, dict[str, Any]]:
        """Refit the deployable artifact after evaluation has consumed its holdout."""
        matches = self._matches(frame)
        if model_type == "elo":
            model: Any = EloModel()
            model.fit(matches)
        else:
            model_class = DixonColesModel if model_type == "dixon-coles" else PoissonModel
            model = model_class(
                maximum_goals=int(selected_hyperparameters.get("maximum_goals", 10)),
                regularization=float(selected_hyperparameters.get("regularization", 10.0)),
            )
            timestamps = frame["prediction_timestamp"].to_list()
            model.fit_timed(
                [(*match, timestamp) for match, timestamp in zip(matches, timestamps, strict=True)],
                half_life_days=float(
                    selected_hyperparameters.get("time_decay_half_life_days", self.time_decay_half_life_days)
                ),
            )
            self._attach_score_model_lineage(model, frame)
        metadata = model.metadata()
        if model_type in {"poisson", "dixon-coles"}:
            metadata["time_decay_half_life_days"] = float(
                selected_hyperparameters.get("time_decay_half_life_days", self.time_decay_half_life_days)
            )
        metadata["deployment_refit_rows"] = frame.height
        return model, metadata

    def _refit_ml_for_deployment(
        self,
        model_type: str,
        frame: pl.DataFrame,
        selected_hyperparameters: dict[str, Any],
        feature_columns: list[str],
    ) -> tuple[Any, dict[str, Any]]:
        """Fit the immutable deployment candidate after holdout evaluation.

        Model selection and calibration remain based on chronological
        validation/test evidence. Only the already-selected specification is
        refitted, so no holdout metric is recomputed or optimized here.
        """
        matrix = frame.select(feature_columns).cast(pl.Float64).to_numpy()
        targets = self._targets(frame)
        if model_type == "logistic":
            model: Any = LogisticProbabilityModel(
                random_seed=self.random_seed,
                c=float(selected_hyperparameters.get("C", 1.0)),
            )
        elif model_type == "catboost":
            model = CatBoostProbabilityModel(
                random_seed=self.random_seed,
                threads=self.cpu_threads,
                iterations=int(selected_hyperparameters.get("iterations", 300)),
            )
        elif model_type == "lightgbm":
            model = LightGBMProbabilityModel(
                random_seed=self.random_seed,
                threads=self.cpu_threads,
                n_estimators=int(selected_hyperparameters.get("n_estimators", 300)),
            )
        else:  # pragma: no cover - caller is restricted to registered ML types
            raise ValueError(f"Unsupported ML deployment refit type {model_type!r}")
        model.fit(matrix, targets)
        return model, {**model.metadata(), "deployment_refit_rows": frame.height}

    def _fit(
        self,
        model_type: str,
        frame: pl.DataFrame,
        fold: Any,
        *,
        parent_model: Any | None = None,
        parent_cutoff: datetime | None = None,
    ) -> tuple[Any, np.ndarray, np.ndarray, dict[str, Any], list[str]]:
        if model_type in {"elo", "poisson", "dixon-coles"}:
            if parent_model is not None:
                raise ValueError(f"Warm-start is not implemented for {model_type}; use a versioned full refit")
            matches = self._matches(frame)
            train_matches = [matches[index] for index in fold.train]
            fixtures = [(matches[index][0], matches[index][1]) for index in fold.test]
            if model_type == "elo":
                model: Any = EloModel()
            elif model_type in {"poisson", "dixon-coles"}:
                model, validation_probabilities, metadata = self._select_score_model(
                    model_type,
                    frame,
                    fold.train,
                    fold.validation,
                )
            if model_type in {"poisson", "dixon-coles"}:
                timestamps = frame["prediction_timestamp"].to_list()
                self._attach_score_model_lineage(model, frame[fold.train])
            else:
                model.fit(train_matches)
            validation_fixtures = [(matches[index][0], matches[index][1]) for index in fold.validation]
            if model_type == "elo":
                validation_probabilities = model.predict_proba(validation_fixtures)
                metadata = model.metadata()
            return (
                model,
                validation_probabilities,
                model.predict_proba(fixtures),
                metadata,
                [],
            )

        maximum_missing = load_evidence_policies()[model_type].maximum_missing_fraction
        feature_columns = self._feature_columns(frame, maximum_missing_fraction=maximum_missing)
        matrix = frame.select(feature_columns).cast(pl.Float64).to_numpy()
        targets = self._targets(frame)
        if parent_model is not None:
            timestamps = frame["prediction_timestamp"].to_list()
            incremental = np.asarray(
                [index for index in fold.train if parent_cutoff is not None and timestamps[index] > parent_cutoff]
            )
            if not len(incremental):
                raise ValueError("Warm-start candidate has no new chronological training observations")
            if len(np.unique(targets[incremental])) < 2:
                raise ValueError("Warm-start observations do not contain enough target classes")
            ml_model = self._new_ml_model(model_type)
            ml_model.fit_incremental(matrix[incremental], targets[incremental], parent_model)
            validation_probabilities = self._ordered_probabilities(ml_model, matrix[fold.validation])
            probabilities = self._ordered_probabilities(ml_model, matrix[fold.test])
            hyperparameters = {
                **ml_model.metadata(),
                "candidate_generation": "warm_start",
                "incremental_observations": len(incremental),
            }
            return ml_model, validation_probabilities, probabilities, hyperparameters, feature_columns
        candidates = self._ml_candidates(model_type)
        tuned = constrained_probability_search(
            candidates,
            matrix[fold.train],
            targets[fold.train],
            matrix[fold.validation],
            targets[fold.validation],
        )
        validation_probabilities = self._ordered_probabilities(tuned.model, matrix[fold.validation])
        ml_model = tuned.model
        probabilities = self._ordered_probabilities(ml_model, matrix[fold.test])
        hyperparameters = {
            **ml_model.metadata(),
            **tuned.hyperparameters,
            "validation_log_loss": tuned.validation_log_loss,
        }
        return ml_model, validation_probabilities, probabilities, hyperparameters, feature_columns

    def _select_score_model(
        self,
        model_type: str,
        frame: pl.DataFrame,
        train: np.ndarray,
        validation: np.ndarray,
    ) -> tuple[Any, np.ndarray, dict[str, Any]]:
        matches = self._matches(frame)
        timestamps = frame["prediction_timestamp"].to_list()
        timed_matches = [(*matches[index], timestamps[index]) for index in train]
        validation_fixtures = [(matches[index][0], matches[index][1]) for index in validation]
        validation_targets = self._targets(frame)[validation]
        candidates: list[tuple[float, float]] = [
            (regularization, half_life) for regularization in (3.0, 10.0) for half_life in (180.0, 365.0, 730.0)
        ]
        best: tuple[float, Any, np.ndarray, float, float] | None = None
        model_class = DixonColesModel if model_type == "dixon-coles" else PoissonModel
        for regularization, half_life in candidates:
            model = model_class(regularization=regularization)
            model.fit_timed(timed_matches, half_life_days=half_life)
            probabilities = model.predict_proba(validation_fixtures)
            loss = float(probability_metrics(validation_targets, probabilities)["log_loss"])
            candidate = (loss, model, probabilities, regularization, half_life)
            if best is None or loss < best[0]:
                best = candidate
        if best is None:  # pragma: no cover - candidates are a fixed non-empty grid
            raise RuntimeError("Score-model tuning produced no candidate")
        loss, model, probabilities, regularization, half_life = best
        metadata = {
            **model.metadata(),
            "regularization": regularization,
            "time_decay_half_life_days": half_life,
            "validation_log_loss": loss,
            "selection_protocol": "chronological-validation-grid-v1",
            "candidate_count": len(candidates),
        }
        return model, probabilities, metadata

    def _attach_score_model_lineage(self, model: Any, frame: pl.DataFrame) -> None:
        """Persist exact training-row lineage used by fixture applicability."""
        fixture_ids = [str(value) for value in frame["fixture_id"].to_list()]
        model.fitted_fixture_ids = tuple(fixture_ids)
        histories: dict[str, list[tuple[datetime, bool]]] = {}
        for home, away, timestamp in frame.select("home_team_id", "away_team_id", "prediction_timestamp").iter_rows():
            histories.setdefault(str(home), []).append((timestamp, True))
            histories.setdefault(str(away), []).append((timestamp, False))
        model.fitted_team_history = {
            team: tuple(sorted(values, key=lambda value: value[0])) for team, values in histories.items()
        }
        placeholders = ",".join("?" for _ in fixture_ids)
        competition_rows = self.connection.execute(
            "SELECT CAST(competition_season_id AS VARCHAR), count(*) FROM fixtures_current "
            f"WHERE CAST(fixture_id AS VARCHAR) IN ({placeholders}) GROUP BY 1 ORDER BY 1",
            fixture_ids,
        ).fetchall()
        model.fitted_competition_counts = {str(row[0]): int(row[1]) for row in competition_rows}
        model.fitted_competitions = tuple(model.fitted_competition_counts)

    def _new_ml_model(self, model_type: str) -> Any:
        if model_type == "logistic":
            return LogisticProbabilityModel(random_seed=self.random_seed)
        if model_type == "catboost":
            return CatBoostProbabilityModel(random_seed=self.random_seed, threads=self.cpu_threads)
        if model_type == "lightgbm":
            return LightGBMProbabilityModel(random_seed=self.random_seed, threads=self.cpu_threads)
        raise ValueError(f"Warm-start is not supported for {model_type}")

    def _load_parent(self, model_type: str, version: str) -> tuple[Any, datetime]:
        row = self.connection.execute(
            "SELECT model_type, artifact_path, coalesce(training_cutoff, training_end) FROM model_runs WHERE version=?",
            [version],
        ).fetchone()
        if not row:
            raise ValueError(f"Parent model {version!r} does not exist")
        if row[0] != model_type:
            raise ValueError(f"Parent model type {row[0]!r} does not match {model_type!r}")
        loaders: dict[str, Any] = {
            "logistic": LogisticProbabilityModel,
            "catboost": CatBoostProbabilityModel,
            "lightgbm": LightGBMProbabilityModel,
        }
        if model_type not in loaders:
            raise ValueError(f"Warm-start is not supported for {model_type}")
        return loaders[model_type].load(Path(row[1])), row[2]

    def _ml_candidates(self, model_type: str) -> list[tuple[dict[str, Any], Any]]:
        if model_type == "logistic":
            return [
                (
                    {"C": c},
                    lambda c=c: LogisticProbabilityModel(random_seed=self.random_seed, c=c),
                )
                for c in (0.1, 1.0)
            ]
        if model_type == "catboost":
            return [
                (
                    {"iterations": iterations},
                    lambda iterations=iterations: CatBoostProbabilityModel(
                        random_seed=self.random_seed,
                        threads=self.cpu_threads,
                        iterations=iterations,
                    ),
                )
                for iterations in (100, 300)
            ]
        return [
            (
                {"n_estimators": estimators},
                lambda estimators=estimators: LightGBMProbabilityModel(
                    random_seed=self.random_seed,
                    threads=self.cpu_threads,
                    n_estimators=estimators,
                ),
            )
            for estimators in (100, 300)
        ]

    @staticmethod
    def _bookmaker_baseline(frame: pl.DataFrame, indexes: np.ndarray, targets: np.ndarray) -> dict[str, object] | None:
        columns = ("bookmaker_home_fair", "bookmaker_draw_fair", "bookmaker_away_fair")
        if not set(columns) <= set(frame.columns):
            return None
        return bookmaker_baseline_metrics(
            targets,
            frame[columns[0]].cast(pl.Float64).to_numpy()[indexes],
            frame[columns[1]].cast(pl.Float64).to_numpy()[indexes],
            frame[columns[2]].cast(pl.Float64).to_numpy()[indexes],
        )

    @staticmethod
    def _matches(frame: pl.DataFrame) -> list[tuple[str, str, int, int]]:
        return list(
            zip(
                frame["home_team_id"].cast(pl.String).to_list(),
                frame["away_team_id"].cast(pl.String).to_list(),
                frame["target_home_goals"].cast(pl.Int64).to_list(),
                frame["target_away_goals"].cast(pl.Int64).to_list(),
                strict=True,
            )
        )

    @staticmethod
    def _targets(frame: pl.DataFrame) -> np.ndarray:
        labels = frame["target_result"].to_list()
        try:
            return np.asarray([TARGET_LABELS[label] for label in labels], dtype=int)
        except KeyError as exc:
            raise ValueError(f"Unknown target result {exc.args[0]!r}") from exc

    @staticmethod
    def _feature_columns(frame: pl.DataFrame, *, maximum_missing_fraction: float = 1.0) -> list[str]:
        columns = []
        for name, dtype in frame.schema.items():
            if name in NON_FEATURE_COLUMNS or not (dtype.is_numeric() or dtype == pl.Boolean):
                continue
            series = frame[name].fill_nan(None) if dtype.is_float() else frame[name]
            if series.null_count() / max(1, frame.height) > maximum_missing_fraction:
                continue
            observed = series.drop_nulls()
            if observed.n_unique() <= 1:
                continue
            counts = observed.value_counts().get_column("count").to_numpy()
            dominant_fraction = float(np.max(counts)) / max(1, len(observed))
            if dominant_fraction >= 0.995:
                continue
            columns.append(name)
        if not columns:
            raise ValueError("Feature dataset contains no numeric model features")
        return columns

    @staticmethod
    def _feature_quality_audit(frame: pl.DataFrame, feature_columns: list[str]) -> dict[str, Any]:
        selected = set(feature_columns)
        features: dict[str, dict[str, float | int | bool | str]] = {}
        for name, dtype in frame.schema.items():
            if name in NON_FEATURE_COLUMNS or not (dtype.is_numeric() or dtype in {pl.Boolean, pl.Null}):
                continue
            series = frame[name].fill_nan(None) if dtype.is_float() else frame[name]
            observed = series.drop_nulls()
            counts = observed.value_counts().get_column("count").to_numpy() if len(observed) else np.array([])
            standard_deviation = observed.cast(pl.Float64).std() if len(observed) else None
            unique_values = observed.n_unique()
            dominant_fraction = float(np.max(counts)) / len(observed) if len(observed) else 0.0
            if name in selected:
                exclusion_reason = "INCLUDED"
            elif not len(observed):
                exclusion_reason = "ALL_NULL"
            elif unique_values <= 1:
                exclusion_reason = "CONSTANT"
            elif dominant_fraction >= 0.995:
                exclusion_reason = "NEAR_CONSTANT"
            else:
                exclusion_reason = "POLICY_EXCLUDED"
            features[name] = {
                "missing_fraction": series.null_count() / max(1, frame.height),
                "unique_values": unique_values,
                "dominant_fraction": dominant_fraction,
                "standard_deviation": (
                    float(standard_deviation) if isinstance(standard_deviation, (int, float)) else 0.0
                ),
                "selected": name in selected,
                "selection_status": exclusion_reason,
            }
        return {
            "rows": frame.height,
            "active_features": len(feature_columns),
            "candidate_features": len(features),
            "excluded_features": len(features) - len(feature_columns),
            "features_at_least_50_percent_missing": sum(
                float(values["missing_fraction"]) >= 0.5 for values in features.values()
            ),
            "features_at_least_90_percent_missing": sum(
                float(values["missing_fraction"]) >= 0.9 for values in features.values()
            ),
            "features": features,
        }

    @staticmethod
    def _ordered_probabilities(model: Any, matrix: np.ndarray) -> np.ndarray:
        probabilities = np.asarray(model.predict_proba(matrix), dtype=float)
        classes = np.asarray(model.estimator.classes_, dtype=int)
        ordered = np.zeros((len(matrix), 3), dtype=float)
        for source, target in enumerate(classes):
            ordered[:, target] = probabilities[:, source]
        return ordered

    @staticmethod
    def _version(model_type: str, dataset_hash: str, created_at: datetime) -> str:
        payload = f"{model_type}:{dataset_hash}:{created_at.isoformat()}".encode()
        suffix = hashlib.sha256(payload).hexdigest()[:8]
        return f"{model_type}-{created_at:%Y%m%dT%H%M%S%fZ}-{suffix}"

    @staticmethod
    def _library_versions() -> dict[str, str]:
        result: dict[str, str] = {}
        for package in ("sports-prediction-engine", "numpy", "polars", "scikit-learn", "scipy", "catboost", "lightgbm"):
            try:
                result[package] = package_version(package)
            except PackageNotFoundError:
                continue
        return result

    @staticmethod
    def _git_commit() -> str | None:
        completed = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
        commit = completed.stdout.strip()
        return commit if completed.returncode == 0 and commit else None
