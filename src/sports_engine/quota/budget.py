from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import QuotaExhaustedError
from sports_engine.providers.api_football.quota import QuotaObservation
from sports_engine.quota.priorities import DISCRETIONARY


@dataclass(frozen=True, slots=True)
class QuotaPolicy:
    minimum_daily_reserve: int
    minimum_minute_reserve: int


class QuotaBudget:
    def __init__(
        self,
        policy: QuotaPolicy,
        observation: QuotaObservation | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.policy = policy
        self.observation = observation
        self.clock = clock or (lambda: datetime.now(UTC))

    def update(self, observation: QuotaObservation) -> None:
        self.observation = observation

    def authorize(self, priority: Priority, cost: int = 1) -> None:
        if not self.observation:
            return
        daily, minute = self._effective_remaining()
        if daily is not None and daily < cost:
            raise QuotaExhaustedError("Provider daily quota is exhausted")
        if minute is not None and minute < cost:
            raise QuotaExhaustedError("Provider minute quota is exhausted")
        if priority in DISCRETIONARY:
            if daily is not None and daily - cost < self.policy.minimum_daily_reserve:
                raise QuotaExhaustedError("Request would violate protected daily reserve")
            if minute is not None and minute - cost < self.policy.minimum_minute_reserve:
                raise QuotaExhaustedError("Request would violate protected minute reserve")

    def backfill_budget(self, estimated_mandatory_requests: int, maximum: int) -> int:
        if not self.observation:
            return 0
        daily, _ = self._effective_remaining()
        if daily is None:
            return 0
        available = daily - self.policy.minimum_daily_reserve - estimated_mandatory_requests
        return max(0, min(maximum, available))

    def _effective_remaining(self) -> tuple[int | None, int | None]:
        if not self.observation:
            return None, None
        now = self.clock().astimezone(UTC)
        observed = self.observation.observed_at.astimezone(UTC)
        daily = self.observation.daily_remaining
        minute = self.observation.minute_remaining
        if now.date() > observed.date() and self.observation.daily_limit is not None:
            daily = self.observation.daily_limit
        if now - observed >= timedelta(minutes=1) and self.observation.minute_limit is not None:
            minute = self.observation.minute_limit
        return daily, minute
