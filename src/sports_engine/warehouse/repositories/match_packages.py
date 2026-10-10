import json
from datetime import UTC, datetime
from typing import Any

import duckdb

from sports_engine.core.ids import canonical_id
from sports_engine.sports.football.normalization.events import normalize_events
from sports_engine.sports.football.normalization.lineups import normalize_lineup
from sports_engine.sports.football.normalization.player_stats import normalize_player_statistics
from sports_engine.sports.football.normalization.team_stats import normalize_team_statistics
from sports_engine.sports.football.quality.completeness import QualityAssessment


def persist_match_package(
    connection: duckdb.DuckDBPyConnection,
    payload: dict[str, Any],
    assessment: QualityAssessment,
    *,
    source_raw_path: str,
    retrieved_at: datetime | None = None,
) -> str:
    observed = retrieved_at or datetime.now(UTC)
    provider_fixture_id = int(payload["fixture"]["id"])
    row = connection.execute(
        "SELECT CAST(fixture_id AS VARCHAR) FROM fixtures WHERE provider_fixture_id=?",
        [provider_fixture_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"Fixture {provider_fixture_id} is not present in the ledger")
    fixture_id = row[0]
    _replace_events(connection, fixture_id, provider_fixture_id, payload.get("events") or [], source_raw_path, observed)
    _replace_lineups(connection, fixture_id, payload.get("lineups") or [], source_raw_path, observed)
    _replace_team_statistics(connection, fixture_id, payload.get("statistics") or [], source_raw_path, observed)
    _replace_player_statistics(connection, fixture_id, payload.get("players") or [], source_raw_path, observed)
    _replace_completeness(connection, fixture_id, assessment, source_raw_path, observed)
    connection.execute(
        "INSERT INTO fixture_quality_status VALUES (?, ?, ?, ?) "
        "ON CONFLICT (fixture_id) DO UPDATE SET eligibility=excluded.eligibility, "
        "assessed_at=excluded.assessed_at, source_raw_path=excluded.source_raw_path",
        [fixture_id, assessment.eligibility.value, observed, source_raw_path],
    )
    return fixture_id


def _ensure_player(
    connection: duckdb.DuckDBPyConnection,
    provider_player_id: int,
    name: str,
    source_raw_path: str,
    observed: datetime,
) -> object:
    player_id = canonical_id("player", "api_football", provider_player_id)
    connection.execute(
        "INSERT INTO players (player_id, name, updated_at, source_raw_path, retrieved_at) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT (player_id) DO UPDATE SET name=excluded.name, "
        "updated_at=excluded.updated_at, source_raw_path=excluded.source_raw_path, retrieved_at=excluded.retrieved_at",
        [player_id, name, observed, source_raw_path, observed],
    )
    return player_id


def _ensure_team(
    connection: duckdb.DuckDBPyConnection,
    provider_team_id: int,
    name: str,
    source_raw_path: str,
    observed: datetime,
) -> object:
    team_id = canonical_id("team", "api_football", provider_team_id)
    connection.execute(
        "INSERT INTO teams (team_id, name, updated_at, source_raw_path, retrieved_at) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT (team_id) DO UPDATE SET "
        "name=excluded.name, updated_at=excluded.updated_at, "
        "source_raw_path=excluded.source_raw_path, retrieved_at=excluded.retrieved_at",
        [team_id, name, observed, source_raw_path, observed],
    )
    return team_id


def _replace_events(
    connection: duckdb.DuckDBPyConnection,
    fixture_id: str,
    provider_fixture_id: int,
    payloads: list[dict[str, Any]],
    source_raw_path: str,
    observed: datetime,
) -> None:
    connection.execute("DELETE FROM fixture_events WHERE fixture_id=?", [fixture_id])
    for payload in payloads:
        for key in ("player", "assist"):
            player = payload.get(key) or {}
            if player.get("id") is not None:
                _ensure_player(
                    connection,
                    int(player["id"]),
                    str(player.get("name") or f"Player {player['id']}"),
                    source_raw_path,
                    observed,
                )
    for event in normalize_events(provider_fixture_id, payloads):
        connection.execute(
            "INSERT INTO fixture_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                event["event_id"],
                event["fixture_id"],
                event["team_id"],
                event["player_id"],
                event["assist_player_id"],
                event["elapsed"],
                event["extra"],
                event["event_type"],
                event["detail"],
                event["comments"],
                event["provider_sequence"],
                json.dumps(event["source_payload"]),
                source_raw_path,
                observed,
            ],
        )


