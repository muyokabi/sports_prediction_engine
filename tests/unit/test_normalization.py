from sports_engine.sports.football.normalization.fixtures import normalize_fixture
from sports_engine.sports.football.normalization.team_stats import normalize_team_statistics


def test_fixture_normalization_preserves_zero_score() -> None:
    record = normalize_fixture(
        {
            "fixture": {
                "id": 7,
                "date": "2026-01-01T12:00:00+00:00",
                "status": {"short": "FT", "long": "Finished", "elapsed": 90},
            },
            "league": {"id": 39, "season": 2026, "round": "1"},
            "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}},
            "goals": {"home": 0, "away": 0},
        }
    )
    assert record.home_goals == 0
    assert record.away_goals == 0


def test_team_statistics_distinguish_zero_from_unknown() -> None:
    record = normalize_team_statistics(
        {
            "team": {"id": 1},
            "statistics": [
                {"type": "Shots on Goal", "value": 0},
                {"type": "Ball Possession", "value": "51%"},
            ],
        }
    )
    assert record.shots_on_goal == 0
    assert record.total_shots is None
    assert record.ball_possession == 51
