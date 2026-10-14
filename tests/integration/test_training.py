import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import polars as pl
import pytest

from sports_engine.evaluation.reports import WalkForwardEvaluator
from sports_engine.models.ml.logistic import LogisticProbabilityModel
from sports_engine.models.registry import ModelRegistry
from sports_engine.training.trainer import ModelTrainer
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate


def _dataset(
    connection: object,
    path: Path,
    *,
    row_count: int = 30,
    name: str = "synthetic",
    dataset_id: str = "10000000-0000-0000-0000-000000000001",
) -> None:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    results = [(2, 0, "HOME"), (1, 1, "DRAW"), (0, 2, "AWAY")]
    rows = []
    for index in range(row_count):
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
    parquet = path / f"{name}.parquet"
    frame.write_parquet(parquet)
    connection.execute(
        "INSERT INTO feature_datasets VALUES (?, ?, current_timestamp, ?, ?, ?, ?, ?, ?)",
        [
            dataset_id,
            name,
            base,
            base + timedelta(days=row_count - 1),
            "schema-hash",
            f"dataset-hash-{name}",
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
        "SELECT model_type, status, training_dataset_hash, metrics, artifact_path, evidence_state, "
        "training_mode, observations_included FROM model_runs WHERE version=?",
        [result.version],
    ).fetchone()
    assert row[:3] == (model_type, "candidate", "dataset-hash-synthetic")
    assert json.loads(row[3])["test_rows"] == 6
    assert Path(row[4]).is_file()
    assert result.artifact_path.parts[-6] == "models"
    year, month, day = result.artifact_path.parts[-5:-2]
    assert f"{year}{month}{day}T" in result.version
    # The scheduler compares against all immutable dataset observations, not
    # only the fitting partition; otherwise validation/test rows would make a
    # freshly trained model immediately appear due again.
    assert row[5:] == ("RESEARCH_TRAINABLE", "full_refit", 30)
    assert connection.execute(
        "SELECT count(*) FROM model_evidence_assessments WHERE model_type=?", [model_type]
    ).fetchone() == (2,)
    manifest = json.loads(result.artifact_path.with_suffix(".pkl.json").read_text())
    assert manifest["class_order"] == ["HOME", "DRAW", "AWAY"]
    assert manifest["random_seed"] == 7
    assert manifest["artifact_sha256"] == sha256(result.artifact_path.read_bytes()).hexdigest()
    assert manifest["feature_quality_audit"]["rows"] == 30
    assert manifest["feature_quality_audit"]["active_features"] == len(manifest["feature_columns"])
    assert manifest["feature_quality_audit"]["candidate_features"] > len(manifest["feature_columns"])
    assert manifest["feature_quality_audit"]["features"]["bookmaker_home_fair"]["selection_status"] == "CONSTANT"
    assert json.loads(row[3])["bookmaker_baseline"]["rows"] == 6
    deployment = json.loads(row[3])["deployment_refit"]
    assert deployment["performed"] is True
    assert deployment["deployment_rows"] == 30
    cutoff = connection.execute("SELECT training_cutoff FROM model_runs WHERE version=?", [result.version]).fetchone()[
        0
    ]
    assert cutoff == datetime(2025, 1, 30, tzinfo=UTC)
    if model_type == "logistic":
        deployed = LogisticProbabilityModel.load(result.artifact_path)
        assert deployed.estimator.named_steps["scale"].n_samples_seen_ == 30
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
    calibrator_path = result.artifact_path.parent / "calibrator.pkl"
    assert calibrator_path.is_file()
    manifest = json.loads(result.artifact_path.with_suffix(".pkl.json").read_text())
    assert manifest["calibrator_sha256"] == sha256(calibrator_path.read_bytes()).hexdigest()
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
        "UPDATE model_runs SET metrics=?, evidence_state='PRODUCTION_ACTIONABLE' WHERE version=?",
        [json.dumps({"log_loss": 0.2, "brier": 0.2}), first.version],
    )
    registry.promote(first.version)
    connection.execute(
        "UPDATE model_runs SET metrics=?, evidence_state='PRODUCTION_ACTIONABLE' WHERE version=?",
        [json.dumps({"log_loss": 0.1, "brier": 0.1}), second.version],
    )
    registry.promote(second.version)
    assert connection.execute("SELECT version, status FROM model_runs ORDER BY created_at").fetchall() == [
        (first.version, "retired"),
        (second.version, "champion"),
    ]
    connection.close()


@pytest.mark.parametrize("model_type", ["logistic", "catboost", "lightgbm"])
def test_warm_start_creates_immutable_child_candidate(tmp_path: Path, model_type: str) -> None:
    connection = connect(tmp_path / f"warm-{model_type}.duckdb")
    migrate(connection)
    _dataset(connection, tmp_path)
    trainer = ModelTrainer(connection, tmp_path / "artifacts", random_seed=7, cpu_threads=1)
    parent = trainer.train(model_type, dataset_name="synthetic")
    parent_bytes = parent.artifact_path.read_bytes()
    _dataset(
        connection,
        tmp_path,
        row_count=90,
        name="expanded",
        dataset_id="20000000-0000-0000-0000-000000000002",
    )
    child = trainer.train(
        model_type,
        dataset_name="expanded",
        training_mode="warm_start",
        parent_model_version=parent.version,
    )
    assert child.version != parent.version
    assert parent.artifact_path.read_bytes() == parent_bytes
    row = connection.execute(
        "SELECT parent_model_version, training_mode, hyperparameters FROM model_runs WHERE version=?",
        [child.version],
    ).fetchone()
    assert row[:2] == (parent.version, "warm_start")
    assert json.loads(row[2])["incremental_observations"] > 0
    connection.close()


