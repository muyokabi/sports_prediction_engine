from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FixtureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_fixture_id: int
    provider_competition_id: int
    provider_season: int
    round: str | None
    kickoff_utc: datetime
    status_short: str
    status_long: str | None
    elapsed: int | None
    home_provider_team_id: int
    home_team_name: str
    away_provider_team_id: int
    away_team_name: str
    home_goals: int | None
    away_goals: int | None
    halftime_home: int | None = None
    halftime_away: int | None = None
    fulltime_home: int | None = None
    fulltime_away: int | None = None
    extratime_home: int | None = None
    extratime_away: int | None = None
    penalty_home: int | None = None
    penalty_away: int | None = None
