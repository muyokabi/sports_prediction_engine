import uuid
from typing import Any

from sports_engine.core.ids import canonical_id


def normalize_events(provider_fixture_id: int, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fixture_id = canonical_id("fixture", "api_football", provider_fixture_id)
    normalized: list[dict[str, Any]] = []
    for sequence, event in enumerate(events):
        team = event.get("team") or {}
        player = event.get("player") or {}
        assist = event.get("assist") or {}
        event_key = f"{provider_fixture_id}:{sequence}:{event.get('type')}:{event.get('detail')}"
        normalized.append(
            {
                "event_id": uuid.uuid5(fixture_id, event_key),
                "fixture_id": fixture_id,
                "team_id": canonical_id("team", "api_football", team["id"]) if team.get("id") else None,
                "player_id": canonical_id("player", "api_football", player["id"]) if player.get("id") else None,
                "assist_player_id": canonical_id("player", "api_football", assist["id"]) if assist.get("id") else None,
                "elapsed": (event.get("time") or {}).get("elapsed"),
                "extra": (event.get("time") or {}).get("extra"),
                "event_type": event.get("type"),
                "detail": event.get("detail"),
                "comments": event.get("comments"),
                "provider_sequence": sequence,
                "source_payload": event,
            }
        )
    return normalized
