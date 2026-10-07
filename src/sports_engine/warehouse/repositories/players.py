import hashlib
import json
import uuid
from datetime import UTC, datetime

import duckdb

from sports_engine.core.ids import canonical_id
from sports_engine.sports.football.domain.player import SquadPlayerRecord

PROVIDER_ID = "8d39dc64-2491-5b70-9fb8-2b0b379b2026"


def store_squad_snapshot(
    connection: duckdb.DuckDBPyConnection,
    *,
    competition_season_id: str,
    provider_team_id: int,
    players: list[SquadPlayerRecord],
    source_raw_path: str,
    observed_at: datetime | None = None,
) -> str:
    observed = observed_at or datetime.now(UTC)
    team_id = canonical_id("team", "api_football", provider_team_id)
    content = [player.model_dump(mode="json") for player in players]
    content_hash = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    snapshot_id = uuid.uuid5(
        canonical_id("squad", "api_football", f"{competition_season_id}:{provider_team_id}"),
        f"{observed.isoformat()}:{content_hash}",
    )
    connection.execute(
        "INSERT INTO squad_snapshots VALUES (?, ?, ?, ?, ?, ?)",
        [snapshot_id, competition_season_id, team_id, observed, source_raw_path, content_hash],
    )
    for player in players:
        player_id = canonical_id("player", "api_football", player.provider_player_id)
        connection.execute(
            "INSERT INTO players (player_id, name, updated_at, source_raw_path, retrieved_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (player_id) DO UPDATE SET name=excluded.name, "
            "updated_at=excluded.updated_at, source_raw_path=excluded.source_raw_path, "
            "retrieved_at=excluded.retrieved_at",
            [player_id, player.name, observed, source_raw_path, observed],
        )
        connection.execute(
            "INSERT INTO provider_entity_map VALUES (?, 'player', ?, ?, ?, ?) "
            "ON CONFLICT (provider_id, entity_type, provider_entity_id) DO UPDATE SET "
            "canonical_entity_id=excluded.canonical_entity_id, last_seen_at=excluded.last_seen_at",
            [PROVIDER_ID, str(player.provider_player_id), player_id, observed, observed],
        )
        connection.execute(
            "INSERT INTO squad_players VALUES (?, ?, ?, ?)",
            [snapshot_id, player_id, player.squad_number, player.position],
        )
    return str(snapshot_id)
