"""Research-only walk-forward evaluation of direct ML market-family specialists."""

import hashlib
import io
import json
from dataclasses import asdict
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import duckdb
import lightgbm as lgb
import numpy as np
import polars as pl
from catboost import CatBoostClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from sports_engine.evaluation.comparison import load_evaluation_report
from sports_engine.evaluation.metrics import binary_probability_metrics
from sports_engine.evaluation.uncertainty import (
    binary_per_fixture_loss,
    chronological_block_bootstrap,
)
from sports_engine.models.calibration.binary import BinaryProbabilityCalibrator
from sports_engine.training.dataset_builder import load_training_dataset, prediction_times
from sports_engine.training.walk_forward import walk_forward_splits

FAMILY_SPECIALIST_POLICY_VERSION = "direct-binary-family-specialist-v1"
FAMILY_TARGETS = {
    "BTTS": "btts_target",
    "TOTAL_GOALS_2_5": "over_2_5_target",
}
FAMILY_SCORE_COLUMNS = {
    "BTTS": "btts_yes_probability",
    "TOTAL_GOALS_2_5": "over_2_5_probability",
}


def evaluate_ml_family_specialist(
    connection: duckdb.DuckDBPyConnection,
    ml_report: Path,
    output_dir: Path,
    *,
    random_seed: int,
    cpu_threads: int,
    score_report: Path | None = None,
) -> Path:
    """Fit direct BTTS and total-goals challengers on each chronological fold."""
    loaded = load_evaluation_report(ml_report)
    payload = loaded["payload"]
    model_type = str(payload.get("model_type"))
    if model_type not in {"logistic", "catboost", "lightgbm"}:
        raise ValueError("Family specialist requires a logistic, CatBoost, or LightGBM report")
    dataset = load_training_dataset(connection, str(payload.get("dataset_id")))
    if dataset.dataset_hash != payload.get("dataset_hash"):
        raise ValueError("Evaluation report and registered feature dataset hashes disagree")
    columns = payload.get("candidate_feature_columns")
    if not isinstance(columns, list) or not columns or any(not isinstance(value, str) for value in columns):
        raise ValueError("ML report does not contain a valid feature-column manifest")
    missing = sorted(set(columns) - set(dataset.frame.columns))
    if missing:
        raise ValueError(f"Feature dataset is missing candidate columns: {', '.join(missing)}")
    matrix = dataset.frame.select(columns).cast(pl.Float64).to_numpy()
    times = prediction_times(dataset)
    folds = walk_forward_splits(
        times,
        minimum_train_periods=int(payload["minimum_train_periods"]),
        test_periods=int(payload["test_periods"]),
        rolling_train_periods=payload.get("rolling_train_periods"),
    )
    calibration_method = payload.get("candidate_calibration_method")
    hyperparameters = payload.get("candidate_hyperparameters") or {}
    family_predictions: dict[str, list[np.ndarray]] = {family: [] for family in FAMILY_TARGETS}
    family_targets: dict[str, list[np.ndarray]] = {family: [] for family in FAMILY_TARGETS}
    fold_metrics: dict[str, list[dict[str, Any]]] = {family: [] for family in FAMILY_TARGETS}
    indexes: list[np.ndarray] = []
    fold_numbers: list[np.ndarray] = []
    for fold_number, fold in enumerate(folds, start=1):
        fit, calibration = _calibration_partition(times, fold.train, bool(calibration_method))
        indexes.append(fold.test)
        fold_numbers.append(np.full(len(fold.test), fold_number, dtype=int))
        for family in FAMILY_TARGETS:
            targets = _family_targets(dataset.frame, family)
            estimator = _binary_estimator(
                model_type,
                hyperparameters,
                random_seed=random_seed,
                cpu_threads=cpu_threads,
            )
            estimator.fit(matrix[fit], targets[fit])
            probabilities = np.asarray(estimator.predict_proba(matrix[fold.test]))[:, 1]
            if calibration_method:
                calibration_probabilities = np.asarray(estimator.predict_proba(matrix[calibration]))[:, 1]
                calibrator = BinaryProbabilityCalibrator(
                    str(calibration_method), random_seed=random_seed
                ).fit(calibration_probabilities, targets[calibration])
                probabilities = calibrator.transform(probabilities)
            family_predictions[family].append(probabilities)
            family_targets[family].append(targets[fold.test])
            fold_metrics[family].append(binary_probability_metrics(targets[fold.test], probabilities))

    combined_indexes = np.concatenate(indexes)
    combined_folds = np.concatenate(fold_numbers)
    aggregate: dict[str, Any] = {}
    for family in FAMILY_TARGETS:
        observed = np.concatenate(family_targets[family])
        predicted = np.concatenate(family_predictions[family])
        metrics = binary_probability_metrics(observed, predicted)
        metrics["fold_metrics"] = fold_metrics[family]
        metrics["metric_uncertainty"] = {
            metric: asdict(
                chronological_block_bootstrap(
                    binary_per_fixture_loss(observed, predicted, metric),
                    seed=random_seed,
                )
            )
            for metric in ("log_loss", "brier")
        }
        aggregate[family] = metrics

    score_comparison: dict[str, Any] = {}
    if score_report is not None:
        score = load_evaluation_report(score_report)
        if score["payload"].get("dataset_hash") != dataset.dataset_hash:
            raise ValueError("Score and specialist reports must use the same dataset hash")
        score_frame = score["predictions"].sort("prediction_timestamp", "fixture_id")
        specialist_keys = pl.DataFrame(
            {
                "fixture_id": [str(dataset.frame["fixture_id"][int(index)]) for index in combined_indexes],
                "prediction_timestamp": [times[int(index)] for index in combined_indexes],
            }
        ).sort("prediction_timestamp", "fixture_id")
        if not specialist_keys["fixture_id"].equals(score_frame["fixture_id"]) or not specialist_keys[
            "prediction_timestamp"
        ].equals(score_frame["prediction_timestamp"]):
            raise ValueError("Score and specialist predictions are not aligned on identical fixtures")
        order = np.lexsort(
            (
                np.asarray([str(dataset.frame["fixture_id"][int(index)]) for index in combined_indexes]),
                np.asarray([times[int(index)].timestamp() for index in combined_indexes]),
            )
        )
        for family in FAMILY_TARGETS:
            observed = np.concatenate(family_targets[family])[order]
            predicted = np.concatenate(family_predictions[family])[order]
            baseline = score_frame[FAMILY_SCORE_COLUMNS[family]].to_numpy()
            score_comparison[family] = {
                metric: asdict(
                    chronological_block_bootstrap(
                        binary_per_fixture_loss(observed, predicted, metric)
                        - binary_per_fixture_loss(observed, baseline, metric),
                        seed=random_seed,
                    )
                )
                for metric in ("log_loss", "brier")
            }

    result_frame = pl.DataFrame(
        {
            "fixture_id": [str(dataset.frame["fixture_id"][int(index)]) for index in combined_indexes],
            "prediction_timestamp": [times[int(index)] for index in combined_indexes],
            "fold": combined_folds,
            "btts_target": np.concatenate(family_targets["BTTS"]),
            "btts_yes_probability": np.concatenate(family_predictions["BTTS"]),
            "over_2_5_target": np.concatenate(family_targets["TOTAL_GOALS_2_5"]),
            "over_2_5_probability": np.concatenate(family_predictions["TOTAL_GOALS_2_5"]),
        }
    )
    buffer = io.BytesIO()
    result_frame.write_parquet(buffer, compression="zstd")
    prediction_payload = buffer.getvalue()
    created_at = datetime.now(UTC)
    result: dict[str, Any] = {
        "experiment": "ML_MARKET_FAMILY_SPECIALIST",
        "policy_version": FAMILY_SPECIALIST_POLICY_VERSION,
        "created_at": created_at.isoformat(),
        "model_type": model_type,
        "candidate_version": payload["candidate_version"],
        "source_ml_report": str(ml_report),
        "source_score_report": str(score_report) if score_report else None,
        "dataset_id": dataset.dataset_id,
        "dataset_hash": dataset.dataset_hash,
        "feature_columns": columns,
        "calibration_method": calibration_method,
        "folds": len(folds),
        "aggregate_metrics": aggregate,
        "paired_specialist_minus_score": score_comparison,
        "serving_changed": False,
        "promotion_eligible": False,
        "promotion_blockers": [
            "RETROSPECTIVE_DEVELOPMENT_ARTIFACTS_ALREADY_INSPECTED",
            "REQUIRES_GENUINELY_LATER_PREDECLARED_TEMPORAL_CONFIRMATION",
            "REQUIRES_FAMILY_SPECIFIC_CALIBRATION_AND_SCOPE_VALIDATION",
            "REQUIRES_MARKET_BASELINE_POLICY_EVIDENCE",
        ],
        "interpretation": (
            "Each binary model is a market-family specialist. Evidence and any future role are confined "
            "to that family; outputs are not a score distribution and cannot price correct scores or another family."
        ),
        "prediction_artifact": {
            "rows": result_frame.height,
            "sha256": hashlib.sha256(prediction_payload).hexdigest(),
        },
    }
    digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:12]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{model_type}-family-specialist-{dataset.dataset_hash[:12]}-{digest}.json"
    prediction_path = path.with_suffix(".predictions.parquet")
    result["prediction_artifact"]["path"] = str(prediction_path)
    prediction_path.write_bytes(prediction_payload)
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return path


