from dataclasses import dataclass
from typing import Any

from sports_engine.core.enums import CompletenessState, Eligibility

REQUIRED_COMPONENTS = (
    "fixture_metadata",
    "final_score",
    "events",
    "goalscorers",
    "assists",
    "cards",
    "substitutions",
    "home_lineup",
    "away_lineup",
    "home_bench",
    "away_bench",
    "home_team_stats",
    "away_team_stats",
    "home_player_stats",
    "away_player_stats",
)
MANDATORY_TEAM_STATISTICS = (
    "Shots on Goal",
    "Total Shots",
    "Fouls",
    "Corner Kicks",
    "Offsides",
    "Ball Possession",
    "Total passes",
    "Passes accurate",
    "Passes %",
)
MANDATORY_PLAYER_PATHS = (
    ("games", "minutes"),
    ("games", "rating"),
    ("shots", "total"),
    ("shots", "on"),
    ("passes", "total"),
    ("passes", "key"),
    ("tackles", "total"),
    ("tackles", "interceptions"),
    ("duels", "total"),
    ("duels", "won"),
    ("dribbles", "attempts"),
    ("dribbles", "success"),
    ("fouls", "drawn"),
    ("fouls", "committed"),
    ("cards", "yellow"),
    ("cards", "red"),
    ("penalty", "scored"),
    ("penalty", "missed"),
    ("penalty", "saved"),
)


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    components: dict[str, CompletenessState]
    eligibility: Eligibility
    missing: tuple[str, ...]


def _lineups_complete(lineups: object) -> bool:
    return (
        isinstance(lineups, list)
        and len(lineups) >= 2
        and all(
            isinstance(item.get("startXI"), list)
            and len(item["startXI"]) == 11
            and isinstance(item.get("substitutes"), list)
            for item in lineups
        )
    )


def _team_statistics_complete(statistics: object) -> bool:
    if not isinstance(statistics, list) or len(statistics) < 2:
        return False
    for team in statistics:
        values = {item.get("type"): item.get("value") for item in team.get("statistics", [])}
        if any(name not in values or values[name] is None for name in MANDATORY_TEAM_STATISTICS):
            return False
    return True


def _nested_value(payload: dict[str, Any], path: tuple[str, str]) -> Any:
    section = payload.get(path[0])
    return section.get(path[1]) if isinstance(section, dict) else None


def _player_statistics_complete(players: object) -> bool:
    if not isinstance(players, list) or len(players) < 2:
        return False
    for team in players:
        rows = team.get("players")
        if not isinstance(rows, list) or not rows:
            return False
        for row in rows:
            statistics = row.get("statistics")
            if not isinstance(statistics, list) or not statistics:
                return False
            if any(_nested_value(statistics[0], path) is None for path in MANDATORY_PLAYER_PATHS):
                return False
    return True


def assess_match_package(payload: dict[str, Any]) -> QualityAssessment:
    fixture = payload.get("fixture") or {}
    status = (fixture.get("status") or {}).get("short")
    goals = payload.get("goals") or {}
    events = payload.get("events")
    event_state = CompletenessState.COMPLETE if isinstance(events, list) else CompletenessState.INCOMPLETE
    lineups_complete = _lineups_complete(payload.get("lineups"))
    team_stats_complete = _team_statistics_complete(payload.get("statistics"))
    player_stats_complete = _player_statistics_complete(payload.get("players"))
    components = {
        "fixture_metadata": CompletenessState.COMPLETE
        if fixture.get("id") and fixture.get("date")
        else CompletenessState.INCOMPLETE,
        "final_score": CompletenessState.COMPLETE
        if status in {"FT", "AET", "PEN"} and goals.get("home") is not None and goals.get("away") is not None
        else CompletenessState.INCOMPLETE,
        "events": event_state,
        "goalscorers": event_state,
        "assists": event_state,
        "cards": event_state,
        "substitutions": event_state,
        "home_lineup": CompletenessState.COMPLETE if lineups_complete else CompletenessState.INCOMPLETE,
        "away_lineup": CompletenessState.COMPLETE if lineups_complete else CompletenessState.INCOMPLETE,
        "home_bench": CompletenessState.COMPLETE if lineups_complete else CompletenessState.INCOMPLETE,
        "away_bench": CompletenessState.COMPLETE if lineups_complete else CompletenessState.INCOMPLETE,
        "home_team_stats": CompletenessState.COMPLETE if team_stats_complete else CompletenessState.INCOMPLETE,
        "away_team_stats": CompletenessState.COMPLETE if team_stats_complete else CompletenessState.INCOMPLETE,
        "home_player_stats": CompletenessState.COMPLETE if player_stats_complete else CompletenessState.INCOMPLETE,
        "away_player_stats": CompletenessState.COMPLETE if player_stats_complete else CompletenessState.INCOMPLETE,
    }
    missing = tuple(name for name in REQUIRED_COMPONENTS if components[name] != CompletenessState.COMPLETE)
    eligibility = Eligibility.ML_ELIGIBLE if not missing else Eligibility.PENDING_REPAIR
    return QualityAssessment(components, eligibility, missing)