def _replace_lineups(
    connection: duckdb.DuckDBPyConnection,
    fixture_id: str,
    payloads: list[dict[str, Any]],
    source_raw_path: str,
    observed: datetime,
) -> None:
    connection.execute(
        "DELETE FROM lineup_players WHERE lineup_id IN (SELECT lineup_id FROM lineups WHERE fixture_id=?)",
        [fixture_id],
    )
    for payload in payloads:
        record = normalize_lineup(payload)
        team_id = canonical_id("team", "api_football", record.provider_team_id)
        lineup_id = canonical_id("lineup", "api_football", f"{fixture_id}:{record.provider_team_id}")
        coach_id = None
        if record.provider_coach_id is not None:
            coach_id = canonical_id("coach", "api_football", record.provider_coach_id)
            connection.execute(
                "INSERT INTO coaches VALUES (?, ?, NULL, ?) ON CONFLICT (coach_id) DO UPDATE SET "
                "name=excluded.name, updated_at=excluded.updated_at",
                [coach_id, record.coach_name or f"Coach {record.provider_coach_id}", observed],
            )
        connection.execute(
            "INSERT INTO lineups VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (lineup_id) DO NOTHING",
            [
                lineup_id,
                fixture_id,
                team_id,
                coach_id,
                record.formation,
                json.dumps(record.source_payload),
                source_raw_path,
                observed,
            ],
        )
        observation_id = canonical_id(
            "lineup_observation",
            "api_football",
            f"{lineup_id}:{observed.isoformat()}:{source_raw_path}",
        )
        connection.execute(
            "INSERT INTO lineup_observations VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                observation_id,
                lineup_id,
                observed,
                coach_id,
                record.formation,
                json.dumps(record.source_payload),
                source_raw_path,
            ],
        )
        seen_lineup_players: set[tuple[object, str]] = set()
        for player in record.players:
            player_key = (player.provider_player_id, player.role)
            if player_key in seen_lineup_players:
                continue
            seen_lineup_players.add(player_key)
            player_id = _ensure_player(connection, player.provider_player_id, player.name, source_raw_path, observed)
            connection.execute(
                "INSERT INTO lineup_players VALUES (?, ?, ?, ?, ?, ?)",
                [lineup_id, player_id, player.number, player.position, player.grid, player.role],
            )


def _replace_team_statistics(
    connection: duckdb.DuckDBPyConnection,
    fixture_id: str,
    payloads: list[dict[str, Any]],
    source_raw_path: str,
    observed: datetime,
) -> None:
    connection.execute("DELETE FROM team_match_statistics WHERE fixture_id=?", [fixture_id])
    for payload in payloads:
        record = normalize_team_statistics(payload)
        values = record.model_dump()
        connection.execute(
            "INSERT INTO team_match_statistics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                fixture_id,
                canonical_id("team", "api_football", record.provider_team_id),
                *(values[field] for field in list(values)[1:-1]),
                json.dumps(record.additional_stats),
                source_raw_path,
                observed,
            ],
        )


def _nested(stats: dict[str, Any], group: str, field: str) -> Any:
    value = stats.get(group)
    return value.get(field) if isinstance(value, dict) else None


def _replace_player_statistics(
    connection: duckdb.DuckDBPyConnection,
    fixture_id: str,
    payloads: list[dict[str, Any]],
    source_raw_path: str,
    observed: datetime,
) -> None:
    connection.execute("DELETE FROM player_match_statistics WHERE fixture_id=?", [fixture_id])
    seen_player_statistics: set[tuple[int, int]] = set()
    for team_payload in payloads:
        team = team_payload.get("team") or {}
        if not isinstance(team, dict) or team.get("id") is None:
            continue
        team_id = _ensure_team(
            connection,
            int(team["id"]),
            str(team.get("name") or f"Team {team['id']}"),
            source_raw_path,
            observed,
        )
        for record in normalize_player_statistics(team_payload):
            record_key = (record.provider_team_id, record.provider_player_id)
            if record_key in seen_player_statistics:
                continue
            seen_player_statistics.add(record_key)
            stats = record.statistics
            player_id = _ensure_player(
                connection, record.provider_player_id, record.player_name, source_raw_path, observed
            )
            fields = [
                ("games", "minutes"),
                ("games", "number"),
                ("games", "position"),
                ("games", "rating"),
                ("games", "captain"),
                ("games", "substitute"),
                ("shots", "total"),
                ("shots", "on"),
                ("goals", "total"),
                ("goals", "conceded"),
                ("goals", "assists"),
                ("goals", "saves"),
                ("passes", "total"),
                ("passes", "key"),
                ("passes", "accuracy"),
                ("tackles", "total"),
                ("tackles", "blocks"),
                ("tackles", "interceptions"),
                ("duels", "total"),
                ("duels", "won"),
                ("dribbles", "attempts"),
                ("dribbles", "success"),
                ("dribbles", "past"),
                ("fouls", "drawn"),
                ("fouls", "committed"),
                ("cards", "yellow"),
                ("cards", "red"),
                ("penalty", "won"),
                ("penalty", "commited"),
                ("penalty", "scored"),
                ("penalty", "missed"),
                ("penalty", "saved"),
            ]
            connection.execute(
                "INSERT INTO player_match_statistics VALUES (" + ",".join("?" for _ in range(38)) + ")",
                [
                    fixture_id,
                    team_id,
                    player_id,
                    *(_nested(stats, group, field) for group, field in fields),
                    json.dumps(stats),
                    source_raw_path,
                    observed,
                ],
            )


def _replace_completeness(
    connection: duckdb.DuckDBPyConnection,
    fixture_id: str,
    assessment: QualityAssessment,
    source_raw_path: str,
    observed: datetime,
) -> None:
    connection.execute("DELETE FROM fixture_completeness WHERE fixture_id=?", [fixture_id])
    for component, state in assessment.components.items():
        connection.execute(
            "INSERT INTO fixture_completeness VALUES (?, ?, ?, ?, ?, ?)",
            [fixture_id, component, state.value, None, observed, source_raw_path],
        )
