import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from sports_engine.evaluation.score_calibration import (
    _scaled_score_matrix,
    _score_outputs,
    evaluate_score_intensity_calibration,
)


def test_scaled_score_matrix_remains_normalized_and_coherent() -> None:
    baseline = _scaled_score_matrix(1.4, 1.1, -0.08, 1.0)
    hotter = _scaled_score_matrix(1.4, 1.1, -0.08, 1.2)

    assert baseline.sum() == pytest.approx(1.0)
    assert hotter.sum() == pytest.approx(1.0)
    assert (baseline >= 0).all()
    indices = np.indices(hotter.shape)
    assert hotter[(indices[0] + indices[1]) >= 3].sum() > baseline[
        (np.indices(baseline.shape)[0] + np.indices(baseline.shape)[1]) >= 3
    ].sum()


def test_score_calibration_uses_final_fold_only_after_validation(tmp_path: Path) -> None:
    rows = 80
    frame = pl.DataFrame(
        {
            "fixture_id": [f"fixture-{index}" for index in range(rows)],
            "prediction_timestamp": [
                datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(rows)
            ],
            "fold": np.repeat([1, 2, 3, 4], rows // 4),
            "target_home_goals": [2 if index % 3 else 1 for index in range(rows)],
            "target_away_goals": [1 if index % 4 else 2 for index in range(rows)],
            "home_expected_goals": [1.35] * rows,
            "away_expected_goals": [1.05] * rows,
            "dixon_coles_rho": [-0.05] * rows,
            "home_training_matches": [20] * rows,
            "away_training_matches": [20] * rows,
        }
    )
    baseline = _score_outputs(frame, 1.0)
    home = frame["target_home_goals"].to_numpy()
    away = frame["target_away_goals"].to_numpy()
    frame = frame.with_columns(
        pl.Series("target", np.where(home > away, 0, np.where(home == away, 1, 2))),
        pl.Series("home_probability", baseline["match_odds"][:, 0]),
        pl.Series("draw_probability", baseline["match_odds"][:, 1]),
        pl.Series("away_probability", baseline["match_odds"][:, 2]),
        pl.Series("btts_target", ((home > 0) & (away > 0)).astype(int)),
        pl.Series("btts_yes_probability", baseline["BTTS"]),
        pl.Series("over_2_5_target", ((home + away) >= 3).astype(int)),
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

    result = evaluate_score_intensity_calibration(
        report,
        tmp_path / "evaluation",
        random_seed=7,
        maximum_validation_log_loss_degradation=1.0,
    )
    payload = json.loads(result.read_text(encoding="utf-8"))

    assert payload["contract"]["development_folds"] == [1, 2]
    assert payload["contract"]["validation_fold"] == 3
    assert payload["contract"]["untouched_test_fold"] == 4
    assert payload["validation_gate"]["passed"] is True
    assert payload["untouched_test"]["rows"] == 20
    assert Path(payload["prediction_artifact"]["path"]).is_file()


def test_score_calibration_rejects_tampered_source(tmp_path: Path) -> None:
    predictions = tmp_path / "source.predictions.parquet"
    predictions.write_bytes(b"not parquet")
    report = tmp_path / "source.json"
    report.write_text(
        json.dumps(
            {
                "model_type": "dixon-coles",
                "prediction_artifact": {"path": str(predictions), "sha256": "wrong"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="digest"):
        evaluate_score_intensity_calibration(report, tmp_path / "evaluation", random_seed=7)