def test_walk_forward_evaluation_writes_reproducible_report(tmp_path: Path) -> None:
    connection = connect(tmp_path / "evaluation.duckdb")
    migrate(connection)
    _dataset(connection, tmp_path)
    candidate = ModelTrainer(connection, tmp_path / "artifacts", random_seed=7, cpu_threads=1).train(
        "logistic", dataset_name="synthetic"
    )
    report = WalkForwardEvaluator(connection, tmp_path / "reports", random_seed=7, cpu_threads=1).evaluate(
        "logistic", dataset_name="synthetic"
    )
    payload = json.loads(report.path.read_text())
    assert payload["candidate_version"] == candidate.version
    assert payload["candidate_training_mode"] == "full_refit"
    prediction_artifact = payload["prediction_artifact"]
    assert prediction_artifact["rows"] == 12
    assert Path(prediction_artifact["path"]).is_file()
    assert report.aggregate_metrics["folds"] == 4
    assert report.aggregate_metrics["test_rows"] == 12
    assert report.aggregate_metrics["bookmaker_baseline"]["rows"] == 12
    assert report.path.is_file()
    connection.close()


def test_score_model_evaluation_retains_family_specific_probabilities(tmp_path: Path) -> None:
    connection = connect(tmp_path / "score-family-evaluation.duckdb")
    migrate(connection)
    _dataset(connection, tmp_path, row_count=45)
    candidate = ModelTrainer(connection, tmp_path / "artifacts", random_seed=7, cpu_threads=1).train(
        "poisson", dataset_name="synthetic"
    )
    report = WalkForwardEvaluator(connection, tmp_path / "reports", random_seed=7, cpu_threads=1).evaluate(
        "poisson", dataset_name="synthetic"
    )
    payload = json.loads(report.path.read_text())
    assert payload["candidate_version"] == candidate.version
    families = payload["aggregate_metrics"]["market_family_metrics"]
    assert set(families) == {"BTTS", "TOTAL_GOALS_2_5"}
    for evidence in families.values():
        assert evidence["probability_integrity"]["passed"] is True
        assert evidence["metric_uncertainty"]["log_loss"]["method"].startswith(
            "chronological-block-bootstrap"
        )
        assert evidence["paired_empirical_rate_difference"]["brier"]["samples"] == 2_000
        assert len(evidence["fold_metrics"]) == 4
    predictions = pl.read_parquet(payload["prediction_artifact"]["path"])
    assert {
        "target_home_goals",
        "target_away_goals",
        "btts_yes_probability",
        "over_2_5_probability",
    } <= set(predictions.columns)
    assert predictions.select(pl.col("btts_yes_probability").is_between(0, 1).all()).item()
    assert predictions.select(pl.col("over_2_5_probability").is_between(0, 1).all()).item()
    connection.close()


def test_probability_scope_validation_is_bound_to_exact_model_and_fails_closed(tmp_path: Path) -> None:
    connection = connect(tmp_path / "scope-validation.duckdb")
    migrate(connection)
    _dataset(connection, tmp_path, row_count=90)
    trained = ModelTrainer(connection, tmp_path / "artifacts", random_seed=7, cpu_threads=1).train(
        "dixon-coles", dataset_name="synthetic"
    )
    evaluator = WalkForwardEvaluator(
        connection,
        tmp_path / "reports",
        random_seed=7,
        cpu_threads=1,
        minimum_competition_rows=100,
        maximum_competition_ece=0.08,
    )
    evaluator._persist_probability_scope_validations(
        "dixon-coles",
        trained.version,
        {
            "probability_forensics": {
                "competition_metrics_minimum_30_rows": {
                    "competition-small": {
                        "competition_name": "Small League",
                        "rows": 99,
                        "log_loss": 1.0,
                        "brier": 0.6,
                        "rps": 0.2,
                        "expected_calibration_error": 0.03,
                        "probability_integrity": {"passed": True},
                        "metric_uncertainty": {
                            "log_loss": {"upper": 1.1},
                            "brier": {"upper": 0.65},
                        },
                    },
                    "competition-unstable": {
                        "competition_name": "Unstable League",
                        "rows": 120,
                        "log_loss": 1.0,
                        "brier": 0.6,
                        "rps": 0.2,
                        "expected_calibration_error": 0.12,
                        "probability_integrity": {"passed": True},
                        "metric_uncertainty": {
                            "log_loss": {"upper": 1.1},
                            "brier": {"upper": 0.65},
                        },
                    },
                    "competition-validated": {
                        "competition_name": "Validated League",
                        "rows": 120,
                        "log_loss": 1.0,
                        "brier": 0.6,
                        "rps": 0.2,
                        "expected_calibration_error": 0.03,
                        "probability_integrity": {"passed": True},
                        "metric_uncertainty": {
                            "log_loss": {"upper": 1.1},
                            "brier": {"upper": 0.65},
                        },
                    },
                }
            }
        },
        tmp_path / "report.json",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    rows = connection.execute(
        "SELECT scope_key, state, reason_codes FROM model_probability_scope_validations "
        "WHERE model_version=? ORDER BY scope_key",
        [trained.version],
    ).fetchall()
    assert rows[0][0:2] == ("competition-small", "INSUFFICIENT_SAMPLE")
    assert "INSUFFICIENT_COMPETITION_EVALUATION_ROWS" in json.loads(rows[0][2])
    assert rows[1][0:2] == ("competition-unstable", "FAILED")
    assert "COMPETITION_CALIBRATION_ECE_EXCEEDED" in json.loads(rows[1][2])
    assert rows[2][0:2] == ("competition-validated", "VALIDATED")
    connection.close()
