import copy
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import QuotaExhaustedError
from sports_engine.providers.api_football.errors import ApiFootballPlanRestrictionError
from sports_engine.sports.football.features.dataset import PointInTimeFeatureBuilder
from sports_engine.sports.football.ingestion.daily_update import DailyUpdateService
from sports_engine.sports.football.ingestion.detailed_matches import DetailedMatchIngestionService
from sports_engine.sports.football.normalization.fixtures import normalize_fixture
from sports_engine.sports.football.quality.completeness import assess_match_package
from sports_engine.sports.football.quality.soak import CompletenessSoakService
from sports_engine.warehouse import checkpoints
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.fixtures import upsert_fixture
from sports_engine.warehouse.repositories.leagues import upsert_competition_season
from sports_engine.warehouse.repositories.match_packages import persist_match_package


def _player(player_id: int) -> dict[str, Any]:
    return {
        "player": {"id": player_id, "name": f"Player {player_id}"},
        "statistics": [
            {
                "games": {
                    "minutes": 90,
                    "number": 1,
                    "position": "G",
                    "rating": "7.0",
                    "captain": False,
                    "substitute": False,
                },
                "shots": {"total": 0, "on": 0},
                "goals": {"total": 0, "conceded": 0, "assists": 0, "saves": 2},
                "passes": {"total": 30, "key": 0, "accuracy": "80"},
                "tackles": {"total": 0, "blocks": 0, "interceptions": 0},
                "duels": {"total": 1, "won": 1},
                "dribbles": {"attempts": 0, "success": 0, "past": 0},
                "fouls": {"drawn": 0, "committed": 0},
                "cards": {"yellow": 0, "red": 0},
                "penalty": {"won": 0, "commited": 0, "scored": 0, "missed": 0, "saved": 0},
            }
        ],
    }


def _stats(team_id: int) -> dict[str, Any]:
    names = {
        "Shots on Goal": 4,
        "Shots off Goal": 3,
        "Total Shots": 9,
        "Blocked Shots": 2,
        "Shots insidebox": 6,
        "Shots outsidebox": 3,
        "Fouls": 8,
        "Corner Kicks": 5,
        "Offsides": 1,
        "Ball Possession": "51%",
        "Yellow Cards": 0,
        "Red Cards": 0,
        "Goalkeeper Saves": 2,
        "Total passes": 400,
        "Passes accurate": 330,
        "Passes %": "82%",
    }
    return {"team": {"id": team_id}, "statistics": [{"type": key, "value": value} for key, value in names.items()]}


def _lineup(team_id: int, first_player: int) -> dict[str, Any]:
    return {
        "team": {"id": team_id},
        "coach": {"id": team_id + 500, "name": f"Coach {team_id}"},
        "formation": "4-3-3",
        "startXI": [
            {
                "player": {
                    "id": first_player + i,
                    "name": f"P {first_player + i}",
                    "number": i + 1,
                    "pos": "M",
                    "grid": "1:1",
                }
            }
            for i in range(11)
        ],
        "substitutes": [{"player": {"id": first_player + 20, "name": "Bench", "number": 20, "pos": "M", "grid": None}}],
    }


def _payload() -> dict[str, Any]:
    return {
        "fixture": {
            "id": 100,
            "date": "2026-08-01T12:00:00+00:00",
            "status": {"short": "FT", "long": "Finished", "elapsed": 90},
        },
        "league": {"id": 39, "season": 2026, "round": "Round 1"},
        "teams": {"home": {"id": 10, "name": "Home"}, "away": {"id": 11, "name": "Away"}},
        "goals": {"home": 1, "away": 0},
        "events": [
            {
                "time": {"elapsed": 10, "extra": None},
                "team": {"id": 10},
                "player": {"id": 1000, "name": "Scorer"},
                "assist": {"id": 1001, "name": "Assist"},
                "type": "Goal",
                "detail": "Normal Goal",
                "comments": None,
            }
        ],
        "lineups": [_lineup(10, 1000), _lineup(11, 2000)],
        "statistics": [_stats(10), _stats(11)],
        "players": [
            {"team": {"id": 10}, "players": [_player(1000 + index) for index in range(11)]},
            {"team": {"id": 11}, "players": [_player(2000 + index) for index in range(11)]},
        ],
    }


