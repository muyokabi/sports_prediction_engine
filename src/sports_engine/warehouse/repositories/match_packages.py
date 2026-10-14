import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import duckdb
import polars as pl

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


def _bulk_insert(
    connection: duckdb.DuckDBPyConnection,
    relation_name: str,
    columns: list[str],
    rows: Sequence[Sequence[object]],
    statement: str,
) -> None:
    """Write a normalized match component with one DuckDB columnar scan."""
    if not rows:
        return
    frame = pl.DataFrame(rows, schema=columns, orient="row", infer_schema_length=None)
    connection.register(relation_name, frame)
    try:
        connection.execute(statement)
    finally:
        connection.unregister(relation_name)


def _bulk_upsert_players(
    connection: duckdb.DuckDBPyConnection,
    players: dict[object, str],
    source_raw_path: str,
    observed: datetime,
) -> None:
    _bulk_insert(
        connection,
        "_incoming_match_players",
        ["player_id", "name", "updated_at", "source_raw_path", "retrieved_at"],
        [[str(player_id), name, observed, source_raw_path, observed] for player_id, name in players.items()],
        "INSERT INTO players (player_id, name, updated_at, source_raw_path, retrieved_at) "
        "SELECT * FROM _incoming_match_players ON CONFLICT (player_id) DO UPDATE SET "
        "name=excluded.name, updated_at=excluded.updated_at, "
        "source_raw_path=excluded.source_raw_path, retrieved_at=excluded.retrieved_at",
    )


