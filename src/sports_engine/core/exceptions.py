"""Typed application failures."""


class SportsEngineError(Exception):
    """Base application error."""


class ConfigurationError(SportsEngineError):
    """Configuration is invalid or unavailable."""


class ProviderError(SportsEngineError):
    """Provider request or payload failed validation."""


class ProviderUnavailableError(ProviderError):
    """Provider could not be reached after transport retries were exhausted."""


class ProviderRateLimitError(ProviderError):
    """Provider refused a request because of a rate limit."""


class ProviderPlanAccessError(ProviderError):
    """The configured provider subscription cannot access requested data."""


class ProviderAuthenticationError(ProviderError):
    """Provider credentials are missing, invalid, or unauthorized."""


class ProviderInvalidParametersError(ProviderError):
    """Provider rejected request parameters."""


class ProviderMalformedResponseError(ProviderError):
    """Provider response is not valid JSON or violates its wrapper contract."""


class QuotaExhaustedError(SportsEngineError):
    """A request would violate a protected quota reserve."""


class DataQualityError(SportsEngineError):
    """Normalized data failed mandatory quality rules."""


class NoEligibleModelError(SportsEngineError):
    """No production-eligible champion model is available."""


class LeakageError(SportsEngineError):
    """A dataset violates point-in-time constraints."""
