from pathlib import Path
from typing import Any

from sports_engine.sports.football.ingestion.discovery import (
    CompetitionDiscoveryService,
    admit_observation_universe,
    score_competition,
)
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate


class CatalogProvider:
    def get(self, endpoint: object, parameters: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
        assert parameters == {"current": "true"}
        full = {
            "fixtures": {
                "events": True,
                "lineups": True,
                "statistics_fixtures": True,
                "statistics_players": True,
            },
            "players": True,
            "odds": True,
        }
        return [
            {
                "league": {"id": 39, "name": "Premier League", "country": "England", "type": "League"},
                "seasons": [{"year": 2026, "current": True, "coverage": full}],
            },
            {
                "league": {"id": 999, "name": "International U19 Friendly", "country": "World", "type": "Cup"},
                "seasons": [{"year": 2026, "current": True, "coverage": full}],
            },
            {
                "league": {"id": 1000, "name": "Sparse League", "country": "Test", "type": "League"},
                "seasons": [{"year": 2026, "current": True, "coverage": {"fixtures": {}, "odds": False}}],
            },
        ]


def test_suitability_components_are_transparent() -> None:
    score = score_competition(
        {"name": "Good League", "type": "League"},
        {
            "coverage": {
                "fixtures": {
                    "events": True,
                    "lineups": True,
                    "statistics_fixtures": True,
                    "statistics_players": True,
                },
                "players": True,
                "odds": True,
            }
        },
    )
    assert score.data_quality == 1.0
    assert score.market_quality == 1.0
    assert score.total > 0.75
    assert not score.reasons


def test_discovery_persists_three_governed_universes(tmp_path: Path) -> None:
    connection = connect(tmp_path / "discovery.duckdb")
    migrate(connection)
    result = CompetitionDiscoveryService(
        connection, CatalogProvider(), lambda purpose, run_id: "raw/catalog.json"
    ).run()
    assert result.discovered == 3
    assert result.observation == 1
    assert result.rejected == 1
    assert connection.execute(
        "SELECT universe_state, count(*) FROM competition_discoveries GROUP BY 1 ORDER BY 1"
    ).fetchall() == [("DISCOVERED", 1), ("OBSERVATION", 1), ("REJECTED", 1)]
    assert connection.execute("SELECT count(*) FROM competition_seasons WHERE admitted").fetchone() == (0,)
    connection.close()


def test_rediscovery_preserves_admission_and_observation_admission_is_bounded(tmp_path: Path) -> None:
    connection = connect(tmp_path / "admission.duckdb")
    migrate(connection)
    service = CompetitionDiscoveryService(connection, CatalogProvider(), lambda purpose, run_id: "raw/catalog.json")
    service.run()
    admitted = admit_observation_universe(connection, limit=1)
    assert len(admitted) == 1
    service.run()
    assert connection.execute(
        "SELECT admitted FROM competition_seasons WHERE competition_season_id=?", admitted
    ).fetchone() == (True,)
    assert connection.execute(
        "SELECT universe_state FROM competition_discoveries WHERE competition_season_id=?", admitted
    ).fetchone() == ("OBSERVATION",)
    connection.close()
