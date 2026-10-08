from typing import Any

from sports_engine.sports.football.domain.player_stats import PlayerMatchStatistics


def normalize_player_statistics(payload: dict[str, Any]) -> list[PlayerMatchStatistics]:
    provider_team_id = payload["team"]["id"]
    result: list[PlayerMatchStatistics] = []
    for item in payload.get("players", []):
        player = item["player"]
        # API-Football can emit multiple distinct placeholder players with id=0.
        # They cannot be assigned a stable canonical identity; retain them in raw
        # lineage but exclude them from the canonical player-stat grain.
        if not isinstance(player.get("id"), int) or player["id"] <= 0:
            continue
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
