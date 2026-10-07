from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sports_engine.core.enums import Priority
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.sports.football.ingestion.reconciliation import FixtureReconciliationService
from sports_engine.sports.football.ingestion.season_bootstrap import SeasonBootstrapService
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.leagues import upsert_competition_season


def fixture(status: str, kickoff: str, home_goals: int | None) -> dict[str, Any]:
    return {
        "fixture": {
            "id": 100,
            "date": kickoff,
            "status": {"short": status, "long": status, "elapsed": 90 if status == "FT" else None},
        },
        "league": {"id": 39, "season": 2026, "round": "Round 1"},
        "teams": {"home": {"id": 10, "name": "Home"}, "away": {"id": 11, "name": "Away"}},
        "goals": {"home": home_goals, "away": 0 if home_goals is not None else None},
    }


class Provider:
    def __init__(self, fixture_payload: dict[str, Any]) -> None:
        self.fixture_payload = fixture_payload

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
                {"team": {"id": 10, "name": "Home", "country": "Country"}, "venue": None},
                {"team": {"id": 11, "name": "Away", "country": "Country"}, "venue": None},
            ]
        return [self.fixture_payload]


def test_reconciliation_records_schedule_status_and_score_correction(tmp_path: Path) -> None:
    connection = connect(tmp_path / "reconcile.duckdb")
    migrate(connection)
    upsert_competition_season(
        connection,
        {"id": 39, "name": "League", "country": "Country", "type": "League"},
        {"year": 2026, "current": True, "coverage": {}},
        admitted=True,
        reason="qualified",
        priority=1,
        source_raw_path="coverage.json.gz",
    )

    def resolver(purpose: str, run_id: str | None) -> str:
        return f"{purpose}.json.gz"

    SeasonBootstrapService(
        connection,
        Provider(fixture("NS", "2026-08-01T12:00:00+00:00", None)),
        raw_path_resolver=resolver,
    ).run()
    result = FixtureReconciliationService(
        connection,
        Provider(fixture("FT", "2026-08-02T12:00:00+00:00", 2)),
        raw_path_resolver=resolver,
    ).run()
    assert result.complete and result.fixtures_seen == 1 and result.observations_added == 1
    assert connection.execute("SELECT status_short, home_goals, away_goals FROM fixtures_current").fetchone() == (
        "FT",
        2,
        0,
    )
    assert connection.execute("SELECT count(*) FROM fixture_schedule_snapshots").fetchone() == (2,)
    assert connection.execute("SELECT count(*) FROM fixture_status_history").fetchone() == (2,)
    connection.close()
