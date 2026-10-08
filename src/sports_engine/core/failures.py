from enum import StrEnum

import duckdb

from sports_engine.core.exceptions import (
    DataQualityError,
    NoEligibleModelError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderPlanAccessError,
    ProviderRateLimitError,
    QuotaExhaustedError,
)


class FailureCategory(StrEnum):
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    QUOTA_EXHAUSTION = "QUOTA_EXHAUSTION"
    PLAN_RESTRICTION = "PLAN_RESTRICTION"
    DATABASE_INTEGRITY_FAILURE = "DATABASE_INTEGRITY_FAILURE"
    FIXTURE_INGESTION_FAILURE = "FIXTURE_INGESTION_FAILURE"
    ODDS_INGESTION_FAILURE = "ODDS_INGESTION_FAILURE"
    NO_ELIGIBLE_MODEL = "NO_ELIGIBLE_MODEL"
    PREDICTION_FAILURE = "PREDICTION_FAILURE"
    BACKUP_FAILURE = "BACKUP_FAILURE"
    UNCLASSIFIED_FAILURE = "UNCLASSIFIED_FAILURE"


def classify_failure(exc: Exception, job_name: str = "") -> FailureCategory:
    if isinstance(exc, ProviderAuthenticationError):
        return FailureCategory.AUTHENTICATION_FAILURE
    if isinstance(exc, (ProviderRateLimitError, QuotaExhaustedError)):
        return FailureCategory.QUOTA_EXHAUSTION
    if isinstance(exc, ProviderPlanAccessError):
        return FailureCategory.PLAN_RESTRICTION
    if isinstance(exc, duckdb.Error):
        return FailureCategory.DATABASE_INTEGRITY_FAILURE
    if isinstance(exc, DataQualityError):
        return FailureCategory.FIXTURE_INGESTION_FAILURE
    if isinstance(exc, NoEligibleModelError):
        return FailureCategory.NO_ELIGIBLE_MODEL
    if isinstance(exc, ProviderError):
        return FailureCategory.PROVIDER_UNAVAILABLE
    if "odds" in job_name:
        return FailureCategory.ODDS_INGESTION_FAILURE
    if "predict" in job_name:
        return FailureCategory.PREDICTION_FAILURE
    if "backup" in job_name:
        return FailureCategory.BACKUP_FAILURE
    return FailureCategory.UNCLASSIFIED_FAILURE
