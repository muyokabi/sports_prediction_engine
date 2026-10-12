from dataclasses import dataclass
from typing import Any

from sports_engine.core.enums import CompletenessState, Eligibility

# A completed result is the minimum trustworthy modelling record.  The
# remaining components are enrichment tiers: useful when present, but API-
# Football's season-level coverage flags do not guarantee them for each match.
# Keeping optional enrichment in this tuple previously caused one player/stats
# request per fixture and discarded valid score-model observations.
REQUIRED_COMPONENTS = (
    "fixture_metadata",
    "final_score",
)
ENRICHMENT_COMPONENTS = (
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
# Paid/current-season qualification established that API-Football uses NULL for
# unperformed actions and non-applicable roles. Participation identity and
# minutes are the required core; analytic/action fields remain nullable.
PLAYER_REQUIRED_CORE = (("games", "minutes"),)


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


def _player_statistics_complete(payload: dict[str, Any]) -> bool:
    players = payload.get("players")
    if not isinstance(players, list) or len(players) < 2:
        return False
    required_participants: set[int] = set()
    lineups = payload.get("lineups")
    if not isinstance(lineups, list) or len(lineups) < 2:
        return False
    for lineup in lineups:
        for item in lineup.get("startXI") or []:
            player = item.get("player") or {}
            if player.get("id") is not None:
                required_participants.add(int(player["id"]))
    for event in payload.get("events") or []:
        if str(event.get("type", "")).lower() in {"subst", "substitution"}:
            incoming = event.get("assist") or {}
            if incoming.get("id") is not None:
                required_participants.add(int(incoming["id"]))
    observed_participants: set[int] = set()
    for team in players:
        rows = team.get("players")
        if not isinstance(rows, list) or not rows:
            return False
        for row in rows:
            player = row.get("player") or {}
            statistics = row.get("statistics")
            if not isinstance(statistics, list) or not statistics:
                continue
            if player.get("id") is not None and all(
                _nested_value(statistics[0], path) is not None for path in PLAYER_REQUIRED_CORE
            ):
                observed_participants.add(int(player["id"]))
    return bool(required_participants) and required_participants <= observed_participants


def assess_match_package(payload: dict[str, Any]) -> QualityAssessment:
    fixture = payload.get("fixture") or {}
    status = (fixture.get("status") or {}).get("short")
    goals = payload.get("goals") or {}
    events = payload.get("events")
    event_state = CompletenessState.COMPLETE if isinstance(events, list) else CompletenessState.INCOMPLETE
    lineups_complete = _lineups_complete(payload.get("lineups"))
    team_stats_complete = _team_statistics_complete(payload.get("statistics"))
    player_stats_complete = _player_statistics_complete(payload)
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
