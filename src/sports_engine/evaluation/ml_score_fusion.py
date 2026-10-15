"""Research-only chronological evaluation of ML-assisted score distributions."""

import hashlib
import io
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from sports_engine.evaluation.comparison import load_evaluation_report
from sports_engine.evaluation.metrics import binary_probability_metrics, probability_metrics
from sports_engine.evaluation.uncertainty import (
    binary_per_fixture_loss,
    chronological_block_bootstrap,
    paired_metric_difference,
)
from sports_engine.markets.score_distribution import ScoreDistribution
from sports_engine.models.ensemble.score_projection import (
    convex_probability_blend,
    project_match_odds_marginals,
    score_matrix_binary_markets,
    score_matrix_match_odds,
)

FUSION_POLICY_VERSION = "outcome-marginal-projection-v1"
DEFAULT_FUSION_WEIGHTS = tuple(value / 20 for value in range(21))
DEFAULT_FAMILY_LOG_LOSS_NONINFERIORITY_MARGIN = 0.001
SCORE_REQUIRED_COLUMNS = {
    "home_expected_goals",
    "away_expected_goals",
    "dixon_coles_rho",
    "btts_target",
    "btts_yes_probability",
    "over_2_5_target",
    "over_2_5_probability",
}


def evaluate_ml_score_fusion(
    score_report: Path,
    ml_report: Path,
    output_dir: Path,
    *,
    random_seed: int,
    weights: tuple[float, ...] = DEFAULT_FUSION_WEIGHTS,
    family_log_loss_noninferiority_margin: float = DEFAULT_FAMILY_LOG_LOSS_NONINFERIORITY_MARGIN,
) -> Path:
    """Select a fusion weight before the final fold and evaluate it on that fold.

    This experiment never changes a model role or serving path. The final fold
    is a chronological confirmation set within the supplied immutable
    out-of-fold artifacts. Reusing previously inspected artifacts is explicitly
    classified as retrospective development evidence, not promotion evidence.
    """
    score = load_evaluation_report(score_report)
    ml = load_evaluation_report(ml_report)
    if score["payload"].get("dataset_hash") != ml["payload"].get("dataset_hash"):
        raise ValueError("Score and ML reports must use the same dataset hash")
    if score["payload"].get("model_type") not in {"poisson", "dixon-coles"}:
        raise ValueError("Score report must be Poisson or Dixon-Coles")
    if ml["payload"].get("model_type") not in {"logistic", "catboost", "lightgbm"}:
        raise ValueError("ML report must be logistic, CatBoost, or LightGBM")

    score_frame = score["predictions"].sort("prediction_timestamp", "fixture_id")
    ml_frame = ml["predictions"].sort("prediction_timestamp", "fixture_id")
    missing = sorted(SCORE_REQUIRED_COLUMNS - set(score_frame.columns))
    if missing:
        raise ValueError(f"Score prediction artifact is missing columns: {', '.join(missing)}")
    _validate_alignment(score_frame, ml_frame)
    folds = sorted(score_frame["fold"].unique().to_list())
    if len(folds) < 2:
        raise ValueError("Fusion evaluation requires at least two chronological folds")
    selection_folds = folds[:-1]
    confirmation_fold = folds[-1]

    score_probabilities = _probabilities(score_frame)
    ml_probabilities = _probabilities(ml_frame)
    targets = score_frame["target"].to_numpy()
    matrices = _rebuild_score_matrices(score_frame, score["payload"])
    _verify_reconstruction(score_frame, matrices, score_probabilities)
    selection_mask = score_frame["fold"].is_in(selection_folds).to_numpy()
    confirmation_mask = (score_frame["fold"] == confirmation_fold).to_numpy()
    selected_weight, selection_candidates = _select_weight(
        matrices,
        score_probabilities,
        ml_probabilities,
        targets,
        score_frame,
        selection_mask,
        weights,
        family_log_loss_noninferiority_margin,
    )
    fused_probabilities = convex_probability_blend(
        score_probabilities, ml_probabilities, ml_weight=selected_weight
    )
    fused_matrices = [
        project_match_odds_marginals(matrix, probabilities)
        for matrix, probabilities in zip(matrices, fused_probabilities, strict=True)
    ]
    fused_btts, fused_totals = _binary_outputs(fused_matrices)

    validation = _period_metrics(
        targets,
        score_probabilities,
        ml_probabilities,
        fused_probabilities,
        score_frame,
        fused_btts,
        fused_totals,
        selection_mask,
    )
    confirmation = _period_metrics(
        targets,
        score_probabilities,
        ml_probabilities,
        fused_probabilities,
        score_frame,
        fused_btts,
        fused_totals,
        confirmation_mask,
    )
    confirmation["paired_fusion_minus_score"] = {
        metric: asdict(
            paired_metric_difference(
                targets[confirmation_mask],
                fused_probabilities[confirmation_mask],
                score_probabilities[confirmation_mask],
                metric,
                seed=random_seed,
            )
        )
        for metric in ("log_loss", "brier", "rps")
    }
    for family, target_column, fused_values, baseline_column in (
        ("BTTS", "btts_target", fused_btts, "btts_yes_probability"),
        ("TOTAL_GOALS_2_5", "over_2_5_target", fused_totals, "over_2_5_probability"),
    ):
        confirmation["families"][family]["paired_fusion_minus_score"] = {
            metric: asdict(
                chronological_block_bootstrap(
                    binary_per_fixture_loss(
                        score_frame[target_column].to_numpy()[confirmation_mask],
                        fused_values[confirmation_mask],
                        metric,
                    )
                    - binary_per_fixture_loss(
                        score_frame[target_column].to_numpy()[confirmation_mask],
                        score_frame[baseline_column].to_numpy()[confirmation_mask],
                        metric,
                    ),
                    seed=random_seed,
                )
            )
            for metric in ("log_loss", "brier")
        }
    match_odds_interval = confirmation["paired_fusion_minus_score"]["log_loss"]
    family_intervals = {
        family: confirmation["families"][family]["paired_fusion_minus_score"]["log_loss"]
        for family in ("BTTS", "TOTAL_GOALS_2_5")
    }
    confirmation_passed = (
        float(match_odds_interval["upper"]) < 0
        and all(
            float(interval["upper"]) <= family_log_loss_noninferiority_margin
            for interval in family_intervals.values()
        )
    )
    confirmation["research_gate"] = {
        "passed": confirmation_passed,
        "match_odds_requires_strict_improvement": True,
        "family_log_loss_noninferiority_margin": family_log_loss_noninferiority_margin,
        "rule": (
            "MATCH_ODDS paired log-loss upper bound must be below zero and each score-family "
            "paired upper bound must not exceed the predeclared non-inferiority margin."
        ),
    }

    result_frame = score_frame.select("fixture_id", "prediction_timestamp", "fold", "target").with_columns(
        pl.Series("score_home_probability", score_probabilities[:, 0]),
        pl.Series("score_draw_probability", score_probabilities[:, 1]),
        pl.Series("score_away_probability", score_probabilities[:, 2]),
        pl.Series("ml_home_probability", ml_probabilities[:, 0]),
        pl.Series("ml_draw_probability", ml_probabilities[:, 1]),
        pl.Series("ml_away_probability", ml_probabilities[:, 2]),
        pl.Series("fused_home_probability", fused_probabilities[:, 0]),
        pl.Series("fused_draw_probability", fused_probabilities[:, 1]),
        pl.Series("fused_away_probability", fused_probabilities[:, 2]),
        pl.Series("fused_btts_yes_probability", fused_btts),
        pl.Series("fused_over_2_5_probability", fused_totals),
        pl.when(pl.col("fold") == confirmation_fold)
        .then(pl.lit("CONFIRMATION"))
        .otherwise(pl.lit("WEIGHT_SELECTION"))
        .alias("experiment_partition"),
    )
    buffer = io.BytesIO()
    result_frame.write_parquet(buffer, compression="zstd")
    prediction_payload = buffer.getvalue()
    created_at = datetime.now(UTC)
    payload: dict[str, Any] = {
        "experiment": "ML_SCORE_FUSION",
        "policy_version": FUSION_POLICY_VERSION,
        "created_at": created_at.isoformat(),
        "dataset_hash": score["payload"]["dataset_hash"],
        "score_report": str(score_report),
        "score_model_type": score["payload"]["model_type"],
        "score_candidate_version": score["payload"]["candidate_version"],
        "ml_report": str(ml_report),
        "ml_model_type": ml["payload"]["model_type"],
        "ml_candidate_version": ml["payload"]["candidate_version"],
        "selection_folds": selection_folds,
        "confirmation_fold": confirmation_fold,
        "weight_grid": list(weights),
        "family_log_loss_noninferiority_margin": family_log_loss_noninferiority_margin,
        "selected_ml_weight": selected_weight,
        "selection_candidates": selection_candidates,
        "selection_rule": (
            "Minimize selection-period 1X2 log loss subject to BTTS and over-2.5 log loss "
            "remaining within the predeclared non-inferiority margin; ties prefer less ML weight."
        ),
        "validation_metrics": validation,
        "confirmation_metrics": confirmation,
        "experiment_verdict": "PASSED_RESEARCH_GATE" if confirmation_passed else "FAILED_RESEARCH_GATE",
        "serving_changed": False,
        "promotion_eligible": False,
        "promotion_blockers": [
            "RETROSPECTIVE_DEVELOPMENT_ARTIFACTS_ALREADY_INSPECTED",
            "REQUIRES_GENUINELY_LATER_PREDECLARED_TEMPORAL_CONFIRMATION",
            "REQUIRES_MARKET_BASELINE_POLICY_EVIDENCE",
        ],
        "interpretation": (
            "The ML classifier adjusts only the home/draw/away regional mass of the score matrix. "
            "Within-outcome scoreline proportions remain those of the score model, so every market "
            "is still derived from one normalized score distribution."
        ),
        "prediction_artifact": {
            "rows": result_frame.height,
            "sha256": hashlib.sha256(prediction_payload).hexdigest(),
        },
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"ml-score-fusion-{str(payload['dataset_hash'])[:12]}-{digest}.json"
    prediction_path = path.with_suffix(".predictions.parquet")
    payload["prediction_artifact"]["path"] = str(prediction_path)
    prediction_path.write_bytes(prediction_payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _select_weight(
    matrices: Sequence[np.ndarray],
    score_probabilities: np.ndarray,
    ml_probabilities: np.ndarray,
    targets: np.ndarray,
    frame: pl.DataFrame,
    mask: np.ndarray,
    weights: tuple[float, ...],
    family_log_loss_noninferiority_margin: float,
) -> tuple[float, list[dict[str, Any]]]:
    if not weights or any(not 0.0 <= value <= 1.0 for value in weights):
        raise ValueError("Fusion weight grid must contain values between zero and one")
    if family_log_loss_noninferiority_margin < 0:
        raise ValueError("Family log-loss non-inferiority margin cannot be negative")
    baseline_btts = frame["btts_yes_probability"].to_numpy()[mask]
    baseline_totals = frame["over_2_5_probability"].to_numpy()[mask]
    btts_targets = frame["btts_target"].to_numpy()[mask]
    totals_targets = frame["over_2_5_target"].to_numpy()[mask]
    baseline_btts_loss = float(binary_probability_metrics(btts_targets, baseline_btts)["log_loss"])
    baseline_totals_loss = float(binary_probability_metrics(totals_targets, baseline_totals)["log_loss"])
    candidates: list[dict[str, Any]] = []
    for weight in sorted(set(weights)):
        blended = convex_probability_blend(score_probabilities, ml_probabilities, ml_weight=weight)
        selected_matrices = [matrix for matrix, selected in zip(matrices, mask, strict=True) if selected]
        projected = [
            project_match_odds_marginals(matrix, probability)
            for matrix, probability in zip(selected_matrices, blended[mask], strict=True)
        ]
        btts, totals = _binary_outputs(projected)
        btts_loss = float(binary_probability_metrics(btts_targets, btts)["log_loss"])
        totals_loss = float(binary_probability_metrics(totals_targets, totals)["log_loss"])
        family_safe = (
            btts_loss <= baseline_btts_loss + family_log_loss_noninferiority_margin
            and totals_loss <= baseline_totals_loss + family_log_loss_noninferiority_margin
        )
        candidates.append(
            {
                "ml_weight": weight,
                "match_odds_log_loss": float(probability_metrics(targets[mask], blended[mask])["log_loss"]),
                "btts_log_loss": btts_loss,
                "over_2_5_log_loss": totals_loss,
                "btts_log_loss_difference": btts_loss - baseline_btts_loss,
                "over_2_5_log_loss_difference": totals_loss - baseline_totals_loss,
                "family_safe": family_safe,
            }
        )
    eligible = [candidate for candidate in candidates if candidate["family_safe"]]
    if not eligible:
        raise RuntimeError("No fusion weight preserves score-family validation loss")
    best_loss = min(float(candidate["match_odds_log_loss"]) for candidate in eligible)
    statistically_tied = [
        candidate for candidate in eligible if float(candidate["match_odds_log_loss"]) <= best_loss + 1e-12
    ]
    selected = min(statistically_tied, key=lambda item: item["ml_weight"])
    return float(selected["ml_weight"]), candidates


def _period_metrics(
    targets: np.ndarray,
    score_probabilities: np.ndarray,
    ml_probabilities: np.ndarray,
    fused_probabilities: np.ndarray,
    frame: pl.DataFrame,
    fused_btts: np.ndarray,
    fused_totals: np.ndarray,
    mask: np.ndarray,
) -> dict[str, Any]:
    return {
        "rows": int(mask.sum()),
        "score": probability_metrics(targets[mask], score_probabilities[mask]),
        "ml": probability_metrics(targets[mask], ml_probabilities[mask]),
        "fusion": probability_metrics(targets[mask], fused_probabilities[mask]),
        "families": {
            "BTTS": {
                "score": binary_probability_metrics(
                    frame["btts_target"].to_numpy()[mask], frame["btts_yes_probability"].to_numpy()[mask]
                ),
                "fusion": binary_probability_metrics(frame["btts_target"].to_numpy()[mask], fused_btts[mask]),
            },
            "TOTAL_GOALS_2_5": {
                "score": binary_probability_metrics(
                    frame["over_2_5_target"].to_numpy()[mask],
                    frame["over_2_5_probability"].to_numpy()[mask],
                ),
                "fusion": binary_probability_metrics(
                    frame["over_2_5_target"].to_numpy()[mask], fused_totals[mask]
                ),
            },
        },
    }


def _rebuild_score_matrices(frame: pl.DataFrame, payload: dict[str, Any]) -> list[np.ndarray]:
    del payload
    matrices: list[np.ndarray] = []
    for home_rate, away_rate, rho in frame.select(
        "home_expected_goals", "away_expected_goals", "dixon_coles_rho"
    ).iter_rows():
        matrix = ScoreDistribution.poisson(float(home_rate), float(away_rate)).probabilities.copy()
        matrix[0, 0] *= 1 - float(home_rate) * float(away_rate) * float(rho)
        matrix[0, 1] *= 1 + float(home_rate) * float(rho)
        matrix[1, 0] *= 1 + float(away_rate) * float(rho)
        matrix[1, 1] *= 1 - float(rho)
        matrix = np.clip(matrix, 0.0, None)
        matrices.append(matrix / matrix.sum())
    return matrices


def _verify_reconstruction(
    frame: pl.DataFrame, matrices: Sequence[np.ndarray], probabilities: np.ndarray
) -> None:
    reconstructed = np.asarray([score_matrix_match_odds(matrix) for matrix in matrices])
    if not np.allclose(reconstructed, probabilities, atol=1e-8):
        raise ValueError("Persisted match odds cannot be reproduced from score parameters")
    btts, totals = _binary_outputs(matrices)
    if not np.allclose(btts, frame["btts_yes_probability"].to_numpy(), atol=1e-8):
        raise ValueError("Persisted BTTS probabilities cannot be reproduced from score parameters")
    if not np.allclose(totals, frame["over_2_5_probability"].to_numpy(), atol=1e-8):
        raise ValueError("Persisted total-goals probabilities cannot be reproduced from score parameters")


def _binary_outputs(matrices: Sequence[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    rows = [score_matrix_binary_markets(matrix) for matrix in matrices]
    return np.asarray([row[0] for row in rows]), np.asarray([row[1] for row in rows])


def _validate_alignment(score: pl.DataFrame, ml: pl.DataFrame) -> None:
    if score.height != ml.height:
        raise ValueError("Score and ML reports do not contain the same number of predictions")
    for column in ("fixture_id", "prediction_timestamp", "fold", "target"):
        if not score[column].equals(ml[column]):
            raise ValueError(f"Score and ML reports are not aligned on {column}")


def _probabilities(frame: pl.DataFrame) -> np.ndarray:
    values = frame.select("home_probability", "draw_probability", "away_probability").to_numpy()
    if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise ValueError("Prediction artifact contains invalid probabilities")
    if not np.allclose(values.sum(axis=1), 1.0, atol=1e-8):
        raise ValueError("Prediction artifact probabilities do not sum to one")
    return values