def _replace_events(
    connection: duckdb.DuckDBPyConnection,
    fixture_id: str,
    provider_fixture_id: int,
    payloads: list[dict[str, Any]],
    source_raw_path: str,
    observed: datetime,
) -> None:
    connection.execute("DELETE FROM fixture_events WHERE fixture_id=?", [fixture_id])
    players: dict[object, str] = {}
    for payload in payloads:
        for key in ("player", "assist"):
            player = payload.get(key) or {}
            if player.get("id") is not None:
                player_id = canonical_id("player", "api_football", int(player["id"]))
                players[player_id] = str(player.get("name") or f"Player {player['id']}")
    _bulk_upsert_players(connection, players, source_raw_path, observed)
    rows = []
    for event in normalize_events(provider_fixture_id, payloads):
        rows.append(
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
            ]
        )
    _bulk_insert(
        connection,
        "_incoming_fixture_events",
        [
            "event_id", "fixture_id", "team_id", "player_id", "assist_player_id", "elapsed", "extra",
            "event_type", "detail", "comments", "provider_sequence", "source_payload", "source_raw_path",
            "retrieved_at",
        ],
        [[str(value) if index < 5 and value is not None else value for index, value in enumerate(row)] for row in rows],
        "INSERT INTO fixture_events SELECT * FROM _incoming_fixture_events",
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
    coaches: dict[object, list[object]] = {}
    lineups: list[list[object]] = []
    observations: list[list[object]] = []
    players: dict[object, str] = {}
    lineup_players: list[list[object]] = []
    for payload in payloads:
        record = normalize_lineup(payload)
        team_id = canonical_id("team", "api_football", record.provider_team_id)
        lineup_id = canonical_id("lineup", "api_football", f"{fixture_id}:{record.provider_team_id}")
        coach_id = None
        if record.provider_coach_id is not None:
            coach_id = canonical_id("coach", "api_football", record.provider_coach_id)
            coaches[coach_id] = [str(coach_id), record.coach_name or f"Coach {record.provider_coach_id}", observed]
        lineups.append(
            [str(lineup_id), fixture_id, str(team_id), str(coach_id) if coach_id else None, record.formation,
             json.dumps(record.source_payload), source_raw_path, observed]
        )
        observation_id = canonical_id(
            "lineup_observation",
            "api_football",
            f"{lineup_id}:{observed.isoformat()}:{source_raw_path}",
        )
        observations.append(
            [str(observation_id), str(lineup_id), observed, str(coach_id) if coach_id else None,
             record.formation, json.dumps(record.source_payload), source_raw_path]
        )
        seen_lineup_players: set[tuple[object, str]] = set()
        for player in record.players:
            player_key = (player.provider_player_id, player.role)
            if player_key in seen_lineup_players:
                continue
            seen_lineup_players.add(player_key)
            player_id = canonical_id("player", "api_football", player.provider_player_id)
            players[player_id] = player.name
            lineup_players.append(
                [str(lineup_id), str(player_id), player.number, player.position, player.grid, player.role]
            )
    _bulk_insert(
        connection, "_incoming_coaches", ["coach_id", "name", "updated_at"], list(coaches.values()),
        "INSERT INTO coaches (coach_id, name, nationality, updated_at) "
        "SELECT coach_id, name, NULL, updated_at FROM _incoming_coaches "
        "ON CONFLICT (coach_id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at",
    )
    _bulk_insert(
        connection, "_incoming_lineups",
        [
            "lineup_id", "fixture_id", "team_id", "coach_id", "formation", "source_payload", "source_raw_path",
            "retrieved_at",
        ],
        lineups, "INSERT INTO lineups SELECT * FROM _incoming_lineups ON CONFLICT (lineup_id) DO NOTHING",
    )
    _bulk_insert(
        connection, "_incoming_lineup_observations",
        ["observation_id", "lineup_id", "observed_at", "coach_id", "formation", "source_payload", "source_raw_path"],
        observations, "INSERT INTO lineup_observations SELECT * FROM _incoming_lineup_observations",
    )
    _bulk_upsert_players(connection, players, source_raw_path, observed)
    _bulk_insert(
        connection, "_incoming_lineup_players",
        ["lineup_id", "player_id", "squad_number", "position", "grid", "role"],
        lineup_players, "INSERT INTO lineup_players SELECT * FROM _incoming_lineup_players",
    )


def _replace_team_statistics(
    connection: duckdb.DuckDBPyConnection,
    fixture_id: str,
    payloads: list[dict[str, Any]],
    source_raw_path: str,
    observed: datetime,
) -> None:
    connection.execute("DELETE FROM team_match_statistics WHERE fixture_id=?", [fixture_id])
    rows = []
    for payload in payloads:
        record = normalize_team_statistics(payload)
        values = record.model_dump()
        rows.append(
            [
                fixture_id,
                str(canonical_id("team", "api_football", record.provider_team_id)),
                *(values[field] for field in list(values)[1:-1]),
                json.dumps(record.additional_stats),
                source_raw_path,
                observed,
            ]
        )
    _bulk_insert(
        connection, "_incoming_team_match_statistics", [f"column_{index}" for index in range(21)], rows,
        "INSERT INTO team_match_statistics SELECT * FROM _incoming_team_match_statistics",
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
    teams: dict[object, str] = {}
    players: dict[object, str] = {}
    rows: list[list[object]] = []
    for team_payload in payloads:
        team = team_payload.get("team") or {}
        if not isinstance(team, dict) or team.get("id") is None:
            continue
        team_id = canonical_id("team", "api_football", int(team["id"]))
        teams[team_id] = str(team.get("name") or f"Team {team['id']}")
        for record in normalize_player_statistics(team_payload):
            record_key = (record.provider_team_id, record.provider_player_id)
            if record_key in seen_player_statistics:
                continue
            seen_player_statistics.add(record_key)
            stats = record.statistics
            player_id = canonical_id("player", "api_football", record.provider_player_id)
            players[player_id] = record.player_name
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
            rows.append(
                [
                    fixture_id,
                    str(team_id),
                    str(player_id),
                    *(_nested(stats, group, field) for group, field in fields),
                    json.dumps(stats),
                    source_raw_path,
                    observed,
                ]
            )
    _bulk_insert(
        connection, "_incoming_match_teams",
        ["team_id", "name", "updated_at", "source_raw_path", "retrieved_at"],
        [[str(team_id), name, observed, source_raw_path, observed] for team_id, name in teams.items()],
        "INSERT INTO teams (team_id, name, updated_at, source_raw_path, retrieved_at) "
        "SELECT * FROM _incoming_match_teams ON CONFLICT (team_id) DO UPDATE SET "
        "name=excluded.name, updated_at=excluded.updated_at, "
        "source_raw_path=excluded.source_raw_path, retrieved_at=excluded.retrieved_at",
    )
    _bulk_upsert_players(connection, players, source_raw_path, observed)
    _bulk_insert(
        connection, "_incoming_player_match_statistics", [f"column_{index}" for index in range(38)], rows,
        "INSERT INTO player_match_statistics SELECT * FROM _incoming_player_match_statistics",
    )


def _replace_completeness(
    connection: duckdb.DuckDBPyConnection,
    fixture_id: str,
    assessment: QualityAssessment,
    source_raw_path: str,
    observed: datetime,
) -> None:
    connection.execute("DELETE FROM fixture_completeness WHERE fixture_id=?", [fixture_id])
    rows = [
        [fixture_id, component, state.value, None, observed, source_raw_path]
        for component, state in assessment.components.items()
    ]
    _bulk_insert(
        connection, "_incoming_fixture_completeness",
        ["fixture_id", "component", "state", "reason", "assessed_at", "source_raw_path"], rows,
        "INSERT INTO fixture_completeness SELECT * FROM _incoming_fixture_completeness",
    )
