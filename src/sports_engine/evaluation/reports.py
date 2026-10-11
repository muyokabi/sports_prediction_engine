import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import polars as pl

from sports_engine.core.paths import dated_artifact_directory
from sports_engine.evaluation.bookmaker_baseline import bookmaker_baseline_metrics
from sports_engine.evaluation.metrics import probability_metrics
from sports_engine.evaluation.uncertainty import (
    chronological_block_bootstrap,
    paired_metric_difference,
    per_fixture_loss,
)
from sports_engine.models.calibration.multiclass import MulticlassProbabilityCalibrator
from sports_engine.models.ml.catboost import CatBoostProbabilityModel
from sports_engine.models.ml.lightgbm import LightGBMProbabilityModel
from sports_engine.models.ml.logistic import LogisticProbabilityModel
from sports_engine.models.registry import validate_model_type
from sports_engine.models.statistical.dixon_coles import DixonColesModel
from sports_engine.models.statistical.elo import EloModel
from sports_engine.models.statistical.poisson import PoissonModel
from sports_engine.training.dataset_builder import load_training_dataset, prediction_times
from sports_engine.training.evidence import load_evidence_policies
from sports_engine.training.trainer import TARGET_LABELS
from sports_engine.training.walk_forward import walk_forward_splits


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    model_type: str
    dataset_id: str
    dataset_hash: str
    fold_metrics: list[dict[str, Any]]
    aggregate_metrics: dict[str, Any]
    created_at: datetime
    path: Path


@dataclass(frozen=True, slots=True)
class EvaluationCandidate:
    version: str
    hyperparameters: dict[str, Any]
    calibration_method: str | None
    feature_columns: tuple[str, ...]


