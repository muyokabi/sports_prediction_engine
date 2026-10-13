import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sports_engine.core.ids import canonical_id
from sports_engine.sports.football.features.dataset import PointInTimeFeatureBuilder
from sports_engine.sports.football.normalization.fixtures import normalize_fixture
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.fixtures import upsert_fixture
from sports_engine.warehouse.repositories.leagues import upsert_competition_season


def _fixture(provider_id: int, kickoff: datetime, *, complete: bool) -> dict[str, object]:
    return {
        "fixture": {
            "id": provider_id,
            "date": kickoff.isoformat(),
            "status": {
                "short": "FT" if complete else "NS",
                "long": "Finished" if complete else "Not Started",
                "elapsed": 90 if complete else None,
            },
        },
        "league": {"id": 39, "season": 2026, "round": "Round 1"},
        "teams": {
            "home": {"id": 10, "name": "Home"},
            "away": {"id": 11, "name": "Away"},
        },
        "goals": {"home": 1 if complete else None, "away": 0 if complete else None},
    }


def _builder(connection: object, tmp_path: Path) -> PointInTimeFeatureBuilder:
    return PointInTimeFeatureBuilder(
        connection,
        tmp_path / "features",
        windows=[3],
        exponential_half_life=5,
        prediction_lead_hours=24,
    )


def _season_and_fixtures(connection: object) -> tuple[str, str]:
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2026, "current": True, "coverage": {"injuries": True}},
        admitted=True,
        reason="qualified",
        priority=1,
    )
    prior_id = upsert_fixture(
        connection,
        normalize_fixture(_fixture(100, datetime(2026, 1, 1, 12, tzinfo=UTC), complete=True)),
        season_id,
        "prior.json.gz",
    )
    target_id = upsert_fixture(
        connection,
        normalize_fixture(_fixture(200, datetime(2026, 1, 10, 12, tzinfo=UTC), complete=False)),
        season_id,
        "target.json.gz",
    )
    return prior_id, target_id


def test_availability_uses_latest_complete_collection_not_union_of_stale_injuries(tmp_path: Path) -> None:
    connection = connect(tmp_path / "injury-snapshots.duckdb")
    migrate(connection)
    _, target_id = _season_and_fixtures(connection)
    first = datetime(2026, 1, 9, 8, tzinfo=UTC)
    latest = datetime(2026, 1, 10, 8, tzinfo=UTC)
    home_team_id = canonical_id("team", "api_football", 10)
    player_id = canonical_id("player", "api_football", 500)
    connection.execute(
        "INSERT INTO players (player_id, name, updated_at) VALUES (?, 'Player 500', ?)",
        [player_id, first],
    )
    connection.execute(
        "INSERT INTO injury_collection_runs VALUES (?, DATE '2026-01-10', ?, 'first.json.gz', true, NULL)",
        [uuid.uuid4(), first],
    )
    connection.execute(
        "INSERT INTO injury_observations VALUES (?, 200, ?, ?, ?, ?, 'Missing Fixture', 'Knock', '{}', "
        "'first.json.gz', NULL)",
        [uuid.uuid4(), target_id, home_team_id, player_id, first],
    )
    # A later complete provider response contains no injury row for this player.
    # Absence in that full snapshot must clear the earlier observation.
    connection.execute(
        "INSERT INTO injury_collection_runs VALUES (?, DATE '2026-01-10', ?, 'latest.json.gz', true, NULL)",
        [uuid.uuid4(), latest],
    )

    features = _builder(connection, tmp_path)._availability_features(
        {
            "fixture_id": target_id,
            "kickoff_utc": datetime(2026, 1, 10, 12, tzinfo=UTC),
            "home_team_id": str(home_team_id),
            "away_team_id": str(canonical_id("team", "api_football", 11)),
        },
        datetime(2026, 1, 10, 10, tzinfo=UTC),
    )

    assert features["player_availability_known"] is True
    assert features["home_injured_players"] == 0
    connection.close()


def test_lineup_strength_uses_membership_from_latest_observation_before_cutoff(tmp_path: Path) -> None:
    connection = connect(tmp_path / "lineup-snapshots.duckdb")
    migrate(connection)
    prior_id, target_id = _season_and_fixtures(connection)
    prior_retrieved = datetime(2026, 1, 2, 12, tzinfo=UTC)
    cutoff = datetime(2026, 1, 9, 12, tzinfo=UTC)
    later = datetime(2026, 1, 9, 16, tzinfo=UTC)
    team_ids = {
        "home": canonical_id("team", "api_football", 10),
        "away": canonical_id("team", "api_football", 11),
    }
    players = {
        "home_old": (500, 5.0, team_ids["home"]),
        "home_later": (501, 9.0, team_ids["home"]),
        "away_old": (600, 6.0, team_ids["away"]),
        "away_later": (601, 10.0, team_ids["away"]),
    }
    for label, (provider_id, rating, team_id) in players.items():
        player_id = canonical_id("player", "api_football", provider_id)
        connection.execute(
            "INSERT INTO players (player_id, name, updated_at) VALUES (?, ?, ?)",
            [player_id, label, prior_retrieved],
        )
        connection.execute(
            "INSERT INTO player_match_statistics "
            "(fixture_id, team_id, player_id, rating, additional_stats, source_raw_path, retrieved_at) "
            "VALUES (?, ?, ?, ?, '{}', 'prior-details.json.gz', ?)",
            [prior_id, team_id, player_id, rating, prior_retrieved],
        )

    observed = datetime(2026, 1, 9, 8, tzinfo=UTC)
    for side, old_provider_id, later_provider_id in (("home", 500, 501), ("away", 600, 601)):
        lineup_id = uuid.uuid4()
        old_payload = {
            "team": {"id": 10 if side == "home" else 11},
            "startXI": [{"player": {"id": old_provider_id}}],
            "substitutes": [],
        }
        later_payload = {
            "team": {"id": 10 if side == "home" else 11},
            "startXI": [{"player": {"id": later_provider_id}}],
            "substitutes": [],
        }
        connection.execute(
            "INSERT INTO lineups (lineup_id, fixture_id, team_id, formation, source_payload, "
            "source_raw_path, retrieved_at) VALUES (?, ?, ?, '4-3-3', ?, 'lineup.json.gz', ?)",
            [lineup_id, target_id, team_ids[side], json.dumps(old_payload), observed],
        )
        connection.execute(
            "INSERT INTO lineup_observations VALUES (?, ?, ?, NULL, '4-3-3', ?, 'observed.json.gz')",
            [uuid.uuid4(), lineup_id, observed, json.dumps(old_payload)],
        )
        connection.execute(
            "INSERT INTO lineup_observations VALUES (?, ?, ?, NULL, '4-3-3', ?, 'later.json.gz')",
            [uuid.uuid4(), lineup_id, later, json.dumps(later_payload)],
        )
        # The mutable convenience table now represents the later lineup. A
        # historical feature cutoff must not read this membership.
        connection.execute(
            "INSERT INTO lineup_players VALUES (?, ?, NULL, NULL, NULL, 'STARTING_XI')",
            [lineup_id, canonical_id("player", "api_football", later_provider_id)],
        )

    features = _builder(connection, tmp_path)._lineup_features(
        {
            "fixture_id": target_id,
            "home_team_id": str(team_ids["home"]),
            "away_team_id": str(team_ids["away"]),
        },
        cutoff,
    )

    assert features["lineup_strength_known"] is True
    assert features["home_lineup_strength"] == pytest.approx(5.0)
    assert features["away_lineup_strength"] == pytest.approx(6.0)
    connection.close()
