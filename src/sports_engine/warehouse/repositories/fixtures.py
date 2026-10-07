import uuid
from datetime import UTC, datetime

import duckdb

from sports_engine.core.ids import canonical_id
from sports_engine.sports.football.domain.fixture import FixtureRecord


def upsert_fixture(
    connection: duckdb.DuckDBPyConnection,
    record: FixtureRecord,
    competition_season_id: str,
    source_raw_path: str,
) -> str:
    now = datetime.now(UTC)
    fixture_id = canonical_id("fixture", "api_football", record.provider_fixture_id)
    home_id = canonical_id("team", "api_football", record.home_provider_team_id)
    away_id = canonical_id("team", "api_football", record.away_provider_team_id)
    for team_id, provider_id, name in (
        (home_id, record.home_provider_team_id, record.home_team_name),
        (away_id, record.away_provider_team_id, record.away_team_name),
    ):
        connection.execute(
            "INSERT INTO teams (team_id, name, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (team_id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at",
            [team_id, name, now],
        )
        connection.execute(
            "INSERT INTO provider_entity_map VALUES "
            "('8d39dc64-2491-5b70-9fb8-2b0b379b2026', 'team', ?, ?, ?, ?) "
            "ON CONFLICT (provider_id, entity_type, provider_entity_id) DO UPDATE SET "
            "canonical_entity_id=excluded.canonical_entity_id, last_seen_at=excluded.last_seen_at",
            [str(provider_id), team_id, now, now],
        )
    existing = connection.execute(
        "SELECT kickoff_utc, status_short, round, status_long, elapsed, home_goals, away_goals, "
        "halftime_home, halftime_away, fulltime_home, fulltime_away, extratime_home, "
        "extratime_away, penalty_home, penalty_away FROM fixtures_current WHERE fixture_id=?",
        [fixture_id],
    ).fetchone()
    if existing is None:
        connection.execute(
            "INSERT INTO fixtures (fixture_id, competition_season_id, provider_fixture_id, round, kickoff_utc, "
            "status_short, status_long, elapsed, home_team_id, away_team_id, home_goals, away_goals, "
            "halftime_home, halftime_away, fulltime_home, fulltime_away, extratime_home, extratime_away, "
            "penalty_home, penalty_away, source_raw_path, normalizer_version, retrieved_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '1', ?, ?)",
            [
                fixture_id,
                competition_season_id,
                record.provider_fixture_id,
                record.round,
                record.kickoff_utc,
                record.status_short,
                record.status_long,
                record.elapsed,
                home_id,
                away_id,
                record.home_goals,
                record.away_goals,
                record.halftime_home,
                record.halftime_away,
                record.fulltime_home,
                record.fulltime_away,
                record.extratime_home,
                record.extratime_away,
                record.penalty_home,
                record.penalty_away,
                source_raw_path,
                now,
                now,
            ],
        )
    changed = existing is None or existing != (
        record.kickoff_utc,
        record.status_short,
        record.round,
        record.status_long,
        record.elapsed,
        record.home_goals,
        record.away_goals,
        record.halftime_home,
        record.halftime_away,
        record.fulltime_home,
        record.fulltime_away,
        record.extratime_home,
        record.extratime_away,
        record.penalty_home,
        record.penalty_away,
    )
    if changed:
        observation_id = uuid.uuid5(fixture_id, f"{now.isoformat()}:{source_raw_path}")
        connection.execute(
            "INSERT INTO fixture_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                observation_id,
                fixture_id,
                now,
                record.round,
                record.kickoff_utc,
                record.status_short,
                record.status_long,
                record.elapsed,
                record.home_goals,
                record.away_goals,
                source_raw_path,
                record.halftime_home,
                record.halftime_away,
                record.fulltime_home,
                record.fulltime_away,
                record.extratime_home,
                record.extratime_away,
                record.penalty_home,
                record.penalty_away,
            ],
        )
    if existing is None or existing[0] != record.kickoff_utc:
        connection.execute(
            "INSERT INTO fixture_schedule_snapshots VALUES (?, ?, ?, NULL, ?, ?)",
            [fixture_id, now, record.kickoff_utc, record.round, source_raw_path],
        )
    if existing is None or existing[1] != record.status_short:
        connection.execute(
            "INSERT INTO fixture_status_history VALUES (?, ?, ?, ?, ?, ?)",
            [
                fixture_id,
                now,
                record.status_short,
                record.status_long,
                record.elapsed,
                source_raw_path,
            ],
        )
    connection.execute(
        "INSERT INTO fixture_team VALUES (?, ?, ?, 'HOME', ?, ?) "
        "ON CONFLICT (fixture_id, team_id) DO UPDATE SET "
        "goals_for=excluded.goals_for, goals_against=excluded.goals_against",
        [fixture_id, home_id, away_id, record.home_goals, record.away_goals],
    )
    connection.execute(
        "INSERT INTO fixture_team VALUES (?, ?, ?, 'AWAY', ?, ?) "
        "ON CONFLICT (fixture_id, team_id) DO UPDATE SET "
        "goals_for=excluded.goals_for, goals_against=excluded.goals_against",
        [fixture_id, away_id, home_id, record.away_goals, record.home_goals],
    )
    return str(fixture_id)
