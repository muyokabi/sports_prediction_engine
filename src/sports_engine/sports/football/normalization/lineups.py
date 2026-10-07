from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LineupPlayer:
    provider_player_id: int
    name: str
    number: int | None
    position: str | None
    grid: str | None
    role: str


@dataclass(frozen=True, slots=True)
class LineupRecord:
    provider_team_id: int
    provider_coach_id: int | None
    coach_name: str | None
    formation: str | None
    players: tuple[LineupPlayer, ...]
    source_payload: dict[str, Any]


def normalize_lineup(payload: dict[str, Any]) -> LineupRecord:
    players: list[LineupPlayer] = []
    for source_name, role in (("startXI", "STARTING_XI"), ("substitutes", "BENCH")):
        for item in payload.get(source_name) or []:
            player = item.get("player") or {}
            if player.get("id") is None:
                continue
            players.append(
                LineupPlayer(
                    provider_player_id=int(player["id"]),
                    name=str(player.get("name") or f"Player {player['id']}"),
                    number=player.get("number"),
                    position=player.get("pos"),
                    grid=player.get("grid"),
                    role=role,
                )
            )
    team = payload.get("team") or {}
    coach = payload.get("coach") or {}
    return LineupRecord(
        provider_team_id=int(team["id"]),
        provider_coach_id=int(coach["id"]) if coach.get("id") is not None else None,
        coach_name=coach.get("name"),
        formation=payload.get("formation"),
        players=tuple(players),
        source_payload=payload,
    )
