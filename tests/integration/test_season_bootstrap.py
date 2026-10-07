from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import ProviderPlanAccessError, QuotaExhaustedError
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.sports.football.ingestion.season_bootstrap import SeasonBootstrapService
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.leagues import upsert_competition_season

TEAM_PAYLOAD = {
    "team": {
        "id": 10,
        "name": "Home",
        "code": "HOM",
        "country": "Country",
        "founded": 1900,
        "national": False,
        "logo": None,
    },
    "venue": None,
}

FIXTURE_PAYLOAD = {
    "fixture": {
        "id": 100,
        "date": "2026-08-01T12:00:00+00:00",
        "status": {"short": "NS", "long": "Not Started", "elapsed": None},
    },
    "league": {"id": 39, "season": 2026, "round": "Regular Season - 1"},
    "teams": {"home": {"id": 10, "name": "Home"}, "away": {"id": 11, "name": "Away"}},
    "goals": {"home": None, "away": None},
}


class BootstrapProvider:
    def __init__(self, stop_on_fixtures: bool = False) -> None:
        self.stop_on_fixtures = stop_on_fixtures
        self.endpoints: list[str] = []

    def get(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        *,
        purpose: str,
        priority: Priority,
        job_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self.endpoints.append(str(endpoint))
        if endpoint == Endpoint.TEAMS:
            return [TEAM_PAYLOAD]
        if endpoint == Endpoint.FIXTURES:
            if self.stop_on_fixtures:
                raise QuotaExhaustedError("reserve")
            return [FIXTURE_PAYLOAD]
        raise AssertionError(endpoint)


def admitted_season(connection: Any) -> None:
    upsert_competition_season(
        connection,
        {"id": 39, "name": "League", "country": "Country", "type": "League"},
        {
            "year": 2026,
            "start": "2026-08-01",
            "end": "2027-05-31",
            "current": True,
            "coverage": {},
        },
        admitted=True,
        reason="qualified",
        priority=1,
        source_raw_path="coverage.json.gz",
    )


def test_bootstrap_resumes_at_fixture_stage_and_is_idempotent(tmp_path: Path) -> None:
    connection = connect(tmp_path / "bootstrap.duckdb")
    migrate(connection)
    admitted_season(connection)
    stopped = BootstrapProvider(stop_on_fixtures=True)
    first = SeasonBootstrapService(
        connection,
        stopped,
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    ).run()
    assert not first.complete and first.next_stage == "fixtures"
    resumed = BootstrapProvider()
    second = SeasonBootstrapService(
        connection,
        resumed,
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    ).run()
    assert second.complete
    assert resumed.endpoints == [str(Endpoint.FIXTURES)]
    assert connection.execute("SELECT count(*) FROM fixtures").fetchone() == (1,)
    rerun = SeasonBootstrapService(
        connection,
        BootstrapProvider(),
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    ).run()
    assert rerun.complete
    assert connection.execute("SELECT count(*) FROM fixtures").fetchone() == (1,)
    assert connection.execute("SELECT count(*) FROM fixture_team").fetchone() == (2,)
    assert connection.execute("SELECT count(*) FROM fixture_observations").fetchone() == (1,)
    connection.close()


def test_fixture_correction_is_append_only_and_current_view_updates(tmp_path: Path) -> None:
    connection = connect(tmp_path / "correction.duckdb")
    migrate(connection)
    admitted_season(connection)
    first_provider = BootstrapProvider()
    SeasonBootstrapService(
        connection,
        first_provider,
        raw_path_resolver=lambda purpose, run_id: "first.json.gz",
    ).run()
    corrected = dict(FIXTURE_PAYLOAD)
    corrected["fixture"] = {
        **FIXTURE_PAYLOAD["fixture"],
        "date": "2026-08-02T14:00:00+00:00",
        "status": {"short": "FT", "long": "Match Finished", "elapsed": 90},
    }
    corrected["goals"] = {"home": 2, "away": 1}

    class CorrectedProvider(BootstrapProvider):
        def get(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            endpoint = args[0]
            if endpoint == Endpoint.TEAMS:
                return [TEAM_PAYLOAD]
            return [corrected]

    SeasonBootstrapService(
        connection,
        CorrectedProvider(),
        raw_path_resolver=lambda purpose, run_id: "corrected.json.gz",
    ).run()
    assert connection.execute("SELECT count(*) FROM fixture_observations").fetchone() == (2,)
    assert connection.execute("SELECT status_short, home_goals, away_goals FROM fixtures_current").fetchone() == (
        "FT",
        2,
        1,
    )
    assert connection.execute("SELECT count(*) FROM fixture_schedule_snapshots").fetchone() == (2,)
    assert connection.execute("SELECT count(*) FROM fixture_status_history").fetchone() == (2,)
    connection.close()


def test_plan_restriction_marks_competition_inaccessible(tmp_path: Path) -> None:
    connection = connect(tmp_path / "restricted.duckdb")
    migrate(connection)
    admitted_season(connection)

    class RestrictedProvider(BootstrapProvider):
        def get(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            raise ProviderPlanAccessError("current season unavailable")

    result = SeasonBootstrapService(
        connection,
        RestrictedProvider(),
        raw_path_resolver=lambda purpose, run_id: "restricted.json.gz",
    ).run()
    assert not result.complete
    assert result.blocked_reason == "current season unavailable"
    assert connection.execute("SELECT admitted, provider_accessible FROM competition_seasons").fetchone() == (
        False,
        False,
    )
    connection.close()
