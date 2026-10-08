from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import duckdb

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import QuotaExhaustedError
from sports_engine.providers.base import SportsDataProvider
from sports_engine.quota.budget import QuotaBudget


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
    ) -> BackfillPlan:
        request_budget = self.quota_budget.backfill_budget(
            estimated_mandatory_requests,
            self.maximum_requests,
        )
        rows = self.connection.execute(
            "SELECT f.provider_fixture_id FROM fixtures_current f "
            "JOIN competition_seasons cs USING (competition_season_id) "
            "LEFT JOIN fixture_quality_status q USING (fixture_id) "
            "LEFT JOIN fixture_repair_state r USING (fixture_id) "
            "WHERE cs.ledger_mode=? AND f.status_short IN ('FT', 'AET', 'PEN') "
            "AND coalesce(q.eligibility, 'PENDING_REPAIR') <> 'ML_ELIGIBLE' "
            "AND coalesce(r.attempt_count, 0) < ? "
            "AND (r.next_retry_after IS NULL OR r.next_retry_after <= ?) "
            "ORDER BY coalesce(r.attempt_count, 0), f.kickoff_utc DESC",
            [ledger_mode, self.repair_attempt_limit, datetime.now(UTC)],
        ).fetchall()
        candidate_count = len(rows)
        fixture_capacity = request_budget * 20
        selected = tuple(int(row[0]) for row in rows[:fixture_capacity])
        return BackfillPlan(selected, request_budget, candidate_count)
