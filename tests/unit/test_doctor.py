from pathlib import Path

from sports_engine.providers.api_football.access import PRODUCTION_ACCESS_PROBE_LEAGUE, production_access_probe
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.leagues import upsert_competition_season


def test_current_season_probe_uses_the_probe_leagues_own_season(tmp_path: Path) -> None:
    connection = connect(tmp_path / "doctor.duckdb")
    migrate(connection)
    upsert_competition_season(
        connection,
        {"id": PRODUCTION_ACCESS_PROBE_LEAGUE, "name": "Premier League"},
        {"year": 2026, "current": True, "coverage": {}},
        admitted=True,
        reason="probe league",
        priority=1,
    )
    upsert_competition_season(
        connection,
        {"id": 999, "name": "Future Tournament"},
        {"year": 2028, "current": True, "coverage": {}},
        admitted=False,
        reason="future catalog row",
        priority=9,
    )

    probe = production_access_probe(connection, 2025)
    assert (probe.league, probe.season, probe.stored_accessible) == (39, 2026, True)
    connection.close()


def test_current_season_probe_falls_back_when_probe_league_is_absent(tmp_path: Path) -> None:
    connection = connect(tmp_path / "doctor-fallback.duckdb")
    migrate(connection)
    probe = production_access_probe(connection, 2026)
    assert (probe.league, probe.season, probe.stored_accessible) == (39, 2026, None)
    connection.close()
