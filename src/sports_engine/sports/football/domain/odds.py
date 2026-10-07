from datetime import datetime

from pydantic import BaseModel, Field


class OddsPrice(BaseModel):
    provider_fixture_id: int
    provider_bookmaker_id: int
    bookmaker_name: str
    provider_market_id: int
    market_name: str
    selection_name: str
    line: str | None = None
    decimal_odds: float = Field(gt=1.0)
    provider_update_time: datetime | None = None
