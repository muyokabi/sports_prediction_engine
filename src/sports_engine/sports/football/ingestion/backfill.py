from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import duckdb

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import QuotaExhaustedError
from sports_engine.providers.base import SportsDataProvider
from sports_engine.quota.budget import QuotaBudget
from sports_engine.warehouse.transactions import transaction


@dataclass(frozen=True, slots=True)
class BackfillPlan:
    fixture_ids: tuple[int, ...]
    request_budget: int
    candidate_count: int


class RequestCappedProvider:
    """Count every backfill request, including targeted repairs."""

    def __init__(self, provider: SportsDataProvider, maximum_requests: int) -> None:
        self.provider = provider
        self.maximum_requests = maximum_requests
        self.requests_used = 0

    def get(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        *,
        purpose: str,
        priority: Priority,
        job_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.requests_used >= self.maximum_requests:
            raise QuotaExhaustedError("Backfill per-run request cap reached")
        self.requests_used += 1
        return self.provider.get(
            endpoint,
            parameters,
            purpose=purpose,
            priority=priority,
            job_run_id=job_run_id,
        )


def reclassify_completed_results(
    connection: duckdb.DuckDBPyConnection,
    *,
    ledger_mode: str,
    provider_seasons: tuple[int, ...] | None = None,
) -> int:
    """Remove legacy repair blocks from valid completed score observations.

    Older assessments treated optional event, lineup, team-stat and player-stat
    enrichment as mandatory.  Preserve those component states and historical
    issues, but stop retrying them as prerequisites for score modelling.
    """
    season_clause = ""
    parameters: list[Any] = [ledger_mode]
    if provider_seasons is not None:
        if not provider_seasons:
            return 0
        placeholders = ",".join("?" for _ in provider_seasons)
        season_clause = f"AND cs.provider_season IN ({placeholders}) "
        parameters.extend(provider_seasons)
    rows = connection.execute(
        "SELECT q.fixture_id FROM fixture_quality_status q "
        "JOIN fixtures_current f USING (fixture_id) "
        "JOIN competition_seasons cs USING (competition_season_id) "
        "WHERE cs.ledger_mode=? AND q.eligibility='PENDING_REPAIR' "
        "AND f.status_short IN ('FT','AET','PEN') "
        "AND f.provider_fixture_id IS NOT NULL AND f.kickoff_utc IS NOT NULL "
        "AND f.home_goals IS NOT NULL AND f.away_goals IS NOT NULL "
        f"{season_clause}",
        parameters,
    ).fetchall()
    fixture_ids = [row[0] for row in rows]
    if not fixture_ids:
        return 0
    with transaction(connection):
        connection.executemany(
            "UPDATE fixture_quality_status SET eligibility='ML_ELIGIBLE' WHERE fixture_id=?",
            [(fixture_id,) for fixture_id in fixture_ids],
        )
        connection.executemany(
            "DELETE FROM fixture_repair_state WHERE fixture_id=?",
            [(fixture_id,) for fixture_id in fixture_ids],
        )
    return len(fixture_ids)


class BackfillPlanner:
    """Select due, incomplete finals without spending protected quota."""

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        quota_budget: QuotaBudget,
        *,
        maximum_requests: int,
        repair_attempt_limit: int,
    ) -> None:
        self.connection = connection
        self.quota_budget = quota_budget
        self.maximum_requests = maximum_requests
        self.repair_attempt_limit = repair_attempt_limit

    def plan(
        self,
        *,
        ledger_mode: str,
        estimated_mandatory_requests: int = 0,
        provider_season: int | None = None,
        provider_seasons: tuple[int, ...] | None = None,
    ) -> BackfillPlan:
        if provider_season is not None and provider_seasons is not None:
            raise ValueError("Use provider_season or provider_seasons, not both")
        request_budget = self.quota_budget.backfill_budget(
            estimated_mandatory_requests,
            self.maximum_requests,
        )
        season_clause = ""
        parameters: list[Any] = [ledger_mode]
        if provider_season is not None:
            season_clause = "AND cs.provider_season=? "
            parameters.append(provider_season)
        elif provider_seasons is not None:
            if not provider_seasons:
                return BackfillPlan((), request_budget, 0)
            placeholders = ",".join("?" for _ in provider_seasons)
            season_clause = f"AND cs.provider_season IN ({placeholders}) "
            parameters.extend(provider_seasons)
        parameters.extend((self.repair_attempt_limit, datetime.now(UTC)))
        rows = self.connection.execute(
            "SELECT f.provider_fixture_id FROM fixtures_current f "
            "JOIN competition_seasons cs USING (competition_season_id) "
            "LEFT JOIN fixture_quality_status q USING (fixture_id) "
            "LEFT JOIN fixture_repair_state r USING (fixture_id) "
            "WHERE cs.ledger_mode=? AND f.status_short IN ('FT', 'AET', 'PEN') "
            "AND coalesce(q.eligibility, 'PENDING_REPAIR') <> 'ML_ELIGIBLE' "
            f"{season_clause}"
            "AND coalesce(r.attempt_count, 0) < ? "
            "AND (r.next_retry_after IS NULL OR r.next_retry_after <= ?) "
            "ORDER BY coalesce(r.attempt_count, 0), f.kickoff_utc DESC",
            parameters,
        ).fetchall()
        candidate_count = len(rows)
        # One batched /fixtures call covers up to twenty IDs and includes all
        # provider-supplied enrichment. Optional team/player detail must never
        # trigger fixture-scoped repair calls merely to make a completed score
        # usable for modelling.
        fixture_capacity = request_budget * 20
        selected = tuple(int(row[0]) for row in rows[:fixture_capacity])
        return BackfillPlan(selected, request_budget, candidate_count)
