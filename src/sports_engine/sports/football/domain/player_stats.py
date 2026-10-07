from typing import Any

from pydantic import BaseModel


class PlayerMatchStatistics(BaseModel):
    provider_team_id: int
    provider_player_id: int
    player_name: str
    statistics: dict[str, Any]
