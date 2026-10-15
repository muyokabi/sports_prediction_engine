import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from sports_engine.evaluation.uncertainty import (
    binary_per_fixture_loss,
    chronological_block_bootstrap,
    paired_metric_difference,
)

PREDICTION_COLUMNS = {
    "fixture_id",
    "prediction_timestamp",
    "target",
    "home_probability",
    "draw_probability",
    "away_probability",
}

SCORE_FAMILY_COLUMNS = {
    "BTTS": ("btts_target", "btts_yes_probability"),
    "TOTAL_GOALS_2_5": ("over_2_5_target", "over_2_5_probability"),
}


def compare_evaluation_reports(
    report_paths: list[Path] | tuple[Path, ...],
    output_dir: Path,
    *,
    random_seed: int,
) -> Path:
    """Compare candidates on identical out-of-fold fixtures.

    Standalone confidence intervals overlap even when paired losses differ
    consistently. This comparison retains fixture identity and bootstraps the
    per-fixture loss difference in chronological blocks.
    """
    if len(report_paths) < 2:
        raise ValueError("At least two evaluation reports are required")
    loaded = [load_evaluation_report(path) for path in report_paths]
    dataset_hashes = {item["payload"].get("dataset_hash") for item in loaded}
    if len(dataset_hashes) != 1:
        raise ValueError("Evaluation reports must use the same dataset hash")

    fixture_keys: set[tuple[str, object]] | None = None
    for item in loaded:
        frame = item["predictions"]
        keys = set(frame.select("fixture_id", "prediction_timestamp").iter_rows())
        if len(keys) != frame.height:
            raise ValueError(f"Prediction artifact contains duplicate fixtures: {item['path']}")
        if fixture_keys is None:
            fixture_keys = keys
        elif fixture_keys != keys:
            raise ValueError("Evaluation reports do not contain identical out-of-fold fixtures")

    ordered = sorted(
        loaded,
        key=lambda item: (
            float(item["payload"]["aggregate_metrics"]["log_loss"]),
            str(item["payload"]["model_type"]),
        ),
    )
    comparisons: list[dict[str, Any]] = []
    score_family_comparisons: list[dict[str, Any]] = []
    for candidate, comparator in combinations(ordered, 2):
        left = candidate["predictions"].sort("prediction_timestamp", "fixture_id")
        right = comparator["predictions"].sort("prediction_timestamp", "fixture_id")
        left_targets = left["target"].to_numpy()
        right_targets = right["target"].to_numpy()
        if not np.array_equal(left_targets, right_targets):
            raise ValueError("Evaluation prediction targets disagree for identical fixtures")
        left_probabilities = _probabilities(left)
        right_probabilities = _probabilities(right)
        intervals = {
            metric: asdict(
                paired_metric_difference(
                    left_targets,
                    left_probabilities,
                    right_probabilities,
                    metric,
                    seed=random_seed,
                )
            )
            for metric in ("log_loss", "brier", "rps")
        }
        candidate_dominates = all(float(intervals[metric]["upper"]) < 0 for metric in intervals)
        comparator_dominates = all(float(intervals[metric]["lower"]) > 0 for metric in intervals)
        comparisons.append(
            {
                "candidate_model_type": candidate["payload"]["model_type"],
                "candidate_version": candidate["payload"]["candidate_version"],
                "comparator_model_type": comparator["payload"]["model_type"],
                "comparator_version": comparator["payload"]["candidate_version"],
                "rows": left.height,
                "paired_loss_difference_candidate_minus_comparator": intervals,
                "verdict": (
                    "CANDIDATE_DOMINATES"
                    if candidate_dominates
                    else "COMPARATOR_DOMINATES"
                    if comparator_dominates
                    else "NO_SIGNIFICANT_DOMINANCE"
                ),
            }
        )
        shared_families = [
            family
            for family, columns in SCORE_FAMILY_COLUMNS.items()
            if set(columns) <= set(left.columns) and set(columns) <= set(right.columns)
        ]
        for family in shared_families:
            target_column, probability_column = SCORE_FAMILY_COLUMNS[family]
            family_targets = left[target_column].to_numpy()
            if not np.array_equal(family_targets, right[target_column].to_numpy()):
                raise ValueError(f"{family} targets disagree for identical fixtures")
            family_intervals = {
                metric: asdict(
                    chronological_block_bootstrap(
                        binary_per_fixture_loss(
                            family_targets, left[probability_column].to_numpy(), metric
                        )
                        - binary_per_fixture_loss(
                            family_targets, right[probability_column].to_numpy(), metric
                        ),
                        seed=random_seed,
                    )
                )
                for metric in ("log_loss", "brier")
            }
            candidate_dominates = all(float(value["upper"]) < 0 for value in family_intervals.values())
            comparator_dominates = all(float(value["lower"]) > 0 for value in family_intervals.values())
            score_family_comparisons.append(
                {
                    "market_family": family,
                    "candidate_model_type": candidate["payload"]["model_type"],
                    "candidate_version": candidate["payload"]["candidate_version"],
                    "comparator_model_type": comparator["payload"]["model_type"],
                    "comparator_version": comparator["payload"]["candidate_version"],
                    "rows": left.height,
                    "paired_loss_difference_candidate_minus_comparator": family_intervals,
                    "verdict": (
                        "CANDIDATE_DOMINATES"
                        if candidate_dominates
                        else "COMPARATOR_DOMINATES"
                        if comparator_dominates
                        else "NO_SIGNIFICANT_DOMINANCE"
                    ),
                }
            )

    created_at = datetime.now(UTC)
    payload = {
        "dataset_hash": next(iter(dataset_hashes)),
        "created_at": created_at.isoformat(),
        "models": [
            {
                "model_type": item["payload"]["model_type"],
                "candidate_version": item["payload"]["candidate_version"],
                "training_mode": item["payload"].get("candidate_training_mode", "unknown"),
                "report_path": str(item["path"]),
                "aggregate_metrics": {
                    key: item["payload"]["aggregate_metrics"][key]
                    for key in ("log_loss", "brier", "rps", "expected_calibration_error")
                },
            }
            for item in ordered
        ],
        "comparisons": comparisons,
        "score_family_comparisons": score_family_comparisons,
        "interpretation": (
            "Dominance requires the 95% chronological block-bootstrap interval to favour one model "
            "for every applicable proper loss on the same fixtures."
        ),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"model-comparison-{str(payload['dataset_hash'])[:12]}-{digest}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_evaluation_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    artifact = payload.get("prediction_artifact")
    if not isinstance(artifact, dict) or not artifact.get("path") or not artifact.get("sha256"):
        raise ValueError(f"Evaluation report has no auditable prediction artifact: {path}")
    prediction_path = Path(str(artifact["path"]))
    prediction_payload = prediction_path.read_bytes()
    if hashlib.sha256(prediction_payload).hexdigest() != artifact["sha256"]:
        raise ValueError(f"Evaluation prediction artifact integrity failed: {prediction_path}")
    frame = pl.read_parquet(prediction_path)
    missing = sorted(PREDICTION_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"Prediction artifact is missing columns: {', '.join(missing)}")
    if frame.height != int(artifact.get("rows", -1)):
        raise ValueError(f"Prediction artifact row count disagrees with report: {prediction_path}")
    return {"path": path, "payload": payload, "predictions": frame}


def _probabilities(frame: pl.DataFrame) -> np.ndarray:
    values = frame.select("home_probability", "draw_probability", "away_probability").to_numpy()
    if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1):
        raise ValueError("Prediction artifact contains invalid probabilities")
    if not np.allclose(values.sum(axis=1), 1.0, atol=1e-8):
        raise ValueError("Prediction artifact probabilities do not sum to one")
    return values
