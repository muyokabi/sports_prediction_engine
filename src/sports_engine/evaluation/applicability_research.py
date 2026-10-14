import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from math import ceil, sqrt
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from sports_engine.evaluation.metrics import probability_metrics
from sports_engine.evaluation.uncertainty import MetricUncertainty, per_fixture_loss

_REQUIRED_COLUMNS = {
    "fixture_id",
    "prediction_timestamp",
    "fold",
    "target",
    "home_probability",
    "draw_probability",
    "away_probability",
    "home_effective_training_matches",
    "away_effective_training_matches",
}


def evaluate_applicability_discrimination(
    evaluation_report: Path,
    output_dir: Path,
    *,
    random_seed: int,
    minimum_effective_matches: float = 5.0,
    minimum_group_rows: int = 100,
) -> Path:
    """Audit whether an existing history floor separates lower-risk fixtures.

    This is deliberately retrospective. It cannot validate a new threshold or
    authorize promotion because every source fold has already been evaluated.
    """
    if not np.isfinite(minimum_effective_matches) or minimum_effective_matches < 0:
        raise ValueError("minimum_effective_matches must be finite and non-negative")
    if minimum_group_rows < 1:
        raise ValueError("minimum_group_rows must be positive")
    source, frame, prediction_payload = _load_source(evaluation_report)
    frame = frame.sort("prediction_timestamp", "fixture_id")
    probabilities = frame.select("home_probability", "draw_probability", "away_probability").to_numpy()
    targets = frame["target"].to_numpy()
    _validate_probabilities(probabilities)
    minimum_history = np.minimum(
        frame["home_effective_training_matches"].to_numpy(),
        frame["away_effective_training_matches"].to_numpy(),
    )
    if not np.isfinite(minimum_history).all() or np.any(minimum_history < 0):
        raise ValueError("Prediction artifact contains invalid effective-history evidence")
    accepted = minimum_history >= minimum_effective_matches
    fold_results: list[dict[str, Any]] = []
    for fold in sorted(frame["fold"].unique().to_list()):
        members = frame["fold"].to_numpy() == fold
        fold_results.append(
            _group_evidence(
                frame.filter(pl.col("fold") == fold),
                targets[members],
                probabilities[members],
                accepted[members],
                random_seed=random_seed + int(fold),
                minimum_group_rows=minimum_group_rows,
            )
        )
    all_groups_adequate = all(item["group_sample_adequate"] for item in fold_results)
    stable_log_loss = all(
        item["accepted_minus_rejected"]["log_loss"]["upper"] < 0
        for item in fold_results
        if item["group_sample_adequate"]
    )
    stable_brier = all(
        item["accepted_minus_rejected"]["brier"]["upper"] < 0
        for item in fold_results
        if item["group_sample_adequate"]
    )
    discriminatively_validated = all_groups_adequate and stable_log_loss and stable_brier
    created_at = datetime.now(UTC)
    payload: dict[str, Any] = {
        "experiment": "fixture-applicability-discrimination-audit-v1",
        "created_at": created_at.isoformat(),
        "source_evaluation_report": str(evaluation_report),
        "source_evaluation_sha256": hashlib.sha256(evaluation_report.read_bytes()).hexdigest(),
        "source_prediction_sha256": hashlib.sha256(prediction_payload).hexdigest(),
        "dataset_hash": source.get("dataset_hash"),
        "candidate_version": source.get("candidate_version"),
        "contract": {
            "minimum_effective_matches": minimum_effective_matches,
            "minimum_group_rows_per_fold": minimum_group_rows,
            "acceptance_definition": "minimum(home, away) recency-weighted fitted matches >= threshold",
            "primary_metrics": ["log_loss", "brier"],
            "stability_rule": (
                "each chronological fold must have adequate accepted and rejected samples and the 95% "
                "moving-block-bootstrap upper bound for accepted-minus-rejected log loss and Brier must be below zero"
            ),
            "evidence_use": "RETROSPECTIVE_AUDIT_ONLY",
            "promotion_permitted": False,
        },
        "fold_results": fold_results,
        "aggregate": _group_evidence(
            frame,
            targets,
            probabilities,
            accepted,
            random_seed=random_seed,
            minimum_group_rows=minimum_group_rows,
        ),
        "decision": (
            "RETROSPECTIVE_DISCRIMINATION_SUPPORTED_NOT_PROMOTION_ELIGIBLE"
            if discriminatively_validated
            else "CURRENT_POLICY_NOT_STABLY_DISCRIMINATIVE"
        ),
        "discriminatively_validated": discriminatively_validated,
        "production_ledger_mutation": False,
        "interpretation": (
            "Absolute loss ceilings are not evidence that an applicability threshold discriminates risk. "
            "A prospective later temporal era is required before changing candidate eligibility."
        ),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
    target_dir = output_dir / created_at.strftime("%Y/%m/%d")
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"applicability-discrimination-{str(source.get('dataset_hash'))[:12]}-{digest}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _group_evidence(
    frame: pl.DataFrame,
    targets: np.ndarray,
    probabilities: np.ndarray,
    accepted: np.ndarray,
    *,
    random_seed: int,
    minimum_group_rows: int,
) -> dict[str, Any]:
    accepted_rows = int(accepted.sum())
    rejected_rows = int((~accepted).sum())
    adequate = accepted_rows >= minimum_group_rows and rejected_rows >= minimum_group_rows
    accepted_metrics = probability_metrics(targets[accepted], probabilities[accepted]) if accepted_rows else None
    rejected_metrics = probability_metrics(targets[~accepted], probabilities[~accepted]) if rejected_rows else None
    differences: dict[str, Any] = {}
    if accepted_rows and rejected_rows:
        for metric in ("log_loss", "brier"):
            losses = per_fixture_loss(targets, probabilities, metric)
            differences[metric] = asdict(
                _group_mean_difference(losses, accepted, seed=random_seed)
            )
    return {
        "fold": int(frame["fold"][0]) if frame["fold"].n_unique() == 1 else "ALL",
        "start": str(frame["prediction_timestamp"].min()),
        "end": str(frame["prediction_timestamp"].max()),
        "rows": frame.height,
        "accepted_rows": accepted_rows,
        "rejected_rows": rejected_rows,
        "coverage": accepted_rows / frame.height,
        "group_sample_adequate": adequate,
        "accepted": _metric_subset(accepted_metrics),
        "rejected": _metric_subset(rejected_metrics),
        "accepted_minus_rejected": differences,
    }


