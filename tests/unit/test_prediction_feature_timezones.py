from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sports_engine.sports.football.features.dataset import PointInTimeFeatureBuilder


class _Result:
    def __init__(self, rows: list[tuple[object, ...]] | None = None, row: tuple[object, ...] = (0,)) -> None:
        self.rows = rows or []
        self.row = row

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows

    def fetchone(self) -> tuple[object, ...]:
        return self.row


class _FeatureConnection:
    def __init__(self, targets: list[tuple[object, ...]]) -> None:
        self.targets = targets

    def execute(self, query: str, _parameters: object = None) -> _Result:
        if query.startswith("SELECT CAST(f.fixture_id AS VARCHAR), f.kickoff_utc"):
            return _Result(self.targets)
        if query.startswith("WITH latest AS"):
            return _Result([])
        return _Result(row=(0,))


class _MixedTimezoneBuilder(PointInTimeFeatureBuilder):
    def _matches(self, _ledger_mode: str) -> list[dict[str, object]]:
        nairobi = ZoneInfo("Africa/Nairobi")
        empty_stats = {
            "shots_on_goal": None,
            "total_shots": None,
            "corner_kicks": None,
            "possession": None,
            "total_passes": None,
            "passes_percentage": None,
            "fouls": None,
            "yellow_cards": None,
            "red_cards": None,
            "player_rating": None,
        }
        return [
            {
                "fixture_id": "history",
                "kickoff_utc": datetime(2026, 10, 1, 15, tzinfo=nairobi),
                "home_team_id": "home-with-history",
                "away_team_id": "old-opponent",
                "home_goals": 1,
                "away_goals": 0,
                "source_observed_at": datetime(2026, 10, 1, 19, tzinfo=nairobi),
                "home_stats": empty_stats,
                "away_stats": empty_stats,
            }
        ]


def test_prediction_frame_normalizes_mixed_connection_and_utc_times(tmp_path: Path) -> None:
    nairobi = ZoneInfo("Africa/Nairobi")
    targets = [
        ("one", datetime(2026, 10, 9, 18, tzinfo=nairobi), "home-with-history", "away-one", "A", "H1", "A1"),
        ("two", datetime(2026, 10, 9, 20, tzinfo=nairobi), "home-two", "away-two", "B", "H2", "A2"),
    ]
    builder = _MixedTimezoneBuilder(
        _FeatureConnection(targets),  # type: ignore[arg-type]
        tmp_path,
        windows=[3],
        exponential_half_life=5,
        prediction_lead_hours=1,
    )
    frame = builder.build_prediction_frame(
        datetime(2026, 10, 9, tzinfo=UTC),
        ledger_mode="production",
        observed_at=datetime(2026, 10, 8, 12, tzinfo=UTC),
        timezone="Africa/Nairobi",
    )

    assert frame.height == 2
    assert frame["kickoff_utc"].dtype.time_zone == "UTC"
    assert frame["prediction_timestamp"].dtype.time_zone == "UTC"
    assert frame["source_observation_max"].dtype.time_zone == "UTC"