class Provider:
    def get(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        *,
        purpose: str,
        priority: Priority,
        job_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        assert parameters == {"ids": "100"}
        return [_payload()]


def test_complete_match_package_is_batched_and_committed_atomically(tmp_path: Path) -> None:
    connection = connect(tmp_path / "details.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League", "country": "England", "type": "League"},
        {"year": 2026, "current": True, "coverage": {}},
        admitted=True,
        reason="qualified",
        priority=1,
    )
    upsert_fixture(connection, normalize_fixture(_payload()), season_id, "fixture.json.gz")
    result = DetailedMatchIngestionService(
        connection,
        Provider(),
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: "details.json.gz",
    ).run([100])
    assert result.complete and result.fixtures_eligible == 1 and result.fixtures_quarantined == 0
    assert connection.execute("SELECT count(*) FROM fixture_events").fetchone() == (1,)
    assert connection.execute("SELECT count(*) FROM lineups").fetchone() == (2,)
    assert connection.execute("SELECT count(*) FROM lineup_players").fetchone() == (24,)
    assert connection.execute("SELECT count(*) FROM team_match_statistics").fetchone() == (2,)
    assert connection.execute("SELECT count(*) FROM player_match_statistics").fetchone() == (22,)
    assert connection.execute("SELECT eligibility FROM fixture_quality_status").fetchone() == ("ML_ELIGIBLE",)
    assert connection.execute("SELECT count(*) FROM fixture_completeness WHERE state='complete'").fetchone() == (15,)
    connection.close()


def test_duplicate_provider_lineup_player_is_deduplicated(tmp_path: Path) -> None:
    connection = connect(tmp_path / "duplicate-lineup.duckdb")
    migrate(connection)
    payload = _payload()
    payload["lineups"][0]["substitutes"].append(copy.deepcopy(payload["lineups"][0]["substitutes"][0]))
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2026, "current": True, "coverage": {}},
        admitted=True,
        reason="qualified",
        priority=1,
    )
    upsert_fixture(connection, normalize_fixture(payload), season_id, "fixture.json.gz")
    assessment = assess_match_package(payload)
    persist_match_package(connection, payload, assessment, source_raw_path="details.json.gz")
    assert connection.execute("SELECT count(*) FROM lineup_players").fetchone() == (24,)
    connection.close()


def test_duplicate_provider_player_statistics_are_deduplicated(tmp_path: Path) -> None:
    connection = connect(tmp_path / "duplicate-player-stat.duckdb")
    migrate(connection)
    payload = _payload()
    payload["players"][0]["players"].append(copy.deepcopy(payload["players"][0]["players"][0]))
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2026, "current": True, "coverage": {}},
        admitted=True,
        reason="qualified",
        priority=1,
    )
    upsert_fixture(connection, normalize_fixture(payload), season_id, "fixture.json.gz")
    assessment = assess_match_package(payload)
    persist_match_package(connection, payload, assessment, source_raw_path="details.json.gz")
    assert connection.execute("SELECT count(*) FROM player_match_statistics").fetchone() == (22,)
    connection.close()