class WalkForwardEvaluator:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        output_dir: Path,
        *,
        random_seed: int,
        cpu_threads: int,
        time_decay_half_life_days: float = 365.0,
        minimum_competition_rows: int = 100,
        maximum_competition_ece: float = 0.08,
        probability_scope_policy_version: str = "competition-calibration-v1",
    ) -> None:
        self.connection = connection
        self.output_dir = output_dir
        self.random_seed = random_seed
        self.cpu_threads = cpu_threads
        self.time_decay_half_life_days = time_decay_half_life_days
        self.minimum_competition_rows = minimum_competition_rows
        self.maximum_competition_ece = maximum_competition_ece
        self.probability_scope_policy_version = probability_scope_policy_version

    def evaluate(
        self,
        model_type: str,
        *,
        dataset_name: str | None = None,
        minimum_train_periods: int | None = None,
        test_periods: int | None = None,
        rolling_train_periods: int | None = None,
    ) -> EvaluationReport:
        validate_model_type(model_type)
        dataset = load_training_dataset(self.connection, dataset_name)
        candidate = self._candidate(model_type, dataset.dataset_hash)
        times = prediction_times(dataset)
        distinct = len(set(times))
        minimum = minimum_train_periods or max(3, int(distinct * 0.6))
        test_size = test_periods or max(1, int(distinct * 0.1))
        folds = walk_forward_splits(
            times,
            minimum_train_periods=minimum,
            test_periods=test_size,
            rolling_train_periods=rolling_train_periods,
        )
        targets = np.asarray([TARGET_LABELS[value] for value in dataset.frame["target_result"]])
        all_targets: list[np.ndarray] = []
        all_probabilities: list[np.ndarray] = []
        all_test_indexes: list[np.ndarray] = []
        fold_metrics: list[dict[str, Any]] = []
        for fold in folds:
            probabilities = self._fit_predict(model_type, dataset.frame, fold.train, fold.test, candidate)
            observed = targets[fold.test]
            metrics = probability_metrics(observed, probabilities)
            fold_metrics.append(metrics)
            all_targets.append(observed)
            all_probabilities.append(probabilities)
            all_test_indexes.append(fold.test)
        combined_targets = np.concatenate(all_targets)
        combined_probabilities = np.vstack(all_probabilities)
        aggregate: dict[str, Any] = probability_metrics(combined_targets, combined_probabilities)
        aggregate["folds"] = len(folds)
        aggregate["test_rows"] = len(combined_targets)
        combined_indexes = np.concatenate(all_test_indexes)
        aggregate["probability_forensics"] = self._probability_forensics(
            dataset.frame,
            combined_indexes,
            combined_targets,
            combined_probabilities,
        )
        aggregate["metric_uncertainty"] = {
            metric: asdict(
                chronological_block_bootstrap(
                    per_fixture_loss(combined_targets, combined_probabilities, metric),
                    seed=self.random_seed,
                )
            )
            for metric in ("log_loss", "brier", "rps")
        }
        baseline = self._baseline(dataset.frame, combined_indexes, combined_targets)
        if baseline is not None:
            aggregate["bookmaker_baseline"] = baseline
            market = self._market_matrix(dataset.frame, combined_indexes)
            usable = np.isfinite(market).all(axis=1) & (market.sum(axis=1) > 0)
            normalized = market[usable] / market[usable].sum(axis=1, keepdims=True)
            aggregate["mean_absolute_probability_delta"] = float(
                np.mean(np.abs(combined_probabilities[usable] - normalized))
            )
            aggregate["paired_market_difference"] = {
                metric: asdict(
                    paired_metric_difference(
                        combined_targets[usable],
                        combined_probabilities[usable],
                        normalized,
                        metric,
                        seed=self.random_seed,
                    )
                )
                for metric in ("log_loss", "brier", "rps")
            }
        closing = self._closing_baseline(dataset.frame, combined_indexes, combined_targets)
        if closing is not None:
            aggregate["closing_market"] = closing
        created_at = datetime.now(UTC)
        payload = {
            "model_type": model_type,
            "candidate_version": candidate.version,
            "candidate_hyperparameters": candidate.hyperparameters,
            "candidate_calibration_method": candidate.calibration_method,
            "candidate_feature_columns": list(candidate.feature_columns),
            "dataset_id": dataset.dataset_id,
            "dataset_hash": dataset.dataset_hash,
            "fold_metrics": fold_metrics,
            "aggregate_metrics": aggregate,
            "created_at": created_at.isoformat(),
            "minimum_train_periods": minimum,
            "test_periods": test_size,
            "rolling_train_periods": rolling_train_periods,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        output_dir = dated_artifact_directory(self.output_dir, created_at)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{model_type}-{dataset.dataset_hash[:12]}-{digest}.json"
        if not path.exists():
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self._persist_probability_scope_validations(model_type, dataset.dataset_hash, aggregate, path, created_at)
        return EvaluationReport(
            model_type,
            dataset.dataset_id,
            dataset.dataset_hash,
            fold_metrics,
            aggregate,
            created_at,
            path,
        )

    def _probability_forensics(
        self,
        frame: pl.DataFrame,
        indexes: np.ndarray,
        targets: np.ndarray,
        probabilities: np.ndarray,
    ) -> dict[str, Any]:
        fixture_ids = [str(frame["fixture_id"][int(index)]) for index in indexes]
        placeholders = ",".join("?" for _ in fixture_ids)
        rows = self.connection.execute(
            "SELECT CAST(f.fixture_id AS VARCHAR), c.name FROM fixtures_current f "
            "JOIN competition_seasons cs USING (competition_season_id) "
            "JOIN competitions c USING (competition_id) "
            f"WHERE CAST(f.fixture_id AS VARCHAR) IN ({placeholders})",
            fixture_ids,
        ).fetchall()
        competition_by_fixture = {str(row[0]): str(row[1]) for row in rows}
        competitions = np.asarray([competition_by_fixture.get(value, "UNKNOWN") for value in fixture_ids])
        by_competition: dict[str, Any] = {}
        for competition in sorted(set(competitions)):
            members = competitions == competition
            if members.sum() < 30:
                continue
            metrics = probability_metrics(targets[members], probabilities[members])
            by_competition[competition] = {
                "rows": int(members.sum()),
                **{key: metrics[key] for key in ("log_loss", "brier", "rps", "expected_calibration_error")},
                "probability_integrity": metrics["probability_integrity"],
                "metric_uncertainty": {
                    metric: asdict(
                        chronological_block_bootstrap(
                            per_fixture_loss(targets[members], probabilities[members], metric),
                            samples=1_000,
                            seed=self.random_seed,
                        )
                    )
                    for metric in ("log_loss", "brier")
                },
            }
        predicted = probabilities.argmax(axis=1)
        confidence = probabilities.max(axis=1)
        correct = predicted == targets
        confidence_bands = []
        for lower, upper in zip(np.arange(0.3, 1.0, 0.1), np.arange(0.4, 1.1, 0.1), strict=True):
            members = (confidence > lower) & (confidence <= upper)
            if members.any():
                mean_confidence = float(confidence[members].mean())
                accuracy = float(correct[members].mean())
                confidence_bands.append(
                    {
                        "lower": round(float(lower), 2),
                        "upper": round(float(upper), 2),
                        "rows": int(members.sum()),
                        "mean_confidence": mean_confidence,
                        "accuracy": accuracy,
                        "calibration_gap": accuracy - mean_confidence,
                    }
                )
        material_gaps = [
            item for item in confidence_bands if item["rows"] >= 50 and abs(item["calibration_gap"]) > 0.10
        ]
        integrity = probability_metrics(targets, probabilities)["probability_integrity"]
        return {
            "passed": bool(integrity["passed"]) and not material_gaps,
            "reasons": ["MATERIAL_CONFIDENCE_BAND_MISCALIBRATION"] if material_gaps else [],
            "confidence_bands": confidence_bands,
            "competition_metrics_minimum_30_rows": by_competition,
        }

    def _persist_probability_scope_validations(
        self,
        model_type: str,
        dataset_hash: str,
        aggregate: dict[str, Any],
        evaluation_path: Path,
        validated_at: datetime,
    ) -> None:
        """Bind chronological league reliability evidence to exact immutable model versions."""
        if model_type not in {"poisson", "dixon-coles"}:
            return
        versions = [
            str(row[0])
            for row in self.connection.execute(
                "SELECT version FROM model_runs WHERE model_type=? AND training_dataset_hash=? "
                "AND status IN ('candidate','champion')",
                [model_type, dataset_hash],
            ).fetchall()
        ]
        if not versions:
            return
        evidence_policy = load_evidence_policies()[model_type]
        forensics = aggregate.get("probability_forensics")
        forensic_payload = forensics if isinstance(forensics, dict) else {}
        competitions = forensic_payload.get("competition_metrics_minimum_30_rows")
        competition_metrics = competitions if isinstance(competitions, dict) else {}
        for version in versions:
            for competition, raw_metrics in competition_metrics.items():
                metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
                rows = int(metrics.get("rows") or 0)
                reasons: list[str] = []
                if rows < self.minimum_competition_rows:
                    reasons.append("INSUFFICIENT_COMPETITION_EVALUATION_ROWS")
                integrity = metrics.get("probability_integrity")
                integrity_payload = integrity if isinstance(integrity, dict) else {}
                if integrity_payload.get("passed") is not True:
                    reasons.append("COMPETITION_PROBABILITY_INTEGRITY_FAILED")
                ece = float(metrics.get("expected_calibration_error", 1.0))
                if ece > self.maximum_competition_ece:
                    reasons.append("COMPETITION_CALIBRATION_ECE_EXCEEDED")
                uncertainty = metrics.get("metric_uncertainty")
                uncertainty_payload = uncertainty if isinstance(uncertainty, dict) else {}
                log_interval = uncertainty_payload.get("log_loss")
                brier_interval = uncertainty_payload.get("brier")
                log_upper = float(log_interval.get("upper", 1e9)) if isinstance(log_interval, dict) else 1e9
                brier_upper = float(brier_interval.get("upper", 1e9)) if isinstance(brier_interval, dict) else 1e9
                if log_upper > evidence_policy.maximum_log_loss:
                    reasons.append("COMPETITION_LOG_LOSS_UNCERTAINTY_EXCEEDED")
                if brier_upper > evidence_policy.maximum_brier:
                    reasons.append("COMPETITION_BRIER_UNCERTAINTY_EXCEEDED")
                state = (
                    "VALIDATED"
                    if not reasons
                    else "INSUFFICIENT_SAMPLE"
                    if reasons == ["INSUFFICIENT_COMPETITION_EVALUATION_ROWS"]
                    else "FAILED"
                )
                key = ":".join(
                    (
                        version,
                        "MATCH_ODDS",
                        "COMPETITION",
                        str(competition),
                        self.probability_scope_policy_version,
                        str(evaluation_path),
                    )
                )
                self.connection.execute(
                    "INSERT INTO model_probability_scope_validations VALUES "
                    "(?, ?, ?, 'MATCH_ODDS', 'COMPETITION', ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT (validation_id) DO UPDATE SET state=excluded.state, metrics=excluded.metrics, "
                    "reason_codes=excluded.reason_codes, validated_at=excluded.validated_at",
                    [
                        str(uuid.uuid5(uuid.NAMESPACE_URL, f"sports-engine:probability-scope:{key}")),
                        version,
                        model_type,
                        str(competition),
                        state,
                        self.probability_scope_policy_version,
                        str(evaluation_path),
                        rows,
                        json.dumps(metrics),
                        json.dumps(reasons),
                        validated_at,
                    ],
                )

    def _candidate(self, model_type: str, dataset_hash: str) -> EvaluationCandidate:
        row = self.connection.execute(
            "SELECT version, hyperparameters, calibration_method, artifact_path FROM model_runs "
            "WHERE model_type=? AND training_dataset_hash=? AND status IN ('candidate','champion') "
            "ORDER BY created_at DESC LIMIT 1",
            [model_type, dataset_hash],
        ).fetchone()
        if not row:
            raise ValueError(f"No trained {model_type} candidate is registered for dataset {dataset_hash}")
        hyperparameters = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        manifest_path = Path(str(row[3])).with_suffix(Path(str(row[3])).suffix + ".json")
        if not manifest_path.is_file():
            raise ValueError(f"Candidate manifest is missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        columns = manifest.get("feature_columns", [])
        if not isinstance(columns, list) or any(not isinstance(value, str) for value in columns):
            raise ValueError(f"Candidate feature manifest is invalid: {manifest_path}")
        if model_type not in {"elo", "poisson", "dixon-coles"} and not columns:
            raise ValueError(f"Candidate feature manifest is empty: {manifest_path}")
        return EvaluationCandidate(str(row[0]), hyperparameters, str(row[2]) if row[2] else None, tuple(columns))

    def _fit_predict(
        self,
        model_type: str,
        frame: pl.DataFrame,
        train: np.ndarray,
        test: np.ndarray,
        candidate: EvaluationCandidate,
    ) -> np.ndarray:
        fit = train
        calibration = np.asarray([], dtype=int)
        if candidate.calibration_method:
            timestamps = frame["prediction_timestamp"].to_list()
            periods = sorted({timestamps[int(index)] for index in train})
            calibration_periods = max(1, len(periods) // 5)
            if calibration_periods >= len(periods):
                raise ValueError("Walk-forward fold has insufficient history for calibration")
            calibration_times = set(periods[-calibration_periods:])
            fit = np.asarray([index for index in train if timestamps[int(index)] not in calibration_times])
            calibration = np.asarray([index for index in train if timestamps[int(index)] in calibration_times])

        probabilities, calibration_probabilities = self._fit_predict_raw(
            model_type,
            frame,
            fit,
            test,
            calibration,
            candidate,
        )
        if candidate.calibration_method:
            targets = np.asarray([TARGET_LABELS[value] for value in frame["target_result"]])
            calibrator = MulticlassProbabilityCalibrator(
                candidate.calibration_method,
                random_seed=self.random_seed,
            ).fit(calibration_probabilities, targets[calibration])
            return calibrator.transform(probabilities)
        return probabilities

    def _fit_predict_raw(
        self,
        model_type: str,
        frame: pl.DataFrame,
        train: np.ndarray,
        test: np.ndarray,
        calibration: np.ndarray,
        candidate: EvaluationCandidate,
    ) -> tuple[np.ndarray, np.ndarray]:
        hyperparameters = candidate.hyperparameters
        if model_type in {"elo", "poisson", "dixon-coles"}:
            matches = list(
                zip(
                    frame["home_team_id"].cast(pl.String).to_list(),
                    frame["away_team_id"].cast(pl.String).to_list(),
                    frame["target_home_goals"].cast(pl.Int64).to_list(),
                    frame["target_away_goals"].cast(pl.Int64).to_list(),
                    strict=True,
                )
            )
            model: Any
            if model_type == "elo":
                model = EloModel(
                    k_factor=float(hyperparameters.get("k_factor", 20.0)),
                    home_advantage=float(hyperparameters.get("home_advantage", 60.0)),
                )
            elif model_type == "poisson":
                model = PoissonModel(
                    maximum_goals=int(hyperparameters.get("maximum_goals", 10)),
                    regularization=float(hyperparameters.get("regularization", 10.0)),
                )
            else:
                model = DixonColesModel(
                    maximum_goals=int(hyperparameters.get("maximum_goals", 10)),
                    regularization=float(hyperparameters.get("regularization", 10.0)),
                )
            if model_type in {"poisson", "dixon-coles"}:
                timestamps = frame["prediction_timestamp"].to_list()
                model.fit_timed(
                    [(*matches[index], timestamps[index]) for index in train],
                    half_life_days=float(
                        hyperparameters.get("time_decay_half_life_days", self.time_decay_half_life_days)
                    ),
                )
            else:
                model.fit([matches[index] for index in train])
            predictions = model.predict_proba([(matches[index][0], matches[index][1]) for index in test])
            calibration_predictions = model.predict_proba(
                [(matches[index][0], matches[index][1]) for index in calibration]
            )
            return predictions, calibration_predictions
        columns = list(candidate.feature_columns)
        missing = sorted(set(columns) - set(frame.columns))
        if missing:
            raise ValueError(f"Candidate evaluation features are absent from the dataset: {', '.join(missing)}")
        matrix = frame.select(columns).cast(pl.Float64).to_numpy()
        targets = np.asarray([TARGET_LABELS[value] for value in frame["target_result"]])
        if model_type == "logistic":
            model = LogisticProbabilityModel(
                random_seed=self.random_seed,
                c=float(hyperparameters.get("C", 1.0)),
            )
        elif model_type == "catboost":
            model = CatBoostProbabilityModel(
                random_seed=self.random_seed,
                threads=self.cpu_threads,
                iterations=int(hyperparameters.get("iterations", 300)),
            )
        else:
            model = LightGBMProbabilityModel(
                random_seed=self.random_seed,
                threads=self.cpu_threads,
                n_estimators=int(hyperparameters.get("n_estimators", 300)),
            )
        model.fit(matrix[train], targets[train])
        return self._ordered_probabilities(model, matrix[test]), self._ordered_probabilities(model, matrix[calibration])

    @staticmethod
    def _ordered_probabilities(model: Any, matrix: np.ndarray) -> np.ndarray:
        if not len(matrix):
            return np.empty((0, 3), dtype=float)
        probabilities = np.asarray(model.predict_proba(matrix))
        ordered = np.zeros((len(matrix), 3))
        for source, target in enumerate(np.asarray(model.estimator.classes_, dtype=int)):
            ordered[:, target] = probabilities[:, source]
        return ordered

    @staticmethod
    def _baseline(frame: pl.DataFrame, indexes: np.ndarray, targets: np.ndarray) -> dict[str, object] | None:
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
    def _market_matrix(frame: pl.DataFrame, indexes: np.ndarray) -> np.ndarray:
        return np.column_stack(
            [
                frame[column].cast(pl.Float64).to_numpy()[indexes]
                for column in (
                    "bookmaker_home_fair",
                    "bookmaker_draw_fair",
                    "bookmaker_away_fair",
                )
            ]
        )

    def _closing_baseline(
        self, frame: pl.DataFrame, indexes: np.ndarray, targets: np.ndarray
    ) -> dict[str, object] | None:
        observed_targets: list[int] = []
        probability_rows: list[list[float]] = []
        for target, index in zip(targets, indexes, strict=True):
            rows = self.connection.execute(
                "WITH latest AS (SELECT o.snapshot_id FROM odds_snapshots o "
                "JOIN fixtures_current f USING (fixture_id) WHERE o.fixture_id=? "
                "AND o.observed_at<=f.kickoff_utc ORDER BY o.observed_at DESC LIMIT 1) "
                "SELECT s.normalized_name, avg(p.fair_probability) FROM latest l "
                "JOIN odds_prices p USING (snapshot_id) JOIN bet_markets m USING (market_id) "
                "JOIN bet_selections s USING (selection_id) "
                "WHERE lower(m.name) IN ('match winner', '1x2') GROUP BY s.normalized_name",
                [frame["fixture_id"][int(index)]],
            ).fetchall()
            values = {name: value for name, value in rows}
            if not all(values.get(outcome) is not None for outcome in ("home", "draw", "away")):
                continue
            probability_rows.append([float(values[outcome]) for outcome in ("home", "draw", "away")])
            observed_targets.append(int(target))
        if not probability_rows:
            return None
        probabilities = np.asarray(probability_rows)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        return {
            **probability_metrics(np.asarray(observed_targets), probabilities),
            "rows": len(observed_targets),
        }
