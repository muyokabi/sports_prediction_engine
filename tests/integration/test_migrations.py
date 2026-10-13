from pathlib import Path

from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate, pending_migrations


def test_all_migrations_apply_and_are_idempotent(tmp_path: Path) -> None:
    connection = connect(tmp_path / "test.duckdb")
    assert migrate(connection) == list(range(1, 35))
    assert migrate(connection) == []
    assert pending_migrations(connection) == []
    tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    assert {
        "fixtures",
        "odds_snapshots",
        "model_runs",
        "api_request_log",
        "squad_snapshots",
        "squad_players",
        "competition_season_teams",
        "fixture_observations",
        "provider_capabilities",
        "fixture_quality_status",
        "lineup_observations",
        "fixture_repair_state",
        "injury_observations",
        "injury_collection_runs",
        "prediction_decisions",
        "prediction_outcomes",
        "model_performance_rollups",
        "model_drift_signals",
        "market_reference_quotes",
        "institutional_opportunities",
        "odds_age_research_results",
        "model_promotion_assessments",
        "model_market_role_events",
        "model_probability_scope_validations",
    } <= tables
    connection.close()
