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
            [] if model_type in {"elo", "poisson", "dixon-coles"} else self._feature_columns(dataset.frame)
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
        created_at = datetime.now(UTC)
        version = self._version(model_type, dataset.dataset_hash, created_at)
        artifact_path = self.artifacts_dir / "models" / version / "model.pkl"
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
            training_start=min(times[index] for index in fold.train),
            training_end=max(times[index] for index in fold.train),
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
                    max(times[index] for index in fold.train),
                    len(fold.train),
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
            raise
        return TrainingResult(
            version,
            model_type,
            artifact_path,
            test_metrics,
            dataset.dataset_id,
            final_evidence.state,
        )

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
            elif model_type == "poisson":
                model = PoissonModel()
            else:
                model = DixonColesModel()
            if model_type in {"poisson", "dixon-coles"}:
                timestamps = frame["prediction_timestamp"].to_list()
                timed_matches = [(*matches[index], timestamps[index]) for index in fold.train]
                model.fit_timed(timed_matches, half_life_days=self.time_decay_half_life_days)
            else:
                model.fit(train_matches)
            validation_fixtures = [(matches[index][0], matches[index][1]) for index in fold.validation]
            metadata = model.metadata()
            if model_type in {"poisson", "dixon-coles"}:
                metadata["time_decay_half_life_days"] = self.time_decay_half_life_days
            return (
                model,
                model.predict_proba(validation_fixtures),
                model.predict_proba(fixtures),
                metadata,
                [],
            )
        feature_columns = self._feature_columns(frame)
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
    def _feature_columns(frame: pl.DataFrame) -> list[str]:
        columns = [
            name
            for name, dtype in frame.schema.items()
            if name not in NON_FEATURE_COLUMNS and (dtype.is_numeric() or dtype == pl.Boolean)
        ]
        if not columns:
            raise ValueError("Feature dataset contains no numeric model features")
        return columns

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
