from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MarketSnapshotKey:
    fixture_id: str
    bookmaker_id: str
    market_id: str
    selection_id: str
    observed_at: datetime
