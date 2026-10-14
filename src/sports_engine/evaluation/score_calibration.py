import hashlib
import io
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from scipy.optimize import minimize_scalar

from sports_engine.core.paths import dated_artifact_directory
from sports_engine.evaluation.metrics import binary_probability_metrics, probability_metrics
from sports_engine.evaluation.uncertainty import (
    binary_per_fixture_loss,
    chronological_block_bootstrap,
    paired_metric_difference,
)
from sports_engine.markets.score_distribution import ScoreDistribution
from sports_engine.models.statistical.dixon_coles import DixonColesModel

_REQUIRED_COLUMNS = {
    "fixture_id",
    "prediction_timestamp",
    "fold",
    "target",
    "target_home_goals",
    "target_away_goals",
    "home_probability",
    "draw_probability",
    "away_probability",
    "btts_target",
    "btts_yes_probability",
    "over_2_5_target",
    "over_2_5_probability",
    "home_expected_goals",
    "away_expected_goals",
    "dixon_coles_rho",
    "home_training_matches",
    "away_training_matches",
}


def evaluate_score_intensity_calibration(
    evaluation_report: Path,
    output_dir: Path,
    *,
    random_seed: int,
    scale_bounds: tuple[float, float] = (0.5, 1.5),
    maximum_validation_log_loss_degradation: float = 0.001,
) -> Path:
    """Evaluate one distribution-preserving Dixon-Coles intensity scale.

    Folds before the penultimate fold fit the development scale. The penultimate
    fold is the validation gate. Only a challenger that passes that frozen gate
    is refit on every pre-test fold and evaluated on the final untouched fold.
    The function writes immutable research artifacts and never mutates the
    warehouse or model registry.
    """
    source = json.loads(evaluation_report.read_text(encoding="utf-8"))
    if source.get("model_type") != "dixon-coles":
        raise ValueError("Score-intensity calibration requires a Dixon-Coles evaluation report")
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
    folds = sorted(int(value) for value in frame["fold"].unique().to_list())
    if len(folds) < 4:
        raise ValueError("At least four chronological folds are required for development, validation, and test")
    development_folds = folds[:-2]
    validation_fold = folds[-2]
    test_fold = folds[-1]

    development = frame.filter(pl.col("fold").is_in(development_folds))
    validation = frame.filter(pl.col("fold") == validation_fold)
    development_scale = _fit_intensity_scale(development, scale_bounds)
    validation_evidence, validation_rows = _stage_evidence(
        validation, development_scale, random_seed=random_seed
    )
    boundary_distance = min(
        development_scale - scale_bounds[0], scale_bounds[1] - development_scale
    )
    validation_reasons: list[str] = []
    if boundary_distance <= 0.01:
        validation_reasons.append("OPTIMUM_AT_OR_NEAR_SCALE_BOUNDARY")
    primary_validation = validation_evidence["paired_differences"]["scoreline_log_loss"]
    if float(primary_validation["estimate"]) >= 0:
        validation_reasons.append("VALIDATION_SCORELINE_LOG_LOSS_NOT_IMPROVED")
    for family in ("match_odds", "BTTS", "TOTAL_GOALS_2_5"):
        difference = validation_evidence["paired_differences"][family]["log_loss"]
        if float(difference["estimate"]) > maximum_validation_log_loss_degradation:
            validation_reasons.append(f"VALIDATION_{family}_LOG_LOSS_DEGRADED")

    final_scale: float | None = None
    test_evidence: dict[str, Any] | None = None
    output_rows = validation_rows.with_columns(pl.lit("VALIDATION").alias("experiment_stage"))
    if not validation_reasons:
        pretest = frame.filter(pl.col("fold") != test_fold)
        final_scale = _fit_intensity_scale(pretest, scale_bounds)
        test = frame.filter(pl.col("fold") == test_fold)
        test_evidence, test_rows = _stage_evidence(test, final_scale, random_seed=random_seed)
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
        "experiment": "GLOBAL_DIXON_COLES_INTENSITY_SCALE_V1",
        "created_at": created_at.isoformat(),
        "source_evaluation_report": str(evaluation_report),
        "source_evaluation_sha256": hashlib.sha256(evaluation_report.read_bytes()).hexdigest(),
        "source_prediction_artifact": str(prediction_path),
        "source_prediction_sha256": hashlib.sha256(raw).hexdigest(),
        "dataset_hash": source.get("dataset_hash"),
        "candidate_version": source.get("candidate_version"),
        "contract": {
            "development_folds": development_folds,
            "validation_fold": validation_fold,
            "untouched_test_fold": test_fold,
            "scale_bounds": list(scale_bounds),
            "selection_objective": "mean realized-score negative log probability",
            "validation_primary_rule": "candidate-minus-baseline scoreline log loss < 0",
            "maximum_family_log_loss_degradation": maximum_validation_log_loss_degradation,
            "distribution_constraint": (
                "multiply both Poisson intensities by one scalar; retain fold rho; "
                "renormalize the common score matrix"
            ),
        },
        "development_scale": development_scale,
        "validation": validation_evidence,
        "validation_gate": {"passed": not validation_reasons, "reasons": validation_reasons},
        "final_pretest_scale": final_scale,
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
    path = target_dir / f"score-intensity-calibration-{str(source.get('dataset_hash'))[:12]}-{digest}.json"
    prediction_target = path.with_suffix(".predictions.parquet")
    payload["prediction_artifact"]["path"] = str(prediction_target)
    prediction_target.write_bytes(output_payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _fit_intensity_scale(frame: pl.DataFrame, bounds: tuple[float, float]) -> float:
    if not 0 < bounds[0] < bounds[1]:
        raise ValueError("Intensity scale bounds must be positive and increasing")

    def objective(scale: float) -> float:
        outputs = _score_outputs(frame, scale)
        return float(outputs["scoreline_loss"].mean())

    fitted = minimize_scalar(objective, bounds=bounds, method="bounded", options={"xatol": 1e-8})
    if not fitted.success or not np.isfinite(fitted.fun):
        raise RuntimeError("Score-intensity calibration optimization failed")
    return float(fitted.x)


def _stage_evidence(
    frame: pl.DataFrame, scale: float, *, random_seed: int
) -> tuple[dict[str, Any], pl.DataFrame]:
    baseline = _score_outputs(frame, 1.0)
    candidate = _score_outputs(frame, scale)
    stored = frame.select("home_probability", "draw_probability", "away_probability").to_numpy()
    reproduction_error = float(np.max(np.abs(stored - baseline["match_odds"])))
    stored_btts_error = float(
        np.max(np.abs(frame["btts_yes_probability"].to_numpy() - baseline["BTTS"]))
    )
    stored_totals_error = float(
        np.max(np.abs(frame["over_2_5_probability"].to_numpy() - baseline["TOTAL_GOALS_2_5"]))
    )
    if max(reproduction_error, stored_btts_error, stored_totals_error) > 1e-8:
        raise ValueError("Latent score parameters do not reproduce the persisted baseline probabilities")
    targets = frame["target"].cast(pl.Int64).to_numpy()
    binary_targets = {
        "BTTS": frame["btts_target"].cast(pl.Int64).to_numpy(),
        "TOTAL_GOALS_2_5": frame["over_2_5_target"].cast(pl.Int64).to_numpy(),
    }
    paired: dict[str, Any] = {
        "scoreline_log_loss": asdict(
            chronological_block_bootstrap(
                candidate["scoreline_loss"] - baseline["scoreline_loss"], seed=random_seed
            )
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
    period_start = frame["prediction_timestamp"].min()
    period_end = frame["prediction_timestamp"].max()
    if not isinstance(period_start, datetime) or not isinstance(period_end, datetime):
        raise ValueError("Prediction timestamps must be non-empty datetimes")
    evidence = {
        "rows": frame.height,
        "scale": scale,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
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
        "baseline_reproduction_maximum_error": max(
            reproduction_error, stored_btts_error, stored_totals_error
        ),
        "representation": _representation_evidence(
            frame,
            baseline["scoreline_loss"],
            candidate["scoreline_loss"],
            random_seed=random_seed,
        ),
    }
    rows = frame.select(
        "fixture_id",
        "prediction_timestamp",
        "fold",
        "target_home_goals",
        "target_away_goals",
        "home_training_matches",
        "away_training_matches",
    ).with_columns(
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


def _score_outputs(frame: pl.DataFrame, scale: float | np.ndarray) -> dict[str, np.ndarray]:
    rows = frame.select(
        "home_expected_goals",
        "away_expected_goals",
        "dixon_coles_rho",
        "target_home_goals",
        "target_away_goals",
    ).iter_rows()
    match_odds: list[list[float]] = []
    btts: list[float] = []
    totals: list[float] = []
    scoreline_loss: list[float] = []
    scales = (
        np.asarray(scale, dtype=float)
        if isinstance(scale, np.ndarray)
        else np.full(frame.height, scale, dtype=float)
    )
    if scales.shape != (frame.height,):
        raise ValueError("Score calibration requires one scale per fixture")
    for (home_rate, away_rate, rho, home_goals, away_goals), row_scale in zip(
        rows, scales, strict=True
    ):
        matrix = _scaled_score_matrix(float(home_rate), float(away_rate), float(rho), float(row_scale))
        indices = np.indices(matrix.shape)
        match_odds.append(
            [float(np.tril(matrix, -1).sum()), float(np.trace(matrix)), float(np.triu(matrix, 1).sum())]
        )
        btts.append(float(matrix[(indices[0] > 0) & (indices[1] > 0)].sum()))
        totals.append(float(matrix[(indices[0] + indices[1]) >= 3].sum()))
        if int(home_goals) >= matrix.shape[0] or int(away_goals) >= matrix.shape[1]:
            raise ValueError("Observed score lies outside the dynamically represented score grid")
        scoreline_loss.append(-float(np.log(max(matrix[int(home_goals), int(away_goals)], 1e-15))))
    return {
        "match_odds": np.asarray(match_odds, dtype=float),
        "BTTS": np.asarray(btts, dtype=float),
        "TOTAL_GOALS_2_5": np.asarray(totals, dtype=float),
        "scoreline_loss": np.asarray(scoreline_loss, dtype=float),
    }


def _scaled_score_matrix(home_rate: float, away_rate: float, rho: float, scale: float) -> np.ndarray:
    if not np.isfinite([home_rate, away_rate, rho, scale]).all() or min(home_rate, away_rate, scale) <= 0:
        raise ValueError("Score calibration inputs must be finite with positive rates and scale")
    scaled_home = home_rate * scale
    scaled_away = away_rate * scale
    matrix = ScoreDistribution.poisson(scaled_home, scaled_away).probabilities.copy()
    for home_goals, away_goals in ((0, 0), (0, 1), (1, 0), (1, 1)):
        adjustment = DixonColesModel._tau(
            home_goals, away_goals, scaled_home, scaled_away, rho
        )
        if adjustment <= 0:
            raise ValueError("Scaled Dixon-Coles correction produced non-positive probability mass")
        matrix[home_goals, away_goals] *= adjustment
    total = float(matrix.sum())
    if not np.isfinite(total) or total <= 0:
        raise ValueError("Scaled score distribution has invalid probability mass")
    return matrix / total


def _representation_evidence(
    frame: pl.DataFrame,
    baseline_scoreline_loss: np.ndarray,
    candidate_scoreline_loss: np.ndarray,
    *,
    random_seed: int,
) -> dict[str, Any]:
    home = frame["home_training_matches"].cast(pl.Int64).to_numpy()
    away = frame["away_training_matches"].cast(pl.Int64).to_numpy()
    masks = {
        "both_teams_seen": (home > 0) & (away > 0),
        "one_team_unseen": (home == 0) ^ (away == 0),
        "both_teams_unseen": (home == 0) & (away == 0),
        "either_team_under_5_matches": (home < 5) | (away < 5),
    }
    difference = candidate_scoreline_loss - baseline_scoreline_loss
    return {
        name: {
            "rows": int(mask.sum()),
            "scoreline_log_loss_difference": (
                asdict(chronological_block_bootstrap(difference[mask], seed=random_seed))
                if mask.any()
                else None
            ),
        }
        for name, mask in masks.items()
    }
