from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackfillPlan:
    estimated_mandatory_requests: int
    available_backfill_requests: int
    reason: str
