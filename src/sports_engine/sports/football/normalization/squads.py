from typing import Any

from sports_engine.sports.football.domain.player import SquadPlayerRecord


def normalize_squad(payload: dict[str, Any]) -> tuple[int, list[SquadPlayerRecord]]:
    team_id = int(payload["team"]["id"])
    players = [
        SquadPlayerRecord(
            provider_player_id=item["id"],
            name=item["name"],
            age=item.get("age"),
            squad_number=item.get("number"),
            position=item.get("position"),
            photo_url=item.get("photo"),
        )
        for item in payload.get("players", [])
    ]
    return team_id, players
