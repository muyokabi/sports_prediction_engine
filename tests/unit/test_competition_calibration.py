import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import polars as pl
import pytest

from sports_engine.evaluation.competition_calibration import (
    _fit_competition_scales,
    _scale_vector,
    evaluate_competition_intensity_calibration,
)
from sports_engine.evaluation.score_calibration import _score_outputs


def _frame() -> pl.DataFrame:
    rows = 40
    return pl.DataFrame(
        {
            "fixture_id": [f"fixture-{index}" for index in range(rows)],
            "competition_id": ["represented"] * 35 + ["sparse"] * 5,
            "competition_name": ["Represented"] * 35 + ["Sparse"] * 5,
            "prediction_timestamp": [datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(rows)],
            "fold": [1] * rows,
            "target_home_goals": [2] * rows,
            "target_away_goals": [1] * rows,
            "home_expected_goals": [1.0] * rows,
            "away_expected_goals": [1.0] * rows,
            "dixon_coles_rho": [-0.05] * rows,
        }
    )


def test_competition_scale_is_shrunk_and_sparse_competition_falls_back() -> None:
    frame = _frame()
    scales, evidence = _fit_competition_scales(
        frame,
        prior_exposure=25.0,
        minimum_rows=30,
    )
    values, states = _scale_vector(frame, scales)

    assert scales == {"represented": pytest.approx((105.0 + 25.0) / (70.0 + 25.0))}
    assert evidence["competitions_estimated"] == 1
    assert np.all(values[:35] > 1.0)
    assert np.all(values[35:] == 1.0)
    assert set(states[35:]) == {"SPARSE_OR_UNSEEN_FALLBACK"}


def test_score_outputs_accept_fixture_specific_scales_and_remain_coherent() -> None:
    frame = _frame().head(2)
    outputs = _score_outputs(frame, np.asarray([0.9, 1.1]))

    assert outputs["match_odds"].shape == (2, 3)
    assert outputs["match_odds"].sum(axis=1) == pytest.approx([1.0, 1.0])
    assert outputs["TOTAL_GOALS_2_5"][1] > outputs["TOTAL_GOALS_2_5"][0]


def test_score_outputs_rejects_scale_vector_with_wrong_length() -> None:
    with pytest.raises(ValueError, match="one scale per fixture"):
        _score_outputs(_frame().head(2), np.asarray([1.0]))


def test_failed_validation_keeps_final_fold_sealed(tmp_path: Path) -> None:
    rows = 80
    home_goals = np.asarray([3] * 40 + [0] * 20 + [2] * 20)
    away_goals = np.asarray([2] * 40 + [0] * 20 + [1] * 20)
    frame = pl.DataFrame(
        {
            "fixture_id": [f"fixture-{index}" for index in range(rows)],
            "prediction_timestamp": [datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(rows)],
            "fold": np.repeat([1, 2, 3, 4], rows // 4),
            "target_home_goals": home_goals,
            "target_away_goals": away_goals,
            "home_expected_goals": [1.35] * rows,
            "away_expected_goals": [1.05] * rows,
            "dixon_coles_rho": [-0.05] * rows,
            "home_training_matches": [20] * rows,
            "away_training_matches": [20] * rows,
        }
    )
    baseline = _score_outputs(frame, 1.0)
    frame = frame.with_columns(
        pl.Series("target", np.where(home_goals > away_goals, 0, np.where(home_goals == away_goals, 1, 2))),
        pl.Series("home_probability", baseline["match_odds"][:, 0]),
        pl.Series("draw_probability", baseline["match_odds"][:, 1]),
        pl.Series("away_probability", baseline["match_odds"][:, 2]),
        pl.Series("btts_target", ((home_goals > 0) & (away_goals > 0)).astype(int)),
        pl.Series("btts_yes_probability", baseline["BTTS"]),
        pl.Series("over_2_5_target", ((home_goals + away_goals) >= 3).astype(int)),
        pl.Series("over_2_5_probability", baseline["TOTAL_GOALS_2_5"]),
    )
    predictions = tmp_path / "source.predictions.parquet"
    frame.write_parquet(predictions)
    raw = predictions.read_bytes()
    report = tmp_path / "source.json"
    report.write_text(
        json.dumps(
            {
                "model_type": "dixon-coles",
                "dataset_hash": "dataset-hash",
                "candidate_version": "candidate-version",
                "prediction_artifact": {
                    "path": str(predictions),
                    "rows": rows,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    connection = duckdb.connect()
    connection.execute("CREATE TABLE competitions (competition_id VARCHAR, name VARCHAR)")
    connection.execute("CREATE TABLE competition_seasons (competition_season_id VARCHAR, competition_id VARCHAR)")
    connection.execute("CREATE TABLE fixtures_current (fixture_id VARCHAR, competition_season_id VARCHAR)")
    connection.execute("INSERT INTO competitions VALUES ('competition', 'Competition')")
    connection.execute("INSERT INTO competition_seasons VALUES ('season', 'competition')")
    connection.executemany(
        "INSERT INTO fixtures_current VALUES (?, 'season')",
        [(f"fixture-{index}",) for index in range(rows)],
    )
    try:
        result = evaluate_competition_intensity_calibration(
            connection,
            report,
            tmp_path / "evaluation",
            random_seed=7,
            prior_exposure_grid=(25.0,),
            minimum_competition_rows=1,
            maximum_validation_log_loss_degradation=1.0,
        )
    finally:
        connection.close()
    payload = json.loads(result.read_text(encoding="utf-8"))

    assert payload["validation_gate"]["passed"] is False
    assert payload["decision"] == "REJECTED_ON_VALIDATION"
    assert payload["untouched_test"] is None
    assert payload["prediction_artifact"]["rows"] == 20
