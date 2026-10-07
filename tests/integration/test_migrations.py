from pathlib import Path

from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate, pending_migrations


def test_all_migrations_apply_and_are_idempotent(tmp_path: Path) -> None:
    connection = connect(tmp_path / "test.duckdb")
    assert migrate(connection) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
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
    } <= tables
    connection.close()
