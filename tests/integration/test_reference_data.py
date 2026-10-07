from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sports_engine.core.enums import Priority
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.sports.football.ingestion.reference_data import ReferenceDataService
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.leagues import upsert_competition_season


class ReferenceProvider:
    def get(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        *,
        purpose: str,
        priority: Priority,
        job_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if endpoint == Endpoint.TEAMS:
            return [
                {
                    "team": {
                        "id": 10,
                        "name": "Example FC",
                        "code": "EXA",
                        "country": "Exampleland",
                        "founded": 1901,
                        "national": False,
                        "logo": "https://example.test/team.png",
                    },
                    "venue": {
                        "id": 20,
                        "name": "Example Ground",
                        "address": "1 Main Road",
                        "city": "Example City",
                        "capacity": 10000,
                        "surface": "grass",
                    },
                }
            ]
        if endpoint == Endpoint.SQUADS:
            return [
                {
                    "team": {"id": 10, "name": "Example FC"},
                    "players": [
                        {
                            "id": 30,
                            "name": "A Player",
                            "age": 25,
                            "number": 9,
                            "position": "Attacker",
                            "photo": "https://example.test/player.png",
                        }
                    ],
                }
            ]
        raise AssertionError(f"Unexpected endpoint {endpoint}")


def create_competition_season(connection: Any) -> str:
    return upsert_competition_season(
        connection,
        {"id": 39, "name": "Premier League", "country": "England", "type": "League"},
        {
            "year": 2026,
            "start": "2026-08-01",
            "end": "2027-05-31",
            "current": True,
            "coverage": {},
        },
        admitted=True,
        reason="test",
        priority=1,
        source_raw_path="coverage.json.gz",
    )


def test_team_and_squad_reference_sync(tmp_path: Path) -> None:
    connection = connect(tmp_path / "reference.duckdb")
    migrate(connection)
    competition_season_id = create_competition_season(connection)
    service = ReferenceDataService(
        connection,
        ReferenceProvider(),
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    )
    team_result = service.sync_teams(
        competition_season_id=competition_season_id,
        provider_league_id=39,
        provider_season=2026,
    )
    squad_result = service.sync_squad(
        competition_season_id=competition_season_id,
        provider_team_id=10,
    )
    assert team_result.teams_written == 1
    assert squad_result.players_written == 1
    assert connection.execute("SELECT name, code FROM teams").fetchone() == ("Example FC", "EXA")
    assert connection.execute("SELECT name FROM venues").fetchone() == ("Example Ground",)
    assert connection.execute("SELECT name FROM players").fetchone() == ("A Player",)
    assert connection.execute("SELECT squad_number, position FROM squad_players").fetchone() == (
        9,
        "Attacker",
    )
    assert connection.execute(
        "SELECT count(*) FROM provider_entity_map WHERE entity_type IN ('team', 'venue', 'player')"
    ).fetchone() == (3,)
    assert connection.execute("SELECT count(*) FROM competition_season_teams").fetchone() == (1,)
    connection.close()
