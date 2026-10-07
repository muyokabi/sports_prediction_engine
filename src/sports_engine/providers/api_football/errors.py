from collections.abc import Mapping
from typing import Any

from sports_engine.core.exceptions import (
    ProviderAuthenticationError,
    ProviderInvalidParametersError,
    ProviderMalformedResponseError,
    ProviderPlanAccessError,
)


class ApiFootballPlanRestrictionError(ProviderPlanAccessError):
    """A structured API-Football subscription/season access failure."""

    def __init__(
        self,
        *,
        endpoint: str,
        parameters: Mapping[str, Any],
        provider_message: str,
        subscription_plan: str | None = None,
        job_run_id: str | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.parameters = dict(parameters)
        requested = self.parameters.get("season")
        self.requested_season = int(requested) if requested is not None else None
        self.provider_message = provider_message
        self.subscription_plan = subscription_plan
        self.job_run_id = job_run_id
        plan = f" plan={subscription_plan}" if subscription_plan else ""
        season = f" season={self.requested_season}" if self.requested_season is not None else ""
        super().__init__(f"API-Football plan restriction:{plan}{season} endpoint={endpoint}: {provider_message}")


class ApiFootballAuthenticationError(ProviderAuthenticationError):
    """API-Football authentication failure."""


class ApiFootballInvalidParametersError(ProviderInvalidParametersError):
    """API-Football parameter validation failure."""


class ApiFootballMalformedResponseError(ProviderMalformedResponseError):
    """API-Football wrapper validation failure."""
