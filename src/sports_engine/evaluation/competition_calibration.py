import hashlib
import io
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import polars as pl

from sports_engine.core.paths import dated_artifact_directory
from sports_engine.evaluation.metrics import binary_probability_metrics, probability_metrics
from sports_engine.evaluation.score_calibration import _REQUIRED_COLUMNS, _score_outputs
from sports_engine.evaluation.uncertainty import (
    binary_per_fixture_loss,
    chronological_block_bootstrap,
    paired_metric_difference,
)


def evaluate_competition_intensity_calibration(
    connection: duckdb.DuckDBPyConnection,
    evaluation_report: Path,
    output_dir: Path,
    *,
    random_seed: int,
    prior_exposure_grid: tuple[float, ...] = (25.0, 100.0, 400.0),
    minimum_competition_rows: int = 30,
    maximum_validation_log_loss_degradation: float = 0.001,
) -> Path:
    """Evaluate a shrunk competition scoring-rate correction chronologically.

    Fold one estimates candidate competition rates, fold two selects the frozen
    shrinkage grid, and fold three is the validation gate. The final fold is
    scored only after the paired validation interval and family safeguards pass.
    This research path writes immutable artifacts and never changes the ledger.
    """
    if not prior_exposure_grid or any(value <= 0 for value in prior_exposure_grid):
        raise ValueError("Prior exposures must be a non-empty set of positive values")
    if minimum_competition_rows < 1:
        raise ValueError("Minimum competition rows must be positive")

    source, frame, raw = _load_source(evaluation_report)
    frame, mapping_digest = _attach_competitions(connection, frame)
    folds = sorted(int(value) for value in frame["fold"].unique().to_list())
    if len(folds) < 4:
        raise ValueError("At least four chronological folds are required")
    specification_fold = folds[0]
    selection_fold = folds[1]
    validation_fold = folds[-2]
    test_fold = folds[-1]
    if len({specification_fold, selection_fold, validation_fold, test_fold}) != 4:
        raise ValueError("Competition calibration requires four distinct chronological stages")

    specification = frame.filter(pl.col("fold") == specification_fold)
    selection = frame.filter(pl.col("fold") == selection_fold)
    sensitivity: list[dict[str, Any]] = []
    for exposure in prior_exposure_grid:
        scales, fit_evidence = _fit_competition_scales(
            specification,
            prior_exposure=exposure,
            minimum_rows=minimum_competition_rows,
        )
        scale_vector, states = _scale_vector(selection, scales)
        candidate = _score_outputs(selection, scale_vector)
        sensitivity.append(
            {
                "prior_exposure": exposure,
                "selection_scoreline_log_loss": float(candidate["scoreline_loss"].mean()),
                "adjusted_rows": int(np.sum(states == "ESTIMATED_COMPETITION_SCALE")),
                "fallback_rows": int(np.sum(states != "ESTIMATED_COMPETITION_SCALE")),
                "fit": fit_evidence,
            }
        )
    selected = min(
        sensitivity,
        key=lambda item: (float(item["selection_scoreline_log_loss"]), float(item["prior_exposure"])),
    )
    selected_exposure = float(selected["prior_exposure"])

    development = frame.filter(pl.col("fold").is_in([specification_fold, selection_fold]))
    development_scales, development_fit = _fit_competition_scales(
        development,
        prior_exposure=selected_exposure,
        minimum_rows=minimum_competition_rows,
    )
    validation = frame.filter(pl.col("fold") == validation_fold)
    validation_evidence, validation_rows = _stage_evidence(
        validation,
        development_scales,
        random_seed=random_seed,
    )
    validation_reasons: list[str] = []
    primary = validation_evidence["paired_differences"]["scoreline_log_loss"]
    if float(primary["upper"]) >= 0:
        validation_reasons.append("VALIDATION_SCORELINE_INTERVAL_NOT_STRICTLY_BETTER")
    for family in ("match_odds", "BTTS", "TOTAL_GOALS_2_5"):
        difference = validation_evidence["paired_differences"][family]["log_loss"]
        if float(difference["estimate"]) > maximum_validation_log_loss_degradation:
            validation_reasons.append(f"VALIDATION_{family}_LOG_LOSS_DEGRADED")
    if not development_scales:
        validation_reasons.append("NO_COMPETITION_ELIGIBLE_FOR_ESTIMATED_SCALE")

    final_fit: dict[str, Any] | None = None
    test_evidence: dict[str, Any] | None = None
    output_rows = validation_rows.with_columns(pl.lit("VALIDATION").alias("experiment_stage"))
    if not validation_reasons:
        pretest = frame.filter(pl.col("fold") != test_fold)
        final_scales, final_fit = _fit_competition_scales(
            pretest,
            prior_exposure=selected_exposure,
            minimum_rows=minimum_competition_rows,
        )
        test = frame.filter(pl.col("fold") == test_fold)
        test_evidence, test_rows = _stage_evidence(test, final_scales, random_seed=random_seed)
        output_rows = pl.concat(
            [
                output_rows,
                test_rows.with_columns(pl.lit("UNTOUCHED_TEST").alias("experiment_stage")),
            ],
            how="vertical",
        )

    created_at = datetime.now(UTC)
    output_buffer = io.BytesIO()
    output_rows.write_parquet(output_buffer, compression="zstd")
    output_payload = output_buffer.getvalue()
    payload: dict[str, Any] = {
        "experiment": "PARTIALLY_POOLED_COMPETITION_INTENSITY_V1",
        "created_at": created_at.isoformat(),
        "source_evaluation_report": str(evaluation_report),
        "source_evaluation_sha256": hashlib.sha256(evaluation_report.read_bytes()).hexdigest(),
        "source_prediction_artifact": str(source["prediction_artifact"]["path"]),
        "source_prediction_sha256": hashlib.sha256(raw).hexdigest(),
        "fixture_competition_mapping_sha256": mapping_digest,
        "dataset_hash": source.get("dataset_hash"),
        "candidate_version": source.get("candidate_version"),
        "contract": {
            "specification_fold": specification_fold,
            "selection_fold": selection_fold,
            "validation_fold": validation_fold,
            "untouched_test_fold": test_fold,
            "prior_exposure_grid": list(prior_exposure_grid),
            "minimum_competition_rows": minimum_competition_rows,
            "selection_objective": "mean realized-score negative log probability",
            "validation_primary_rule": (
                "candidate-minus-baseline scoreline log-loss 95% block-bootstrap upper bound < 0"
            ),
            "maximum_family_log_loss_degradation": maximum_validation_log_loss_degradation,
            "sparse_or_unseen_policy": "scale 1.0",
            "distribution_constraint": (
                "multiply both Poisson intensities by the shrunk competition scale; "
                "retain fold rho; renormalize the common score matrix"
            ),
        },
        "selection_sensitivity": sensitivity,
        "selected_prior_exposure": selected_exposure,
        "development_fit": development_fit,
        "validation": validation_evidence,
        "validation_gate": {"passed": not validation_reasons, "reasons": validation_reasons},
        "final_pretest_fit": final_fit,
        "untouched_test": test_evidence,
        "decision": "TESTED_CHALLENGER" if test_evidence is not None else "REJECTED_ON_VALIDATION",
        "prediction_artifact": {
            "rows": output_rows.height,
            "sha256": hashlib.sha256(output_payload).hexdigest(),
        },
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
    target_dir = dated_artifact_directory(output_dir, created_at)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / (f"competition-intensity-calibration-{str(source.get('dataset_hash'))[:12]}-{digest}.json")
    prediction_target = path.with_suffix(".predictions.parquet")
    payload["prediction_artifact"]["path"] = str(prediction_target)
    prediction_target.write_bytes(output_payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _load_source(evaluation_report: Path) -> tuple[dict[str, Any], pl.DataFrame, bytes]:
    source = json.loads(evaluation_report.read_text(encoding="utf-8"))
    if source.get("model_type") != "dixon-coles":
        raise ValueError("Competition calibration requires a Dixon-Coles evaluation report")
    artifact = source.get("prediction_artifact")
    if not isinstance(artifact, dict):
        raise ValueError("Evaluation report has no prediction artifact")
    prediction_path = Path(str(artifact.get("path")))
    raw = prediction_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact.get("sha256"):
        raise ValueError("Evaluation prediction artifact digest does not match its report")
    frame = pl.read_parquet(io.BytesIO(raw)).sort("prediction_timestamp")
    missing = sorted(_REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"Evaluation artifact lacks score-calibration lineage: {', '.join(missing)}")
    return source, frame, raw


def _attach_competitions(connection: duckdb.DuckDBPyConnection, frame: pl.DataFrame) -> tuple[pl.DataFrame, str]:
    fixture_ids = frame.select("fixture_id").unique().sort("fixture_id")
    relation_name = "_competition_calibration_fixture_ids"
    connection.register(relation_name, fixture_ids)
    try:
        mapping = connection.execute(
            f"SELECT ids.fixture_id, CAST(c.competition_id AS VARCHAR) AS competition_id, "
            f"c.name AS competition_name FROM {relation_name} ids "
            "JOIN fixtures_current f ON CAST(f.fixture_id AS VARCHAR)=ids.fixture_id "
            "JOIN competition_seasons cs USING (competition_season_id) "
            "JOIN competitions c USING (competition_id) ORDER BY ids.fixture_id"
        ).pl()
    finally:
        connection.unregister(relation_name)
    if mapping.height != fixture_ids.height or mapping["competition_id"].null_count():
        raise ValueError("Every evaluation fixture must have one verified competition mapping")
    mapping_payload = json.dumps(mapping.to_dicts(), sort_keys=True, ensure_ascii=False).encode("utf-8")
    joined = frame.join(mapping, on="fixture_id", how="left", validate="m:1")
    if joined["competition_id"].null_count():
        raise ValueError("Competition mapping join produced unknown fixtures")
    return joined, hashlib.sha256(mapping_payload).hexdigest()


def _fit_competition_scales(
    frame: pl.DataFrame,
    *,
    prior_exposure: float,
    minimum_rows: int,
) -> tuple[dict[str, float], dict[str, Any]]:
    grouped = (
        frame.with_columns(
            (pl.col("target_home_goals") + pl.col("target_away_goals")).alias("observed_goals"),
            (pl.col("home_expected_goals") + pl.col("away_expected_goals")).alias("expected_goals"),
        )
        .group_by("competition_id", "competition_name")
        .agg(
            pl.len().alias("rows"),
            pl.col("observed_goals").sum(),
            pl.col("expected_goals").sum(),
        )
        .sort("competition_id")
    )
    scales: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    for item in grouped.iter_rows(named=True):
        eligible = int(item["rows"]) >= minimum_rows and float(item["expected_goals"]) > 0
        scale = (
            (float(item["observed_goals"]) + prior_exposure) / (float(item["expected_goals"]) + prior_exposure)
            if eligible
            else 1.0
        )
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("Competition intensity fitting produced an invalid scale")
        if eligible:
            scales[str(item["competition_id"])] = float(scale)
        rows.append({**item, "eligible": eligible, "scale": float(scale)})
    return scales, {
        "prior_exposure": prior_exposure,
        "minimum_rows": minimum_rows,
        "competitions_seen": grouped.height,
        "competitions_estimated": len(scales),
        "competitions": rows,
    }


def _scale_vector(frame: pl.DataFrame, scales: dict[str, float]) -> tuple[np.ndarray, np.ndarray]:
    competition_ids = frame["competition_id"].cast(pl.String).to_list()
    values = np.asarray([scales.get(value, 1.0) for value in competition_ids], dtype=float)
    states = np.asarray(
        ["ESTIMATED_COMPETITION_SCALE" if value in scales else "SPARSE_OR_UNSEEN_FALLBACK" for value in competition_ids]
    )
    return values, states


def _stage_evidence(
    frame: pl.DataFrame,
    scales: dict[str, float],
    *,
    random_seed: int,
) -> tuple[dict[str, Any], pl.DataFrame]:
    scale_vector, states = _scale_vector(frame, scales)
    baseline = _score_outputs(frame, 1.0)
    candidate = _score_outputs(frame, scale_vector)
    stored = frame.select("home_probability", "draw_probability", "away_probability").to_numpy()
    reproduction_error = float(np.max(np.abs(stored - baseline["match_odds"])))
    stored_btts_error = float(np.max(np.abs(frame["btts_yes_probability"].to_numpy() - baseline["BTTS"])))
    stored_totals_error = float(np.max(np.abs(frame["over_2_5_probability"].to_numpy() - baseline["TOTAL_GOALS_2_5"])))
    if max(reproduction_error, stored_btts_error, stored_totals_error) > 1e-8:
        raise ValueError("Latent score parameters do not reproduce the persisted baseline probabilities")
    targets = frame["target"].cast(pl.Int64).to_numpy()
    binary_targets = {
        "BTTS": frame["btts_target"].cast(pl.Int64).to_numpy(),
        "TOTAL_GOALS_2_5": frame["over_2_5_target"].cast(pl.Int64).to_numpy(),
    }
    paired: dict[str, Any] = {
        "scoreline_log_loss": asdict(
            chronological_block_bootstrap(candidate["scoreline_loss"] - baseline["scoreline_loss"], seed=random_seed)
        ),
        "match_odds": {
            metric: asdict(
                paired_metric_difference(
                    targets,
                    candidate["match_odds"],
                    baseline["match_odds"],
                    metric,
                    seed=random_seed,
                )
            )
            for metric in ("log_loss", "brier", "rps")
        },
    }
    for family, observed in binary_targets.items():
        paired[family] = {
            metric: asdict(
                chronological_block_bootstrap(
                    binary_per_fixture_loss(observed, candidate[family], metric)
                    - binary_per_fixture_loss(observed, baseline[family], metric),
                    seed=random_seed,
                )
            )
            for metric in ("log_loss", "brier")
        }
    competition_evidence: dict[str, Any] = {}
    difference = candidate["scoreline_loss"] - baseline["scoreline_loss"]
    competition_ids = frame["competition_id"].cast(pl.String).to_numpy()
    for competition_id in sorted(set(competition_ids)):
        mask = competition_ids == competition_id
        if int(mask.sum()) < 30:
            continue
        competition_evidence[str(competition_id)] = {
            "competition_name": str(frame.filter(pl.col("competition_id") == competition_id)["competition_name"][0]),
            "rows": int(mask.sum()),
            "scale": float(scale_vector[mask][0]),
            "state": str(states[mask][0]),
            "scoreline_log_loss_difference": asdict(chronological_block_bootstrap(difference[mask], seed=random_seed)),
        }
    period_start = frame["prediction_timestamp"].min()
    period_end = frame["prediction_timestamp"].max()
    if not isinstance(period_start, datetime) or not isinstance(period_end, datetime):
        raise ValueError("Prediction timestamps must be non-empty datetimes")
    evidence = {
        "rows": frame.height,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "adjusted_rows": int(np.sum(states == "ESTIMATED_COMPETITION_SCALE")),
        "fallback_rows": int(np.sum(states != "ESTIMATED_COMPETITION_SCALE")),
        "estimated_competitions": len(scales),
        "baseline": {
            "scoreline_log_loss": float(baseline["scoreline_loss"].mean()),
            "match_odds": probability_metrics(targets, baseline["match_odds"]),
            "BTTS": binary_probability_metrics(binary_targets["BTTS"], baseline["BTTS"]),
            "TOTAL_GOALS_2_5": binary_probability_metrics(
                binary_targets["TOTAL_GOALS_2_5"], baseline["TOTAL_GOALS_2_5"]
            ),
        },
        "candidate": {
            "scoreline_log_loss": float(candidate["scoreline_loss"].mean()),
            "match_odds": probability_metrics(targets, candidate["match_odds"]),
            "BTTS": binary_probability_metrics(binary_targets["BTTS"], candidate["BTTS"]),
            "TOTAL_GOALS_2_5": binary_probability_metrics(
                binary_targets["TOTAL_GOALS_2_5"], candidate["TOTAL_GOALS_2_5"]
            ),
        },
        "paired_differences": paired,
        "baseline_reproduction_maximum_error": max(reproduction_error, stored_btts_error, stored_totals_error),
        "by_competition": competition_evidence,
    }
    rows = frame.select(
        "fixture_id",
        "competition_id",
        "competition_name",
        "prediction_timestamp",
        "fold",
        "target_home_goals",
        "target_away_goals",
        "home_training_matches",
        "away_training_matches",
    ).with_columns(
        pl.Series("competition_scale", scale_vector),
        pl.Series("competition_scale_state", states),
        pl.Series("baseline_scoreline_loss", baseline["scoreline_loss"]),
        pl.Series("candidate_scoreline_loss", candidate["scoreline_loss"]),
        pl.Series("baseline_home_probability", baseline["match_odds"][:, 0]),
        pl.Series("candidate_home_probability", candidate["match_odds"][:, 0]),
        pl.Series("baseline_draw_probability", baseline["match_odds"][:, 1]),
        pl.Series("candidate_draw_probability", candidate["match_odds"][:, 1]),
        pl.Series("baseline_away_probability", baseline["match_odds"][:, 2]),
        pl.Series("candidate_away_probability", candidate["match_odds"][:, 2]),
        pl.Series("baseline_btts_probability", baseline["BTTS"]),
        pl.Series("candidate_btts_probability", candidate["BTTS"]),
        pl.Series("baseline_over_2_5_probability", baseline["TOTAL_GOALS_2_5"]),
        pl.Series("candidate_over_2_5_probability", candidate["TOTAL_GOALS_2_5"]),
    )
    return evidence, rows
