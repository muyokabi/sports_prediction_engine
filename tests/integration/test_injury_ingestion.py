from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any

from sports_engine.core.enums import Priority
from sports_engine.sports.football.ingestion.injuries import InjuryIngestionService
from sports_engine.sports.football.normalization.fixtures import normalize_fixture
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.fixtures import upsert_fixture
from sports_engine.warehouse.repositories.leagues import upsert_competition_season


def test_injuries_are_append_only_and_unknown_teams_are_ignored(tmp_path: Path) -> None:
    connection = connect(tmp_path / "injuries.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2026, "current": True, "coverage": {"injuries": True}},
        admitted=True,
        reason="qualified",
        priority=1,
    )
    upsert_fixture(
        connection,
        normalize_fixture(
            {
                "fixture": {
                    "id": 100,
                    "date": "2026-10-08T12:00:00+00:00",
                    "status": {"short": "NS", "long": "Not Started", "elapsed": None},
                },
                "league": {"id": 39, "season": 2026, "round": "Round 1"},
                "teams": {
                    "home": {"id": 10, "name": "Home"},
                    "away": {"id": 11, "name": "Away"},
                },
                "goals": {"home": None, "away": None},
            }
        ),
        season_id,
        "fixture.json.gz",
    )

    class Provider:
        def get_all_pages(
            self,
            endpoint: str,
            parameters: Mapping[str, Any],
            *,
            purpose: str,
            priority: Priority,
            job_run_id: str | None = None,
        ) -> Iterator[dict[str, Any]]:
            yield {
                "fixture": {"id": 100},
                "team": {"id": 10, "name": "Home"},
                "player": {"id": 500, "name": "Player", "type": "Missing Fixture", "reason": "Hamstring"},
            }
            yield {
                "fixture": {"id": 999},
                "team": {"id": 999, "name": "Unknown"},
                "player": {"id": 501, "name": "Unknown", "type": "Missing Fixture", "reason": "Knock"},
            }

    result = InjuryIngestionService(
        connection,
        Provider(),
        raw_path_resolver=lambda purpose, run_id: "injuries.json.gz",
    ).run(date(2026, 10, 8))
    assert (result.observations_written, result.ignored_unknown_teams) == (1, 1)
    assert connection.execute("SELECT count(*) FROM injury_observations").fetchone() == (1,)
    assert connection.execute("SELECT complete FROM injury_collection_runs").fetchone() == (True,)
    connection.close()
