from typing import Any

from sports_engine.sports.football.domain.team_stats import TeamMatchStatistics

STATISTIC_FIELDS = {
    "Shots on Goal": "shots_on_goal",
    "Shots off Goal": "shots_off_goal",
    "Total Shots": "total_shots",
    "Blocked Shots": "blocked_shots",
    "Shots insidebox": "shots_inside_box",
    "Shots outsidebox": "shots_outside_box",
    "Fouls": "fouls",
    "Corner Kicks": "corner_kicks",
    "Offsides": "offsides",
    "Ball Possession": "ball_possession",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Goalkeeper Saves": "goalkeeper_saves",
    "Total passes": "total_passes",
    "Passes accurate": "passes_accurate",
    "Passes %": "passes_percentage",
}


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.endswith("%"):
        value = value[:-1]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_team_statistics(payload: dict[str, Any]) -> TeamMatchStatistics:
    values = {item.get("type"): item.get("value") for item in payload.get("statistics", [])}
    known = {field: _number(values.get(provider_name)) for provider_name, field in STATISTIC_FIELDS.items()}
    additional = {key: value for key, value in values.items() if key not in STATISTIC_FIELDS}
    return TeamMatchStatistics(provider_team_id=payload["team"]["id"], additional_stats=additional, **known)
