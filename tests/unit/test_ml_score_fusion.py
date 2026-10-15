import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import poisson

from sports_engine.evaluation.ml_score_fusion import evaluate_ml_score_fusion
from sports_engine.markets.score_distribution import ScoreDistribution
from sports_engine.models.ensemble.score_projection import (
    convex_probability_blend,
    project_match_odds_marginals,
    score_matrix_binary_markets,
    score_matrix_match_odds,
)


def test_outcome_projection_is_normalized_and_matches_target_marginals() -> None:
    matrix = np.outer(poisson.pmf(np.arange(8), 1.6), poisson.pmf(np.arange(8), 1.1))
    matrix /= matrix.sum()
    target = np.asarray([0.25, 0.35, 0.40])

    projected = project_match_odds_marginals(matrix, target)

    assert np.isclose(projected.sum(), 1.0)
    assert np.allclose(score_matrix_match_odds(projected), target)
    home_mask = np.tril(np.ones_like(matrix, dtype=bool), -1)
    assert np.allclose(
        projected[home_mask] / projected[home_mask].sum(),
        matrix[home_mask] / matrix[home_mask].sum(),
    )


def test_probability_blend_rejects_invalid_inputs() -> None:
    valid = np.asarray([[0.4, 0.3, 0.3]])
    assert np.allclose(convex_probability_blend(valid, valid, ml_weight=0.5), valid)
    with np.testing.assert_raises(ValueError):
        convex_probability_blend(valid, valid, ml_weight=1.1)
    with np.testing.assert_raises(ValueError):
        project_match_odds_marginals(np.ones(3), valid[0])


def test_research_fusion_writes_hash_bound_non_promotable_artifact(tmp_path: Path) -> None:
    score_path = _report(tmp_path, "dixon-coles", score=True)
    ml_path = _report(tmp_path, "catboost", score=False)

    path = evaluate_ml_score_fusion(score_path, ml_path, tmp_path / "fusion", random_seed=7)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["selected_ml_weight"] == 0.0
    assert payload["promotion_eligible"] is False
    assert payload["serving_changed"] is False
    prediction_path = Path(payload["prediction_artifact"]["path"])
    assert hashlib.sha256(prediction_path.read_bytes()).hexdigest() == payload["prediction_artifact"]["sha256"]


def _report(tmp_path: Path, model_type: str, *, score: bool) -> Path:
    rows = 12
    matrix = ScoreDistribution.poisson(1.4, 1.0).probabilities
    match = score_matrix_match_odds(matrix)
    btts, totals = score_matrix_binary_markets(matrix)
    data: dict[str, object] = {
        "fixture_id": [f"fixture-{index:02d}" for index in range(rows)],
        "prediction_timestamp": [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(rows)],
        "fold": [1] * 6 + [2] * 6,
        "target": [index % 3 for index in range(rows)],
        "home_probability": [float(match[0])] * rows,
        "draw_probability": [float(match[1])] * rows,
        "away_probability": [float(match[2])] * rows,
    }
    if score:
        data.update(
            {
                "target_home_goals": [index % 4 for index in range(rows)],
                "target_away_goals": [(index + 1) % 3 for index in range(rows)],
                "btts_target": [int(index % 4 > 0 and (index + 1) % 3 > 0) for index in range(rows)],
                "btts_yes_probability": [btts] * rows,
                "over_2_5_target": [int(index % 4 + (index + 1) % 3 >= 3) for index in range(rows)],
                "over_2_5_probability": [totals] * rows,
                "home_expected_goals": [1.4] * rows,
                "away_expected_goals": [1.0] * rows,
                "dixon_coles_rho": [0.0] * rows,
            }
        )
    prediction_path = tmp_path / f"{model_type}.predictions.parquet"
    pl.DataFrame(data).write_parquet(prediction_path)
    raw = prediction_path.read_bytes()
    report_path = tmp_path / f"{model_type}.json"
    report_path.write_text(
        json.dumps(
            {
                "model_type": model_type,
                "candidate_version": f"{model_type}-version",
                "candidate_hyperparameters": {"maximum_goals": 5},
                "dataset_hash": "same-dataset-hash",
                "aggregate_metrics": {"log_loss": 1.0},
                "prediction_artifact": {
                    "path": str(prediction_path),
                    "rows": rows,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    return report_path
