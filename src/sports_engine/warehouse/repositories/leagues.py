import json
from datetime import UTC, datetime
from typing import Any

import duckdb

from sports_engine.core.ids import canonical_id


def upsert_competition_season(
    connection: duckdb.DuckDBPyConnection,
    league: dict[str, Any],
    season: dict[str, Any],
    *,
    admitted: bool,
    reason: str,
    priority: int | None,
    source_raw_path: str | None = None,
    retrieved_at: datetime | None = None,
    ledger_mode: str = "production",
    replay_eligible: bool = False,
) -> str:
    now = retrieved_at or datetime.now(UTC)
    competition_id = canonical_id("competition", "api_football", league["id"])
    season_id = canonical_id("season", "api_football", f"{league['id']}:{season['year']}")
    competition_season_id = canonical_id("competition_season", "api_football", f"{league['id']}:{season['year']}")
    connection.execute(
        "INSERT INTO competitions (competition_id, name, country, competition_type, logo_url, "
        "created_at, updated_at, source_raw_path, retrieved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (competition_id) DO UPDATE SET name=excluded.name, country=excluded.country, "
        "competition_type=excluded.competition_type, logo_url=excluded.logo_url, "
        "updated_at=excluded.updated_at, source_raw_path=excluded.source_raw_path, "
        "retrieved_at=excluded.retrieved_at",
        [
            competition_id,
            league["name"],
            league.get("country"),
            league.get("type"),
            league.get("logo"),
            now,
            now,
            source_raw_path,
            now,
        ],
    )
    connection.execute(
        "INSERT INTO provider_entity_map VALUES "
        "('8d39dc64-2491-5b70-9fb8-2b0b379b2026', 'competition', ?, ?, ?, ?) "
        "ON CONFLICT (provider_id, entity_type, provider_entity_id) DO UPDATE SET "
        "canonical_entity_id=excluded.canonical_entity_id, last_seen_at=excluded.last_seen_at",
        [str(league["id"]), competition_id, now, now],
    )
    connection.execute(
        "INSERT INTO seasons VALUES (?, ?, ?, ?, ?) ON CONFLICT (season_id) DO UPDATE SET "
        "start_date=excluded.start_date, end_date=excluded.end_date, current=excluded.current",
        [
            season_id,
            str(season["year"]),
            season.get("start"),
            season.get("end"),
            season.get("current", False),
        ],
    )
    connection.execute(
        "INSERT INTO competition_seasons (competition_season_id, competition_id, season_id, "
        "provider_season, admitted, admission_reason, coverage, priority, created_at, "
        "source_raw_path, retrieved_at, provider_accessible, access_reason, ledger_mode, replay_eligible) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, true, NULL, ?, ?) "
        "ON CONFLICT (competition_id, provider_season) DO UPDATE SET admitted=excluded.admitted, "
        "admission_reason=excluded.admission_reason, coverage=excluded.coverage, "
        "priority=excluded.priority, source_raw_path=excluded.source_raw_path, "
        "retrieved_at=excluded.retrieved_at, ledger_mode=excluded.ledger_mode, "
        "provider_accessible=true, access_reason=NULL, replay_eligible=excluded.replay_eligible",
        [
            competition_season_id,
            competition_id,
            season_id,
            season["year"],
            admitted,
            reason,
            json.dumps(season.get("coverage") or {}),
            priority,
            now,
            source_raw_path,
            now,
            ledger_mode,
            replay_eligible,
        ],
    )
    return str(competition_season_id)


def admitted_seasons(
    connection: duckdb.DuckDBPyConnection, ledger_mode: str | None = None
) -> list[tuple[str, int, int]]:
    eligibility_clause = "cs.replay_eligible" if ledger_mode == "replay" else "cs.admitted"
    mode_clause = " AND cs.ledger_mode=?" if ledger_mode is not None else ""
    parameters = [ledger_mode] if ledger_mode is not None else []
    return connection.execute(
        "SELECT CAST(cs.competition_season_id AS VARCHAR), CAST(pem.provider_entity_id AS INTEGER), "
        "cs.provider_season FROM competition_seasons cs "
        "JOIN provider_entity_map pem ON pem.canonical_entity_id=cs.competition_id "
        f"AND pem.entity_type='competition' WHERE {eligibility_clause} "
        f"AND cs.provider_accessible{mode_clause} "
        "ORDER BY cs.priority",
        parameters,
    ).fetchall()


def mark_provider_season_inaccessible(connection: duckdb.DuckDBPyConnection, provider_season: int, reason: str) -> None:
    connection.execute(
        "UPDATE competition_seasons SET provider_accessible=false, admitted=false, "
        "access_reason=?, admission_reason=? WHERE provider_season=? AND admitted",
        [reason, f"provider access blocked: {reason}", provider_season],
    )
