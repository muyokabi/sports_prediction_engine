from typing import Any

from sports_engine.sports.football.domain.player_stats import PlayerMatchStatistics


def normalize_player_statistics(payload: dict[str, Any]) -> list[PlayerMatchStatistics]:
    provider_team_id = payload["team"]["id"]
    result: list[PlayerMatchStatistics] = []
    for item in payload.get("players", []):
        player = item["player"]
        statistics = item.get("statistics") or []
        if statistics:
            result.append(
                PlayerMatchStatistics(
                    provider_team_id=provider_team_id,
                    provider_player_id=player["id"],
                    player_name=player["name"],
                    statistics=statistics[0],
                )
            )
    return result