def test_incomplete_package_is_quarantined_and_not_ml_eligible(tmp_path: Path) -> None:
    connection = connect(tmp_path / "incomplete.duckdb")
    migrate(connection)
    payload = _payload()
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2026, "current": True, "coverage": {}},
        admitted=True,
        reason="qualified",
        priority=1,
    )
    upsert_fixture(connection, normalize_fixture(payload), season_id, "fixture.json.gz")
    payload["players"][0]["players"][0]["statistics"][0]["games"]["minutes"] = None

    class IncompleteProvider(Provider):
        def get(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            if args[0] == "/fixtures/players":
                return payload["players"]
            return [payload]

    result = DetailedMatchIngestionService(
        connection,
        IncompleteProvider(),
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: "details.json.gz",
    ).run([100])
    assert result.fixtures_quarantined == 1
    assert connection.execute("SELECT eligibility FROM fixture_quality_status").fetchone() == ("PENDING_REPAIR",)
    assert connection.execute("SELECT count(*) FROM data_quality_issues").fetchone() == (1,)
    assert len(list((tmp_path / "quarantine").glob("*.json"))) == 1
    connection.close()


def test_action_nulls_and_unused_substitutes_do_not_fail_player_core_completeness() -> None:
    payload = _payload()
    played = payload["players"][0]["players"][0]["statistics"][0]
    played["shots"]["total"] = None
    played["tackles"]["total"] = None
    payload["players"][0]["players"].append(
        {
            "player": {"id": 1020, "name": "Unused"},
            "statistics": [
                {
                    "games": {"minutes": None, "substitute": True},
                    "shots": {"total": None},
                    "passes": {"total": None},
                }
            ],
        }
    )
    assert assess_match_package(payload).eligibility.value == "ML_ELIGIBLE"


def test_zero_id_provider_placeholders_are_not_canonicalized(tmp_path: Path) -> None:
    connection = connect(tmp_path / "placeholder-player.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2026, "current": True, "coverage": {}},
        admitted=True,
        reason="qualified",
        priority=1,
    )
    payload = _payload()
    placeholder = _player(0)
    placeholder["player"]["name"] = "Unknown A"
    second = copy.deepcopy(placeholder)
    second["player"]["name"] = "Unknown B"
    payload["players"][0]["players"].extend([placeholder, second])
    upsert_fixture(connection, normalize_fixture(payload), season_id, "fixture.json.gz")

    class PlaceholderProvider(Provider):
        def get(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            return [payload]

    result = DetailedMatchIngestionService(
        connection,
        PlaceholderProvider(),
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: "details.json.gz",
    ).run([100])
    assert result.fixtures_eligible == 1
    assert connection.execute("SELECT count(*) FROM player_match_statistics").fetchone() == (22,)
    connection.close()


def test_daily_update_discovers_globally_filters_locally_and_is_idempotent(tmp_path: Path) -> None:
    connection = connect(tmp_path / "daily.duckdb")
    migrate(connection)
    upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2024, "current": False, "coverage": {}},
        admitted=False,
        replay_eligible=True,
        ledger_mode="replay",
        reason="replay-only",
        priority=1,
    )
    completed = _payload()
    completed["league"]["season"] = 2024
    completed["fixture"]["date"] = "2024-05-20T12:00:00+00:00"
    tomorrow = _payload()
    tomorrow["fixture"] = {
        "id": 101,
        "date": "2024-05-22T12:00:00+00:00",
        "status": {"short": "NS", "long": "Not Started", "elapsed": None},
    }
    tomorrow["league"]["season"] = 2024
    tomorrow["goals"] = {"home": None, "away": None}

    class DailyProvider:
        def __init__(self) -> None:
            self.detail_calls = 0

        def get(
            self,
            endpoint: str,
            parameters: Mapping[str, Any],
            *,
            purpose: str,
            priority: Priority,
            job_run_id: str | None = None,
        ) -> list[dict[str, Any]]:
            if "ids" in parameters:
                self.detail_calls += 1
                return [completed]
            if parameters["date"] == "2024-05-20":
                return [completed]
            if parameters["date"] == "2024-05-22":
                return [tomorrow]
            return []

    provider = DailyProvider()
    service = DailyUpdateService(
        connection,
        provider,
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    )
    first = service.run(date(2024, 5, 21), ledger_mode="replay")
    second = service.run(date(2024, 5, 21), ledger_mode="replay")
    assert first.relevant_fixtures == 2 and first.completed_candidates == 1
    assert first.enrichment.fixtures_eligible == 1
    assert second.completed_candidates == 0
    assert provider.detail_calls == 1
    assert connection.execute("SELECT count(*) FROM fixtures").fetchone() == (2,)
    assert connection.execute("SELECT count(*) FROM fixture_events").fetchone() == (1,)
    connection.close()