def compare_ml_family_specialists(
    report_paths: list[Path] | tuple[Path, ...],
    output_dir: Path,
    *,
    random_seed: int,
) -> Path:
    """Pair direct family specialists on identical out-of-fold fixtures."""
    if len(report_paths) < 2:
        raise ValueError("At least two family-specialist reports are required")
    reports = [_load_specialist_report(path) for path in report_paths]
    if len({item["payload"].get("dataset_hash") for item in reports}) != 1:
        raise ValueError("Family-specialist reports must use the same dataset hash")
    comparisons: list[dict[str, Any]] = []
    for left, right in combinations(reports, 2):
        left_frame = left["predictions"].sort("prediction_timestamp", "fixture_id")
        right_frame = right["predictions"].sort("prediction_timestamp", "fixture_id")
        for column in ("fixture_id", "prediction_timestamp", "fold"):
            if not left_frame[column].equals(right_frame[column]):
                raise ValueError(f"Family-specialist reports are not aligned on {column}")
        for family, target_column, probability_column in (
            ("BTTS", "btts_target", "btts_yes_probability"),
            ("TOTAL_GOALS_2_5", "over_2_5_target", "over_2_5_probability"),
        ):
            if not left_frame[target_column].equals(right_frame[target_column]):
                raise ValueError(f"Family-specialist targets disagree for {family}")
            targets = left_frame[target_column].to_numpy()
            intervals = {
                metric: asdict(
                    chronological_block_bootstrap(
                        binary_per_fixture_loss(targets, left_frame[probability_column].to_numpy(), metric)
                        - binary_per_fixture_loss(
                            targets, right_frame[probability_column].to_numpy(), metric
                        ),
                        seed=random_seed,
                    )
                )
                for metric in ("log_loss", "brier")
            }
            left_dominates = all(float(interval["upper"]) < 0 for interval in intervals.values())
            right_dominates = all(float(interval["lower"]) > 0 for interval in intervals.values())
            comparisons.append(
                {
                    "market_family": family,
                    "left_model_type": left["payload"]["model_type"],
                    "right_model_type": right["payload"]["model_type"],
                    "rows": left_frame.height,
                    "paired_loss_difference_left_minus_right": intervals,
                    "verdict": (
                        "LEFT_DOMINATES"
                        if left_dominates
                        else "RIGHT_DOMINATES"
                        if right_dominates
                        else "NO_SIGNIFICANT_DOMINANCE"
                    ),
                }
            )
    created_at = datetime.now(UTC)
    payload = {
        "experiment": "ML_MARKET_FAMILY_SPECIALIST_COMPARISON",
        "policy_version": FAMILY_SPECIALIST_POLICY_VERSION,
        "created_at": created_at.isoformat(),
        "dataset_hash": reports[0]["payload"]["dataset_hash"],
        "reports": [str(item["path"]) for item in reports],
        "comparisons": comparisons,
        "promotion_eligible": False,
        "interpretation": (
            "Dominance is family-specific and requires both paired log-loss and Brier 95% chronological "
            "block intervals to favour the same model. No result transfers to another market family."
        ),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"family-specialist-comparison-{str(payload['dataset_hash'])[:12]}-{digest}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _load_specialist_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("experiment") != "ML_MARKET_FAMILY_SPECIALIST":
        raise ValueError(f"Not a family-specialist report: {path}")
    artifact = payload.get("prediction_artifact")
    if not isinstance(artifact, dict) or not artifact.get("path") or not artifact.get("sha256"):
        raise ValueError(f"Family-specialist report has no auditable predictions: {path}")
    prediction_path = Path(str(artifact["path"]))
    raw = prediction_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
        raise ValueError(f"Family-specialist artifact integrity failed: {prediction_path}")
    frame = pl.read_parquet(prediction_path)
    if frame.height != int(artifact.get("rows", -1)):
        raise ValueError("Family-specialist artifact row count disagrees with its report")
    return {"path": path, "payload": payload, "predictions": frame}


def _family_targets(frame: pl.DataFrame, family: str) -> np.ndarray:
    home = frame["target_home_goals"].cast(pl.Int64).to_numpy()
    away = frame["target_away_goals"].cast(pl.Int64).to_numpy()
    if family == "BTTS":
        return ((home > 0) & (away > 0)).astype(int)
    if family == "TOTAL_GOALS_2_5":
        return ((home + away) >= 3).astype(int)
    raise ValueError(f"Unsupported family {family!r}")


def _calibration_partition(
    times: list[datetime], train: np.ndarray, calibrated: bool
) -> tuple[np.ndarray, np.ndarray]:
    if not calibrated:
        return train, np.asarray([], dtype=int)
    periods = sorted({times[int(index)] for index in train})
    calibration_periods = max(1, len(periods) // 5)
    if calibration_periods >= len(periods):
        raise ValueError("Walk-forward fold has insufficient history for calibration")
    calibration_times = set(periods[-calibration_periods:])
    fit = np.asarray([index for index in train if times[int(index)] not in calibration_times])
    calibration = np.asarray([index for index in train if times[int(index)] in calibration_times])
    return fit, calibration


def _binary_estimator(
    model_type: str,
    hyperparameters: dict[str, Any],
    *,
    random_seed: int,
    cpu_threads: int,
) -> Any:
    if model_type == "logistic":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=float(hyperparameters.get("C", 1.0)),
                        max_iter=1000,
                        class_weight="balanced",
                        random_state=random_seed,
                    ),
                ),
            ]
        )
    if model_type == "catboost":
        return CatBoostClassifier(
            loss_function="Logloss",
            iterations=int(hyperparameters.get("iterations", 300)),
            depth=6,
            learning_rate=0.05,
            random_seed=random_seed,
            thread_count=cpu_threads,
            verbose=False,
            allow_writing_files=False,
        )
    if model_type == "lightgbm":
        return lgb.LGBMClassifier(
            objective="binary",
            n_estimators=int(hyperparameters.get("n_estimators", 300)),
            num_leaves=31,
            learning_rate=0.05,
            random_state=random_seed,
            n_jobs=cpu_threads,
            verbosity=-1,
        )
    raise ValueError(f"Unsupported ML model type {model_type!r}")
