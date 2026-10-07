from enum import StrEnum


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    P5 = "P5"
    P6 = "P6"


class CompletenessState(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    NOT_EXPECTED = "not_expected"
    UNAVAILABLE = "unavailable_from_provider"
    PENDING = "pending"
    QUARANTINED = "quarantined"


class Eligibility(StrEnum):
    ML_ELIGIBLE = "ML_ELIGIBLE"
    NOT_ML_ELIGIBLE = "NOT_ML_ELIGIBLE"
    PENDING_REPAIR = "PENDING_REPAIR"


class ProductionReadiness(StrEnum):
    IMPLEMENTATION_IN_PROGRESS = "IMPLEMENTATION_IN_PROGRESS"
    BLOCKED_BY_PROVIDER_PLAN = "BLOCKED_BY_PROVIDER_PLAN"
    PRODUCTION_READY_AWAITING_CURRENT_SEASON_PROVIDER_ACCESS = (
        "PRODUCTION_READY_AWAITING_CURRENT_SEASON_PROVIDER_ACCESS"
    )
    PRODUCTION_VERIFIED = "PRODUCTION_VERIFIED"