def test_plan_restricted_batch_falls_back_to_full_single_fixture_response(tmp_path: Path) -> None:
    connection = connect(tmp_path / "fallback.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2024, "current": False, "coverage": {}},
        admitted=False,
        replay_eligible=True,
        ledger_mode="replay",
        reason="replay-only",
        priority=1,
    )
    payload = _payload()
    payload["league"]["season"] = 2024
    upsert_fixture(connection, normalize_fixture(payload), season_id, "fixture.json.gz")

    class RestrictedBatchProvider(Provider):
        def __init__(self) -> None:
            self.parameters: list[dict[str, Any]] = []

        def get(
            self,
            endpoint: str,
            parameters: Mapping[str, Any],
            *,
            purpose: str,
            priority: Priority,
            job_run_id: str | None = None,
        ) -> list[dict[str, Any]]:
            self.parameters.append(dict(parameters))
            if "ids" in parameters:
                raise ApiFootballPlanRestrictionError(
                    endpoint="/fixtures",
                    parameters=parameters,
                    provider_message="Ids parameter unavailable",
                    subscription_plan="Free",
                )
            return [payload]

    provider = RestrictedBatchProvider()
    result = DetailedMatchIngestionService(
        connection,
        provider,
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    ).run([100])
    assert result.fixtures_eligible == 1
    assert provider.parameters == [{"ids": "100"}, {"id": 100}]
    connection.close()


def test_missing_embedded_statistics_use_targeted_repair_endpoints(tmp_path: Path) -> None:
    connection = connect(tmp_path / "repair.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2024, "current": False, "coverage": {}},
        admitted=False,
        replay_eligible=True,
        ledger_mode="replay",
        reason="replay-only",
        priority=1,
    )
    complete = _payload()
    complete["league"]["season"] = 2024
    upsert_fixture(connection, normalize_fixture(complete), season_id, "fixture.json.gz")
    initial = dict(complete)
    initial["statistics"] = []
    initial["players"] = []

    class RepairProvider(Provider):
        def __init__(self) -> None:
            self.endpoints: list[str] = []

        def get(
            self,
            endpoint: str,
            parameters: Mapping[str, Any],
            *,
            purpose: str,
            priority: Priority,
            job_run_id: str | None = None,
        ) -> list[dict[str, Any]]:
            self.endpoints.append(str(endpoint))
            if endpoint == "/fixtures":
                return [initial]
            if endpoint == "/fixtures/statistics":
                return complete["statistics"]
            if endpoint == "/fixtures/players":
                return complete["players"]
            raise AssertionError(endpoint)

    provider = RepairProvider()
    result = DetailedMatchIngestionService(
        connection,
        provider,
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: f"{purpose}.json.gz",
    ).run([100])
    assert result.fixtures_eligible == 1
    assert provider.endpoints == [
        "/fixtures",
        "/fixtures/statistics",
        "/fixtures/players",
    ]
    connection.close()


def test_completeness_soak_reports_assessed_and_unassessed_counts(tmp_path: Path) -> None:
    connection = connect(tmp_path / "soak.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2024, "current": False, "coverage": {}},
        admitted=False,
        replay_eligible=True,
        ledger_mode="replay",
        reason="replay-only",
        priority=1,
    )
    payload = _payload()
    payload["league"]["season"] = 2024
    upsert_fixture(connection, normalize_fixture(payload), season_id, "fixture.json.gz")
    result = CompletenessSoakService(
        connection,
        Provider(),
        tmp_path / "quarantine",
        tmp_path / "reports",
        raw_path_resolver=lambda purpose, run_id: "details.json.gz",
    ).run(
        ledger_mode="replay",
        league_limit=1,
        fixtures_per_league=1,
        repair_attempt_limit=3,
        job_run_id=None,
    )
    assert (result.fixtures_sampled, result.fixtures_assessed, result.fixtures_unassessed) == (1, 1, 0)
    assert (result.fully_complete, result.ml_eligible, result.quarantined) == (1, 1, 0)
    assert result.report_path.exists()
    connection.close()


