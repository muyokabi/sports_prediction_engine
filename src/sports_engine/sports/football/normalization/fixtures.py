from typing import Any

from sports_engine.sports.football.domain.fixture import FixtureRecord


def normalize_fixture(payload: dict[str, Any]) -> FixtureRecord:
    fixture = payload["fixture"]
    league = payload["league"]
    teams = payload["teams"]
    goals = payload.get("goals") or {}
    score = payload.get("score") or {}
    halftime = score.get("halftime") or {}
    fulltime = score.get("fulltime") or {}
    extratime = score.get("extratime") or {}
    penalty = score.get("penalty") or {}
    return FixtureRecord(
        provider_fixture_id=fixture["id"],
        provider_competition_id=league["id"],
        provider_season=league["season"],
        round=league.get("round"),
        kickoff_utc=fixture["date"],
        status_short=fixture["status"]["short"],
        status_long=fixture["status"].get("long"),
        elapsed=fixture["status"].get("elapsed"),
        home_provider_team_id=teams["home"]["id"],
        home_team_name=teams["home"]["name"],
        away_provider_team_id=teams["away"]["id"],
        away_team_name=teams["away"]["name"],
        home_goals=goals.get("home"),
        away_goals=goals.get("away"),
        halftime_home=halftime.get("home"),
        halftime_away=halftime.get("away"),
        fulltime_home=fulltime.get("home"),
        fulltime_away=fulltime.get("away"),
        extratime_home=extratime.get("home"),
        extratime_away=extratime.get("away"),
        penalty_home=penalty.get("home"),
        penalty_away=penalty.get("away"),
    )
