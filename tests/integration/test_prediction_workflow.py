import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sports_engine.evaluation.backtest import BacktestService
from sports_engine.models.registry import ModelRegistry, ModelRun
from sports_engine.models.statistical.elo import EloModel
from sports_engine.sports.football.domain.fixture import FixtureRecord
from sports_engine.sports.football.prediction.service import PredictionService
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.fixtures import upsert_fixture
from sports_engine.warehouse.repositories.leagues import upsert_competition_season


def test_champion_prediction_is_point_in_time_and_append_only(tmp_path: Path) -> None:
    connection = connect(tmp_path / "prediction.duckdb")
    migrate(connection)
    observed = datetime(2026, 6, 1, 9, tzinfo=UTC)
    kickoff = observed + timedelta(days=1, hours=3)
    competition_season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "Test League", "country": "Test", "type": "League"},
        {
            "year": 2026,
            "start": "2026-01-01",
            "end": "2026-12-31",
            "current": True,
            "coverage": {},
        },
        admitted=True,
        reason="test",
        priority=1,
        ledger_mode="production",
    )
    fixture_id = upsert_fixture(
        connection,
        FixtureRecord(
            provider_fixture_id=12345,
            provider_competition_id=39,
            provider_season=2026,
            round="1",
            kickoff_utc=kickoff,
            status_short="NS",
            status_long="Not Started",
            elapsed=None,
            home_provider_team_id=1,
            home_team_name="Home",
            away_provider_team_id=2,
            away_team_name="Away",
            home_goals=None,
            away_goals=None,
        ),
        competition_season_id,
        "raw/test.json",
    )
    bookmaker_id = str(uuid.uuid4())
    market_id = str(uuid.uuid4())
    snapshot_id = str(uuid.uuid4())
    connection.execute("INSERT INTO bookmakers VALUES (?, 1, 'Test Book')", [bookmaker_id])
    connection.execute("INSERT INTO bet_markets VALUES (?, 1, 'Match Winner')", [market_id])
    connection.execute(
        "INSERT INTO odds_snapshots VALUES (?, ?, ?, NULL, 'raw/odds.json', NULL, 'hash')",
        [snapshot_id, fixture_id, observed - timedelta(hours=1)],
    )
    for outcome, price, fair in (
        ("home", 3.0, 0.30),
        ("draw", 3.2, 0.30),
        ("away", 2.4, 0.40),
    ):
        selection_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO bet_selections VALUES (?, ?, ?, ?, NULL)",
            [selection_id, market_id, outcome.title(), outcome],
        )
        connection.execute(
            "INSERT INTO odds_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [snapshot_id, bookmaker_id, market_id, selection_id, price, 1 / price, fair, 0.05],
        )
    artifact = tmp_path / "artifacts" / "models" / "elo-test" / "model.pkl"
    EloModel().save(artifact)
    ModelRegistry(connection).register(
        ModelRun(
            model_type="elo",
            version="elo-test",
            status="candidate",
            training_start=observed - timedelta(days=100),
            training_end=observed - timedelta(days=1),
            feature_schema_hash="schema",
            training_dataset_hash="dataset",
            hyperparameters={},
            metrics={"log_loss": 1.0, "brier": 0.6},
            calibration_method=None,
            artifact_path=artifact,
            library_versions={},
            git_commit=None,
            created_at=observed,
        )
    )
    ModelRegistry(connection).promote("elo-test")
    service = PredictionService(connection, windows=[3], exponential_half_life=5.0, prediction_lead_hours=24)
    first = service.predict(kickoff.date(), ledger_mode="production", timezone="UTC", observed_at=observed)
    second = service.predict(
        kickoff.date(),
        ledger_mode="production",
        timezone="UTC",
        observed_at=observed + timedelta(minutes=1),
    )
    assert first.fixture_count == 1
    assert first.frame["probability_home"][0] + first.frame["probability_draw"][0] + first.frame["probability_away"][
        0
    ] == pytest.approx(1.0)
    assert first.prediction_run_id != second.prediction_run_id
    assert connection.execute("SELECT count(*) FROM prediction_runs").fetchone() == (2,)
    assert connection.execute(
        "SELECT count(*) FROM predictions WHERE CAST(fixture_id AS VARCHAR)=?", [fixture_id]
    ).fetchone() == (2,)
    upsert_fixture(
        connection,
        FixtureRecord(
            provider_fixture_id=12345,
            provider_competition_id=39,
            provider_season=2026,
            round="1",
            kickoff_utc=kickoff,
            status_short="FT",
            status_long="Match Finished",
            elapsed=90,
            home_provider_team_id=1,
            home_team_name="Home",
            away_provider_team_id=2,
            away_team_name="Away",
            home_goals=1,
            away_goals=0,
        ),
        competition_season_id,
        "raw/final.json",
    )
    backtest = BacktestService(connection, tmp_path / "backtests").run()
    assert backtest.predictions_seen == 2
    assert backtest.bets == 2
    assert backtest.profit == pytest.approx(4.0)
    assert backtest.report_path.is_file()
    connection.close()