def test_rerun_after_commit_before_checkpoint_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    connection = connect(tmp_path / "post-commit-crash.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2024, "current": False, "coverage": {}},
        admitted=False,
        replay_eligible=True,
        ledger_mode="replay",
        reason="replay-only",
        priority=1,
    )
    payload = _payload()
    payload["league"]["season"] = 2024
    upsert_fixture(connection, normalize_fixture(payload), season_id, "fixture.json.gz")
    real_put = checkpoints.put
    calls = 0

    def crash_once(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("crash after commit")
        real_put(*args, **kwargs)

    monkeypatch.setattr(checkpoints, "put", crash_once)
    service = DetailedMatchIngestionService(
        connection,
        Provider(),
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: "details.json.gz",
    )
    with pytest.raises(RuntimeError, match="after commit"):
        service.run([100])
    assert connection.execute("SELECT count(*) FROM fixture_quality_status").fetchone() == (1,)
    monkeypatch.setattr(checkpoints, "put", real_put)
    assert service.run([100]).fixtures_eligible == 1
    assert connection.execute("SELECT count(*) FROM fixture_quality_status").fetchone() == (1,)
    assert connection.execute("SELECT count(*) FROM fixture_events").fetchone() == (1,)
    connection.close()


def test_batch_quota_interruption_resumes_without_duplicates(tmp_path: Path) -> None:
    connection = connect(tmp_path / "batch-resume.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2024, "current": False, "coverage": {}},
        admitted=False,
        replay_eligible=True,
        ledger_mode="replay",
        reason="replay-only",
        priority=1,
    )
    first = _payload()
    first["league"]["season"] = 2024
    second = copy.deepcopy(first)
    second["fixture"]["id"] = 101
    for payload in (first, second):
        upsert_fixture(connection, normalize_fixture(payload), season_id, "fixture.json.gz")
    incomplete_second = copy.deepcopy(second)
    incomplete_second["players"] = []

    class InterruptedBatchProvider:
        def get(self, endpoint: str, parameters: Mapping[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
            if endpoint == "/fixtures":
                return [first, incomplete_second]
            raise QuotaExhaustedError("protected reserve")

    interrupted = DetailedMatchIngestionService(
        connection,
        InterruptedBatchProvider(),
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: "details.json.gz",
    ).run([100, 101])
    assert not interrupted.complete and interrupted.fixtures_eligible == 1 and interrupted.next_batch_index == 0

    class ResumedBatchProvider:
        def get(self, endpoint: str, parameters: Mapping[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
            assert endpoint == "/fixtures"
            return [first, second]

    resumed = DetailedMatchIngestionService(
        connection,
        ResumedBatchProvider(),
        tmp_path / "quarantine",
        raw_path_resolver=lambda purpose, run_id: "details.json.gz",
    ).run([100, 101])
    assert resumed.complete and resumed.fixtures_eligible == 2
    assert connection.execute("SELECT count(*) FROM fixture_quality_status").fetchone() == (2,)
    assert connection.execute("SELECT count(*) FROM fixture_events").fetchone() == (2,)
    connection.close()


def test_point_in_time_dataset_uses_only_prior_observed_matches(tmp_path: Path) -> None:
    connection = connect(tmp_path / "features.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2026, "current": True, "coverage": {}},
        admitted=True,
        reason="qualified",
        priority=1,
    )
    base = datetime(2026, 1, 1, 12, tzinfo=UTC)
    for index in range(3):
        payload = copy.deepcopy(_payload())
        payload["fixture"]["id"] = 200 + index
        kickoff = base + timedelta(days=index * 10)
        payload["fixture"]["date"] = kickoff.isoformat()
        payload["goals"] = {"home": index + 1, "away": index}
        upsert_fixture(connection, normalize_fixture(payload), season_id, f"fixture-{index}.json.gz")
        persist_match_package(
            connection,
            payload,
            assess_match_package(payload),
            source_raw_path=f"details-{index}.json.gz",
            retrieved_at=kickoff + timedelta(days=1),
        )
    artifact = PointInTimeFeatureBuilder(
        connection,
        tmp_path / "parquet",
        windows=[3, 5],
        exponential_half_life=5,
        prediction_lead_hours=24,
    ).build("training", ledger_mode="production")
    frame = pl.read_parquet(artifact.parquet_path)
    assert artifact.row_count == 3
    assert frame["home_goals_for_l3"].to_list() == [None, 1.0, 1.5]
    assert all(
        source <= prediction
        for source, prediction in zip(frame["source_observation_max"], frame["prediction_timestamp"], strict=True)
    )
    assert connection.execute("SELECT count(*) FROM feature_datasets").fetchone() == (1,)
    connection.close()
