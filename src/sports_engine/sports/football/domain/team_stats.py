from typing import Any

from pydantic import BaseModel


class TeamMatchStatistics(BaseModel):
    provider_team_id: int
    shots_on_goal: float | None = None
    shots_off_goal: float | None = None
    total_shots: float | None = None
    blocked_shots: float | None = None
    shots_inside_box: float | None = None
    shots_outside_box: float | None = None
    fouls: float | None = None
    corner_kicks: float | None = None
    offsides: float | None = None
    ball_possession: float | None = None
    yellow_cards: float | None = None
    red_cards: float | None = None
    goalkeeper_saves: float | None = None
    total_passes: float | None = None
    passes_accurate: float | None = None
    passes_percentage: float | None = None
    additional_stats: dict[str, Any]