def _metric_subset(metrics: dict[str, Any] | None) -> dict[str, Any] | None:
    if metrics is None:
        return None
    return {
        key: metrics[key]
        for key in ("log_loss", "brier", "rps", "expected_calibration_error", "probability_integrity")
    }


def _group_mean_difference(
    losses: np.ndarray,
    accepted: np.ndarray,
    *,
    seed: int,
    samples: int = 2_000,
    confidence: float = 0.95,
) -> MetricUncertainty:
    rows = np.asarray(losses, dtype=float)
    groups = np.asarray(accepted, dtype=bool)
    if rows.ndim != 1 or len(rows) != len(groups) or not groups.any() or groups.all():
        raise ValueError("Group comparison requires aligned accepted and rejected losses")
    width = min(max(1, int(sqrt(len(rows)))), len(rows))
    starts = np.arange(len(rows) - width + 1)
    blocks_needed = ceil(len(rows) / width)
    rng = np.random.default_rng(seed)
    estimates: list[float] = []
    for _ in range(samples):
        selected = rng.choice(starts, size=blocks_needed, replace=True)
        indexes = np.concatenate([np.arange(start, start + width) for start in selected])[: len(rows)]
        sampled_groups = groups[indexes]
        if sampled_groups.any() and not sampled_groups.all():
            sampled_losses = rows[indexes]
            estimates.append(float(sampled_losses[sampled_groups].mean() - sampled_losses[~sampled_groups].mean()))
    if len(estimates) < max(100, samples // 2):
        raise ValueError("Insufficient bootstrap samples retained both applicability groups")
    alpha = (1 - confidence) / 2
    values = np.asarray(estimates)
    return MetricUncertainty(
        estimate=float(rows[groups].mean() - rows[~groups].mean()),
        lower=float(np.quantile(values, alpha)),
        upper=float(np.quantile(values, 1 - alpha)),
        samples=len(estimates),
        method=f"chronological-moving-block-group-bootstrap(block_size={width})",
    )


def _load_source(path: Path) -> tuple[dict[str, Any], pl.DataFrame, bytes]:
    source = json.loads(path.read_text(encoding="utf-8"))
    artifact = source.get("prediction_artifact")
    if not isinstance(artifact, dict) or not artifact.get("path") or not artifact.get("sha256"):
        raise ValueError("Evaluation report has no auditable prediction artifact")
    prediction_path = Path(str(artifact["path"]))
    raw = prediction_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
        raise ValueError("Source prediction artifact digest verification failed")
    frame = pl.read_parquet(prediction_path)
    missing = sorted(_REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"Prediction artifact is missing exact applicability columns: {', '.join(missing)}")
    if frame.height != int(artifact.get("rows", -1)):
        raise ValueError("Prediction artifact row count disagrees with source report")
    return source, frame, raw


def _validate_probabilities(probabilities: np.ndarray) -> None:
    if not np.isfinite(probabilities).all() or np.any(probabilities < 0) or np.any(probabilities > 1):
        raise ValueError("Prediction artifact contains invalid probabilities")
    if not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-8):
        raise ValueError("Prediction artifact probabilities do not sum to one")
