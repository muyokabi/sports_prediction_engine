import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from sports_engine.core.config import AppConfig
from sports_engine.models.registry import ModelRegistry, ModelRun
from sports_engine.sports.football.normalization.fixtures import normalize_fixture
from sports_engine.training.continuous import _train_due_candidate, run_due_ml_updates
from sports_engine.training.scheduler import (
    DEFAULT_RETRAINING_POLICIES,
    UpdateDecision,
    UpdateTrigger,
    assess_model_update,
)
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.fixtures import upsert_fixture
from sports_engine.warehouse.repositories.leagues import upsert_competition_season


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
    assert stored is not None
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


def test_empty_warehouse_does_not_schedule_initial_training(tmp_path: Path) -> None:
    connection = connect(tmp_path / "empty-scheduler.duckdb")
    migrate(connection)
    decision = assess_model_update(connection, "poisson", eligible_observations=0)
    assert not decision.due
    assert decision.triggers == ()
    connection.close()


def test_due_ml_updates_accepts_empty_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    connection = connect(tmp_path / "empty-learning.duckdb")
    migrate(connection)
    promotion = SimpleNamespace(promoted_versions=(), withheld_versions=())
    monkeypatch.setattr("sports_engine.training.continuous.run_automated_promotion", lambda *args, **kwargs: promotion)
    config = AppConfig(data_dir=tmp_path / "data", artifacts_dir=tmp_path / "artifacts")
    result = run_due_ml_updates(connection, config, ledger_mode="production")
    assert result.eligible_observations == 0
    assert result.due_models == ()
    assert result.trained_versions == ()
    connection.close()


def test_due_ml_updates_counts_score_only_results_in_exact_training_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = connect(tmp_path / "score-only-learning.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2026, "current": True, "coverage": {}},
        admitted=True,
        ledger_mode="production",
        reason="qualified",
        priority=1,
    )
    payload = {
        "fixture": {
            "id": 901,
            "date": datetime(2026, 10, 1, 12, tzinfo=UTC).isoformat(),
            "status": {"short": "FT", "long": "Finished", "elapsed": 90},
        },
        "league": {"id": 39, "season": 2026, "round": "Round 1"},
        "teams": {
            "home": {"id": 10, "name": "Home"},
            "away": {"id": 11, "name": "Away"},
        },
        "goals": {"home": 1, "away": 0},
    }
    upsert_fixture(connection, normalize_fixture(payload), season_id, "fixture.json.gz")
    observed_counts: list[int] = []

    def not_due(*_args: object, eligible_observations: int, **_kwargs: object) -> UpdateDecision:
        observed_counts.append(eligible_observations)
        return UpdateDecision("poisson", None, False, 0, (), "full_refit")

    promotion = SimpleNamespace(promoted_versions=(), withheld_versions=())
    monkeypatch.setattr("sports_engine.training.continuous.assess_model_update", not_due)
    monkeypatch.setattr("sports_engine.training.continuous.run_automated_promotion", lambda *args, **kwargs: promotion)
    config = AppConfig(data_dir=tmp_path / "data", artifacts_dir=tmp_path / "artifacts")

    result = run_due_ml_updates(connection, config, ledger_mode="production")

    assert result.eligible_observations == 1
    assert observed_counts == [1] * 6
    assert connection.execute("SELECT count(*) FROM fixture_quality_status").fetchone() == (0,)
    connection.close()


def test_due_ml_update_falls_back_to_immutable_full_refit() -> None:
    calls: list[dict[str, object]] = []

    class Trainer:
        def train(self, _model_type: str, **kwargs: object) -> object:
            calls.append(kwargs)
            if kwargs["training_mode"] == "warm_start":
                raise ValueError("feature schema changed")
            return SimpleNamespace(version="replacement")

    decision = UpdateDecision("logistic", "parent", True, 100, (UpdateTrigger.NEW_OBSERVATIONS,), "warm_start")
    result = _train_due_candidate(Trainer(), decision, "dataset")  # type: ignore[arg-type]
    assert result.version == "replacement"
    assert [call["training_mode"] for call in calls] == ["warm_start", "full_refit"]
    assert calls[0]["parent_model_version"] == "parent"
    assert "parent_model_version" not in calls[1]


def test_automatic_ml_updates_use_full_refits() -> None:
    assert DEFAULT_RETRAINING_POLICIES["logistic"].mode == "full_refit"
    assert DEFAULT_RETRAINING_POLICIES["catboost"].mode == "full_refit"
    assert DEFAULT_RETRAINING_POLICIES["lightgbm"].mode == "full_refit"
