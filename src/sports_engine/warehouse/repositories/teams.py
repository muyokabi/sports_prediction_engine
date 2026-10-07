from datetime import UTC, datetime

import duckdb

from sports_engine.core.ids import canonical_id
from sports_engine.sports.football.domain.team import TeamRecord

PROVIDER_ID = "8d39dc64-2491-5b70-9fb8-2b0b379b2026"


def upsert_team(
    connection: duckdb.DuckDBPyConnection,
    record: TeamRecord,
    *,
    source_raw_path: str,
    retrieved_at: datetime | None = None,
) -> str:
    observed = retrieved_at or datetime.now(UTC)
    team_id = canonical_id("team", "api_football", record.provider_team_id)
    venue_id = None
    if record.venue and record.venue.provider_venue_id is not None:
        venue_id = canonical_id("venue", "api_football", record.venue.provider_venue_id)
        connection.execute(
            "INSERT INTO venues VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (venue_id) DO UPDATE SET name=excluded.name, city=excluded.city, "
            "address=excluded.address, capacity=excluded.capacity, surface=excluded.surface, "
            "updated_at=excluded.updated_at",
            [
                venue_id,
                record.venue.name,
                record.venue.city,
                record.venue.address,
                record.venue.capacity,
                record.venue.surface,
                observed,
            ],
        )
        _map_entity(connection, "venue", record.venue.provider_venue_id, venue_id, observed)
    connection.execute(
        "INSERT INTO teams (team_id, name, country, founded, national, logo_url, updated_at, "
        "code, home_venue_id, source_raw_path, retrieved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (team_id) DO UPDATE SET name=excluded.name, country=excluded.country, "
        "founded=excluded.founded, national=excluded.national, logo_url=excluded.logo_url, "
        "updated_at=excluded.updated_at, code=excluded.code, home_venue_id=excluded.home_venue_id, "
        "source_raw_path=excluded.source_raw_path, retrieved_at=excluded.retrieved_at",
        [
            team_id,
            record.name,
            record.country,
            record.founded,
            record.national,
            record.logo_url,
            observed,
            record.code,
            venue_id,
            source_raw_path,
            observed,
        ],
    )
    _map_entity(connection, "team", record.provider_team_id, team_id, observed)
    return str(team_id)


def link_competition_season_team(
    connection: duckdb.DuckDBPyConnection,
    *,
    competition_season_id: str,
    team_id: str,
    source_raw_path: str,
    observed_at: datetime | None = None,
) -> None:
    observed = observed_at or datetime.now(UTC)
    connection.execute(
        "INSERT INTO competition_season_teams VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (competition_season_id, team_id) DO UPDATE SET "
        "last_observed_at=excluded.last_observed_at, source_raw_path=excluded.source_raw_path",
        [competition_season_id, team_id, observed, observed, source_raw_path],
    )


def _map_entity(
    connection: duckdb.DuckDBPyConnection,
    entity_type: str,
    provider_entity_id: int,
    canonical_entity_id: object,
    observed: datetime,
) -> None:
    connection.execute(
        "INSERT INTO provider_entity_map VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (provider_id, entity_type, provider_entity_id) DO UPDATE SET "
        "canonical_entity_id=excluded.canonical_entity_id, last_seen_at=excluded.last_seen_at",
        [PROVIDER_ID, entity_type, str(provider_entity_id), canonical_entity_id, observed, observed],
    )
