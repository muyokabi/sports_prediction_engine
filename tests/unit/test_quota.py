from datetime import UTC, datetime, timedelta

import pytest

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import QuotaExhaustedError
from sports_engine.providers.api_football.quota import QuotaObservation
from sports_engine.quota.budget import QuotaBudget, QuotaPolicy


def observation(daily: int, minute: int) -> QuotaObservation:
    return QuotaObservation(100, daily, 10, minute, datetime.now(UTC))


def test_discretionary_work_preserves_reserves() -> None:
    budget = QuotaBudget(QuotaPolicy(10, 2), observation(10, 5))
    with pytest.raises(QuotaExhaustedError, match="daily reserve"):
        budget.authorize(Priority.P5)


def test_mandatory_work_can_use_reserve() -> None:
    QuotaBudget(QuotaPolicy(10, 2), observation(10, 2)).authorize(Priority.P1)


def test_backfill_budget_subtracts_reserve_and_mandatory_work() -> None:
    budget = QuotaBudget(QuotaPolicy(10, 2), observation(77, 8))
    assert budget.backfill_budget(17, 40) == 40
    assert budget.backfill_budget(60, 40) == 7


def test_quota_headers_are_case_insensitive() -> None:
    result = QuotaObservation.from_headers(
        {
            "X-RateLimit-Requests-Limit": "100",
            "x-ratelimit-requests-remaining": "88",
            "X-RateLimit-Limit": "10",
            "x-ratelimit-remaining": "7",
        },
        datetime.now(UTC),
    )
    assert (
        result.daily_limit,
        result.daily_remaining,
        result.minute_limit,
        result.minute_remaining,
    ) == (100, 88, 10, 7)


def test_stale_minute_observation_uses_reset_limit() -> None:
    now = datetime(2026, 10, 7, 12, 1, 1, tzinfo=UTC)
    stale = QuotaObservation(100, 50, 10, 2, now - timedelta(seconds=61))
    QuotaBudget(QuotaPolicy(10, 2), stale, clock=lambda: now).authorize(Priority.P5)


def test_new_utc_day_uses_daily_reset_limit() -> None:
    now = datetime(2026, 10, 8, 0, 0, 1, tzinfo=UTC)
    stale = QuotaObservation(100, 0, 10, 0, now - timedelta(days=1))
    budget = QuotaBudget(QuotaPolicy(10, 2), stale, clock=lambda: now)
    budget.authorize(Priority.P5)
    assert budget.backfill_budget(20, 100) == 70
