import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import polars as pl

from sports_engine.evaluation.family_specialists import evaluate_ml_family_specialist
from sports_engine.models.calibration.binary import BinaryProbabilityCalibrator


def test_binary_calibrator_preserves_valid_probability_range() -> None:
    calibrator = BinaryProbabilityCalibrator("platt", random_seed=7).fit(
        probabilities=pl.Series([0.1, 0.2, 0.8, 0.9]).to_numpy(),
        targets=pl.Series([0, 0, 1, 1]).to_numpy(),
    )
    values = calibrator.transform(pl.Series([0.3, 0.7]).to_numpy())
    assert len(values) == 2
    assert ((values >= 0) & (values <= 1)).all()


def test_family_specialist_is_family_scoped_and_non_promotable(tmp_path: Path) -> None:
    rows = 12
    timestamps = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(rows)]
    frame = pl.DataFrame(
        {
            "fixture_id": [f"fixture-{index}" for index in range(rows)],
            "prediction_timestamp": timestamps,
            "home_team_id": [f"home-{index % 3}" for index in range(rows)],
            "away_team_id": [f"away-{index % 4}" for index in range(rows)],
            "target_home_goals": [index % 3 for index in range(rows)],
            "target_away_goals": [(index + 1) % 3 for index in range(rows)],
            "target_result": [
                "HOME" if index % 3 == 0 else "DRAW" if index % 3 == 1 else "AWAY"
                for index in range(rows)
            ],
            "feature_a": [float(index) for index in range(rows)],
            "feature_b": [float(index % 2) for index in range(rows)],
        }
    )
    parquet = tmp_path / "dataset.parquet"
    frame.write_parquet(parquet)
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE feature_datasets(dataset_id VARCHAR, name VARCHAR, schema_hash VARCHAR, "
        "dataset_hash VARCHAR, parquet_path VARCHAR, config JSON, created_at TIMESTAMP)"
    )
    connection.execute(
        "INSERT INTO feature_datasets VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["dataset-id", "test", "schema", "dataset-hash", str(parquet), "{}", timestamps[-1]],
    )
    report = _ml_report(tmp_path, timestamps)

    path = evaluate_ml_family_specialist(
        connection,
        report,
        tmp_path / "output",
        random_seed=7,
        cpu_threads=1,
    )
    connection.close()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["promotion_eligible"] is False
    assert set(payload["aggregate_metrics"]) == {"BTTS", "TOTAL_GOALS_2_5"}
    assert payload["interpretation"].startswith("Each binary model is a market-family specialist")
    prediction_path = Path(payload["prediction_artifact"]["path"])
    assert hashlib.sha256(prediction_path.read_bytes()).hexdigest() == payload["prediction_artifact"]["sha256"]


def _ml_report(tmp_path: Path, timestamps: list[datetime]) -> Path:
    predictions = pl.DataFrame(
        {
            "fixture_id": ["unused"],
            "prediction_timestamp": [timestamps[-1]],
            "fold": [1],
            "target": [0],
            "home_probability": [0.4],
            "draw_probability": [0.3],
            "away_probability": [0.3],
        }
    )
    prediction_path = tmp_path / "ml.predictions.parquet"
    predictions.write_parquet(prediction_path)
    raw = prediction_path.read_bytes()
    report_path = tmp_path / "ml.json"
    report_path.write_text(
        json.dumps(
            {
                "model_type": "logistic",
                "candidate_version": "logistic-test",
                "candidate_hyperparameters": {"C": 0.1},
                "candidate_calibration_method": None,
                "candidate_feature_columns": ["feature_a", "feature_b"],
                "dataset_id": "dataset-id",
                "dataset_hash": "dataset-hash",
                "minimum_train_periods": 4,
                "test_periods": 2,
                "rolling_train_periods": None,
                "aggregate_metrics": {"log_loss": 1.0},
                "prediction_artifact": {
                    "path": str(prediction_path),
                    "rows": 1,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    return report_path
