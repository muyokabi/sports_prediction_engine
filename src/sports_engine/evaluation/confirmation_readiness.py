"""Audit whether a later feature dataset can support temporal confirmation.

This module does not score a model or promote anything.  It answers the prior
question: did the ledger actually add a clean, later outcome era, or would a
"confirmation" rerun mostly recycle fixtures that have already been inspected?
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from sports_engine.training.dataset_builder import load_training_dataset

CONFIRMATION_READINESS_POLICY_VERSION = "temporal-confirmation-readiness-v1"
_KEY_COLUMNS = ["fixture_id", "prediction_timestamp"]
_TARGET_COLUMNS = ["target_home_goals", "target_away_goals", "target_result"]


def evaluate_confirmation_readiness(
    connection: duckdb.DuckDBPyConnection,
    baseline_dataset: str,
    candidate_dataset: str,
    output_dir: Path,
    *,
    minimum_new_rows: int = 100,
) -> Path:
    """Write an immutable audit of new, removed, or changed evaluation rows."""
    if minimum_new_rows < 1:
        raise ValueError("minimum_new_rows must be positive")
    baseline = load_training_dataset(connection, baseline_dataset)
    candidate = load_training_dataset(connection, candidate_dataset)
    if baseline.dataset_hash == candidate.dataset_hash:
        raise ValueError("Baseline and candidate datasets are identical")

    required = set(_KEY_COLUMNS + _TARGET_COLUMNS)
    for label, frame in (("baseline", baseline.frame), ("candidate", candidate.frame)):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{label} dataset is missing confirmation columns: {', '.join(missing)}")
        if frame.select(pl.struct(_KEY_COLUMNS).is_duplicated().any()).item():
            raise ValueError(f"{label} dataset contains duplicate fixture/timestamp keys")

    baseline_rows = baseline.frame.select(_KEY_COLUMNS + _TARGET_COLUMNS)
    candidate_rows = candidate.frame.select(_KEY_COLUMNS + _TARGET_COLUMNS)
    baseline_keys = baseline_rows.select(_KEY_COLUMNS)
    candidate_keys = candidate_rows.select(_KEY_COLUMNS)
    added = candidate_rows.join(baseline_keys, on=_KEY_COLUMNS, how="anti").sort(_KEY_COLUMNS)
    removed = baseline_rows.join(candidate_keys, on=_KEY_COLUMNS, how="anti").sort(_KEY_COLUMNS)
    overlap = baseline_rows.join(candidate_rows, on=_KEY_COLUMNS, how="inner", suffix="_candidate")
    target_change = pl.lit(False)
    for column in _TARGET_COLUMNS:
        target_change = target_change | pl.col(column).ne_missing(pl.col(f"{column}_candidate"))
    changed = overlap.filter(target_change)

    baseline_max = _require_datetime(
        baseline_rows["prediction_timestamp"].max(), "Baseline dataset has no prediction timestamps"
    )
    later_added = added.filter(pl.col("prediction_timestamp") > baseline_max)
    non_later_added = added.filter(pl.col("prediction_timestamp") <= baseline_max)
    added_dates = (
        added.select(pl.col("prediction_timestamp").dt.date().alias("date"))
        .unique()
        .sort("date")
    )

    reasons: list[str] = []
    if later_added.height < minimum_new_rows:
        reasons.append("INSUFFICIENT_GENUINELY_LATER_ROWS")
    if non_later_added.height:
        reasons.append("ADDITIONS_OVERLAP_PREVIOUSLY_INSPECTED_ERA")
    if removed.height:
        reasons.append("BASELINE_ROWS_REMOVED")
    if changed.height:
        reasons.append("OVERLAPPING_TARGETS_CHANGED")
    ready = not reasons

    delta_evidence = json.dumps(
        added.select(_KEY_COLUMNS + _TARGET_COLUMNS).to_dicts(),
        default=str,
        sort_keys=True,
    )
    candidate_max = _require_datetime(
        candidate_rows["prediction_timestamp"].max(), "Candidate dataset has no prediction timestamps"
    )
    created_at = datetime.now(UTC)
    result: dict[str, Any] = {
        "experiment": "TEMPORAL_CONFIRMATION_READINESS",
        "policy_version": CONFIRMATION_READINESS_POLICY_VERSION,
        "created_at": created_at.isoformat(),
        "baseline": {
            "dataset_id": baseline.dataset_id,
            "name": baseline.name,
            "dataset_hash": baseline.dataset_hash,
            "schema_hash": baseline.schema_hash,
            "rows": baseline.frame.height,
            "maximum_prediction_timestamp": baseline_max.isoformat(),
        },
        "candidate": {
            "dataset_id": candidate.dataset_id,
            "name": candidate.name,
            "dataset_hash": candidate.dataset_hash,
            "schema_hash": candidate.schema_hash,
            "rows": candidate.frame.height,
            "maximum_prediction_timestamp": candidate_max.isoformat(),
        },
        "contract": {
            "minimum_new_rows": minimum_new_rows,
            "new_rows_must_be_strictly_later": True,
            "removed_rows_allowed": False,
            "changed_overlapping_targets_allowed": False,
            "promotion_eligible": False,
        },
        "delta": {
            "added_rows": added.height,
            "genuinely_later_rows": later_added.height,
            "non_later_added_rows": non_later_added.height,
            "removed_rows": removed.height,
            "changed_overlapping_targets": changed.height,
            "distinct_added_dates": added_dates.height,
            "first_added_timestamp": _optional_iso(added["prediction_timestamp"].min()),
            "last_added_timestamp": _optional_iso(added["prediction_timestamp"].max()),
            "added_rows_sha256": hashlib.sha256(delta_evidence.encode()).hexdigest(),
        },
        "ready_for_confirmation_evaluation": ready,
        "reasons": reasons,
        "interpretation": (
            "Readiness only permits a later predeclared evaluation to be run. It is not model, calibration, "
            "market-baseline, actionability, or promotion evidence."
        ),
    }
    digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:12]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (
        f"confirmation-readiness-{baseline.dataset_hash[:12]}-to-"
        f"{candidate.dataset_hash[:12]}-{digest}.json"
    )
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _optional_iso(value: object) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _require_datetime(value: object, message: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(message)
    return value
