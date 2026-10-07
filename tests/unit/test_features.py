from datetime import UTC, datetime, timedelta

import polars as pl

from sports_engine.sports.football.features.rolling import rolling_team_features


def test_rolling_features_exclude_current_match() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "fixture_id": [1, 2, 3],
            "team_id": ["A", "A", "A"],
            "kickoff_utc": [base, base + timedelta(days=1), base + timedelta(days=2)],
            "goals_for": [1, 9, 2],
            "goals_against": [0, 0, 1],
        }
    )
    result = rolling_team_features(frame, [2])
    assert result["goals_for_l2"].to_list() == [None, 1.0, 5.0]
