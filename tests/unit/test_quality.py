from sports_engine.core.enums import Eligibility
from sports_engine.sports.football.quality.completeness import assess_match_package


def complete_player() -> dict[str, object]:
    return {
        "games": {"minutes": 90, "rating": "7.0"},
        "shots": {"total": 0, "on": 0},
        "passes": {"total": 20, "key": 0},
        "tackles": {"total": 0, "interceptions": 0},
        "duels": {"total": 0, "won": 0},
        "dribbles": {"attempts": 0, "success": 0},
        "fouls": {"drawn": 0, "committed": 0},
        "cards": {"yellow": 0, "red": 0},
        "penalty": {"scored": 0, "missed": 0, "saved": 0},
    }


def complete_team_statistics() -> list[dict[str, object]]:
    names = (
        "Shots on Goal",
        "Total Shots",
        "Fouls",
        "Corner Kicks",
        "Offsides",
        "Ball Possession",
        "Total passes",
        "Passes accurate",
        "Passes %",
    )
    return [{"type": name, "value": 0} for name in names]


def complete_participants(first_player_id: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    player_ids = range(first_player_id, first_player_id + 11)
    lineup = [{"player": {"id": player_id}} for player_id in player_ids]
    players = [
        {"player": {"id": player_id}, "statistics": [complete_player()]}
        for player_id in range(first_player_id, first_player_id + 11)
    ]
    return lineup, players


def test_incomplete_match_is_not_ml_eligible() -> None:
    assessment = assess_match_package(
        {
            "fixture": {"id": 1, "date": "2026-01-01", "status": {"short": "FT"}},
            "goals": {"home": 1, "away": 0},
        }
    )
    assert assessment.eligibility == Eligibility.PENDING_REPAIR
    assert "events" in assessment.missing


def test_full_embedded_package_is_eligible() -> None:
    home_lineup, home_players = complete_participants(100)
    away_lineup, away_players = complete_participants(200)
    payload = {
        "fixture": {"id": 1, "date": "2026-01-01", "status": {"short": "FT"}},
        "goals": {"home": 1, "away": 0},
        "events": [],
        "lineups": [
            {"startXI": home_lineup, "substitutes": []},
            {"startXI": away_lineup, "substitutes": []},
        ],
        "statistics": [
            {"statistics": complete_team_statistics()},
            {"statistics": complete_team_statistics()},
        ],
        "players": [
            {"players": home_players},
            {"players": away_players},
        ],
    }
    assert assess_match_package(payload).eligibility == Eligibility.ML_ELIGIBLE


def test_unknown_mandatory_statistic_is_not_treated_as_zero() -> None:
    payload = {
        "fixture": {"id": 1, "date": "2026-01-01", "status": {"short": "FT"}},
        "goals": {"home": 0, "away": 0},
        "events": [],
        "lineups": [
            {"startXI": [{} for _ in range(11)], "substitutes": []},
            {"startXI": [{} for _ in range(11)], "substitutes": []},
        ],
        "statistics": [
            {"statistics": complete_team_statistics()},
            {
                "statistics": [
                    {**item, "value": None} if item["type"] == "Shots on Goal" else item
                    for item in complete_team_statistics()
                ]
            },
        ],
        "players": [
            {"players": [{"statistics": [complete_player()]}]},
            {"players": [{"statistics": [complete_player()]}]},
        ],
    }
    assessment = assess_match_package(payload)
    assert assessment.eligibility == Eligibility.PENDING_REPAIR
    assert "away_team_stats" in assessment.missing
