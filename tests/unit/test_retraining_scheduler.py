import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sports_engine.models.registry import ModelRegistry, ModelRun
from sports_engine.training.scheduler import UpdateTrigger, assess_model_update
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate


def test_retraining_trigger_uses_model_specific_new_observation_policy(tmp_path: Path) -> None:
    connection = connect(tmp_path / "scheduler.duckdb")
    migrate(connection)
    now = datetime(2026, 10, 8, tzinfo=UTC)
    run = ModelRun(
        "poisson",
        "poisson-parent",
        "candidate",
        now - timedelta(days=100),
        now - timedelta(days=8),
        "schema",
        "dataset",
        {},
        {"log_loss": 1.0, "brier": 0.6},
        None,
        Path("model.pkl"),
        {},
        None,
        now - timedelta(days=8),
    )
    ModelRegistry(connection).register(run)
    connection.execute(
        "UPDATE model_runs SET observations_included=100, training_mode='full_refit' WHERE version=?",
        [run.version],
    )
    decision = assess_model_update(connection, "poisson", eligible_observations=125, now=now)
    assert decision.due
    assert UpdateTrigger.NEW_OBSERVATIONS in decision.triggers
    assert UpdateTrigger.ELAPSED_TIME in decision.triggers
    stored = connection.execute(
        "SELECT due, reason_codes FROM model_update_events WHERE current_version=?", [run.version]
    ).fetchone()
    assert stored[0] is True
    assert "NEW_OBSERVATIONS" in json.loads(stored[1])
    connection.close()


def test_drift_can_trigger_review_before_batch_threshold(tmp_path: Path) -> None:
    connection = connect(tmp_path / "drift.duckdb")
    migrate(connection)
    decision = assess_model_update(connection, "catboost", eligible_observations=10, drift=True)
    assert decision.due
    assert UpdateTrigger.DRIFT in decision.triggers
    connection.close()
