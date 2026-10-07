from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProviderCapabilities(BaseModel):
    """Observed provider subscription and quota state without plan-based assumptions."""

    model_config = ConfigDict(frozen=True)

    provider: str
    subscription_plan: str | None = None
    subscription_active: bool | None = None
    subscription_end: str | None = None
    requests_used_today: int | None = None
    daily_limit: int | None = None
    daily_remaining: int | None = None
    minute_limit: int | None = None
    minute_remaining: int | None = None
    observed_at: datetime
