from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import QuotaExhaustedError
from sports_engine.providers.api_football.quota import QuotaObservation
from sports_engine.quota.budget import QuotaBudget, QuotaPolicy
from sports_engine.sports.football.ingestion.backfill import BackfillPlanner, RequestCappedProvider
from sports_engine.sports.football.normalization.fixtures import normalize_fixture
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.fixtures import upsert_fixture
from sports_engine.warehouse.repositories.leagues import upsert_competition_season


def test_backfill_uses_dynamic_surplus_and_excludes_exhausted_repairs(tmp_path: Path) -> None:
    connection = connect(tmp_path / "backfill.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2024, "current": False, "coverage": {}},
        admitted=False,
        replay_eligible=True,
        ledger_mode="replay",
        reason="replay-only",
        priority=1,
    )
    now = datetime.now(UTC)
    for provider_id in (100, 101):
        upsert_fixture(
            connection,
            normalize_fixture(
                {
                    "fixture": {
                        "id": provider_id,
                        "date": "2024-05-01T12:00:00+00:00",
                        "status": {"short": "FT", "long": "Finished", "elapsed": 90},
                    },
                    "league": {"id": 39, "season": 2024, "round": "Round 1"},
                    "teams": {
                        "home": {"id": 10, "name": "Home"},
                        "away": {"id": 11, "name": "Away"},
                    },
                    "goals": {"home": 1, "away": 0},
                }
            ),
            season_id,
            "fixture.json.gz",
        )
    fixture_id = connection.execute("SELECT fixture_id FROM fixtures WHERE provider_fixture_id=101").fetchone()[0]
    connection.execute(
        "INSERT INTO fixture_repair_state VALUES (?, 3, ?, ?, '[]')",
        [fixture_id, now, now - timedelta(hours=1)],
    )
    budget = QuotaBudget(
        QuotaPolicy(minimum_daily_reserve=10, minimum_minute_reserve=2),
        QuotaObservation(7_500, 100, 300, 298, now),
    )
    plan = BackfillPlanner(
        connection,
        budget,
        maximum_requests=40,
        repair_attempt_limit=3,
    ).plan(ledger_mode="replay", estimated_mandatory_requests=20)
    assert plan.request_budget == 40
    assert plan.candidate_count == 1
    assert plan.fixture_ids == (100,)
    connection.close()


def test_request_cap_counts_batch_and_targeted_repairs() -> None:
    class Provider:
        def get(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            return []

    capped = RequestCappedProvider(Provider(), 2)  # type: ignore[arg-type]
    for purpose in ("batch", "repair"):
        assert capped.get("/fixtures", {}, purpose=purpose, priority=Priority.P3) == []
    with pytest.raises(QuotaExhaustedError, match="per-run request cap"):
        capped.get("/fixtures", {}, purpose="overflow", priority=Priority.P3)
    assert capped.requests_used == 2


def test_backfill_can_be_restricted_to_one_registered_season(tmp_path: Path) -> None:
    connection = connect(tmp_path / "season-filter.duckdb")
    migrate(connection)
    for year, provider_id in ((2023, 103), (2024, 104)):
        season_id = upsert_competition_season(
            connection,
            {"id": 39, "name": "League"},
            {"year": year, "current": False, "coverage": {}},
            admitted=False,
            replay_eligible=True,
            ledger_mode="replay",
            reason="replay-only",
            priority=1,
        )
        fixture = {
            "fixture": {
                "id": provider_id,
                "date": f"{year}-05-01T12:00:00+00:00",
                "status": {"short": "FT", "long": "Finished", "elapsed": 90},
            },
            "league": {"id": 39, "season": year, "round": "Round 1"},
            "teams": {"home": {"id": 10, "name": "Home"}, "away": {"id": 11, "name": "Away"}},
            "goals": {"home": 1, "away": 0},
        }
        upsert_fixture(connection, normalize_fixture(fixture), season_id, f"fixture-{year}.json.gz")
    now = datetime.now(UTC)
    budget = QuotaBudget(
        QuotaPolicy(minimum_daily_reserve=10, minimum_minute_reserve=2),
        QuotaObservation(7_500, 100, 300, 298, now),
    )
    plan = BackfillPlanner(connection, budget, maximum_requests=40, repair_attempt_limit=3).plan(
        ledger_mode="replay", provider_season=2024
    )
    assert plan.candidate_count == 1
    assert plan.fixture_ids == (104,)
    connection.close()
