import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from sports_engine.evaluation.reports import WalkForwardEvaluator
from sports_engine.models.registry import ModelRegistry
from sports_engine.training.trainer import ModelTrainer
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate


def _dataset(connection: object, path: Path) -> None:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    results = [(2, 0, "HOME"), (1, 1, "DRAW"), (0, 2, "AWAY")]
    rows = []
    for index in range(30):
        home_goals, away_goals, result = results[index % len(results)]
        rows.append(
            {
                "fixture_id": f"fixture-{index}",
                "prediction_timestamp": base + timedelta(days=index),
                "source_observation_max": base + timedelta(days=index, hours=-1),
                "home_team_id": f"team-{index % 4}",
                "away_team_id": f"team-{(index + 1) % 4}",
                "elo_difference": float(index - 15),
                "form": None if index == 0 else float(index % 5),
                "bookmaker_consensus_known": index % 2 == 0,
                "bookmaker_home_fair": 0.45,
                "bookmaker_draw_fair": 0.25,
                "bookmaker_away_fair": 0.30,
                "target_home_goals": home_goals,
                "target_away_goals": away_goals,
                "target_result": result,
            }
        )
    frame = pl.DataFrame(rows)
    parquet = path / "training.parquet"
    frame.write_parquet(parquet)
    connection.execute(
        "INSERT INTO feature_datasets VALUES (?, ?, current_timestamp, ?, ?, ?, ?, ?, ?)",
        [
            "10000000-0000-0000-0000-000000000001",
            "synthetic",
            base,
            base + timedelta(days=29),
            "schema-hash",
            "dataset-hash",
            str(parquet),
            json.dumps({"ledger_mode": "replay"}),
        ],
    )


@pytest.mark.parametrize("model_type", ["elo", "poisson", "dixon-coles", "logistic", "catboost", "lightgbm"])
def test_training_registers_immutable_candidate_with_manifest(tmp_path: Path, model_type: str) -> None:
    connection = connect(tmp_path / f"{model_type}.duckdb")
    migrate(connection)
    _dataset(connection, tmp_path)
    result = ModelTrainer(connection, tmp_path / "artifacts", random_seed=7, cpu_threads=1).train(
        model_type, dataset_name="synthetic"
    )
    row = connection.execute(
        "SELECT model_type, status, training_dataset_hash, metrics, artifact_path FROM model_runs WHERE version=?",
        [result.version],
    ).fetchone()
    assert row[:3] == (model_type, "candidate", "dataset-hash")
    assert json.loads(row[3])["test_rows"] == 6
    assert Path(row[4]).is_file()
    manifest = json.loads(result.artifact_path.with_suffix(".pkl.json").read_text())
    assert manifest["class_order"] == ["HOME", "DRAW", "AWAY"]
    assert manifest["random_seed"] == 7
    assert json.loads(row[3])["bookmaker_baseline"]["rows"] == 6
    connection.close()


def test_calibration_uses_validation_holdout_and_is_persisted(tmp_path: Path) -> None:
    connection = connect(tmp_path / "calibration.duckdb")
    migrate(connection)
    _dataset(connection, tmp_path)
    result = ModelTrainer(connection, tmp_path / "artifacts", random_seed=7, cpu_threads=1).train(
        "logistic", dataset_name="synthetic", calibration_method="platt"
    )
    row = connection.execute(
        "SELECT calibration_method, metrics FROM model_runs WHERE version=?", [result.version]
    ).fetchone()
    assert row[0] == "platt"
    assert "uncalibrated" in json.loads(row[1])
    assert (result.artifact_path.parent / "calibrator.pkl").is_file()
    connection.close()


def test_registry_promotion_retires_previous_champion(tmp_path: Path) -> None:
    connection = connect(tmp_path / "registry.duckdb")
    migrate(connection)
    _dataset(connection, tmp_path)
    trainer = ModelTrainer(connection, tmp_path / "artifacts", random_seed=7, cpu_threads=1)
    first = trainer.train("elo", dataset_name="synthetic")
    second = trainer.train("poisson", dataset_name="synthetic")
    registry = ModelRegistry(connection)
    connection.execute(
        "UPDATE model_runs SET metrics=? WHERE version=?",
        [json.dumps({"log_loss": 0.2, "brier": 0.2}), first.version],
    )
    registry.promote(first.version)
    connection.execute(
        "UPDATE model_runs SET metrics=? WHERE version=?",
        [json.dumps({"log_loss": 0.1, "brier": 0.1}), second.version],
    )
    registry.promote(second.version)
    assert connection.execute("SELECT version, status FROM model_runs ORDER BY created_at").fetchall() == [
        (first.version, "retired"),
        (second.version, "champion"),
    ]
    connection.close()


def test_walk_forward_evaluation_writes_reproducible_report(tmp_path: Path) -> None:
    connection = connect(tmp_path / "evaluation.duckdb")
    migrate(connection)
    _dataset(connection, tmp_path)
    report = WalkForwardEvaluator(connection, tmp_path / "reports", random_seed=7, cpu_threads=1).evaluate(
        "logistic", dataset_name="synthetic"
    )
    assert report.aggregate_metrics["folds"] == 4
    assert report.aggregate_metrics["test_rows"] == 12
    assert report.aggregate_metrics["bookmaker_baseline"]["rows"] == 12
    assert report.path.is_file()
    connection.close()
