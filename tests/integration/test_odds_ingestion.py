import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from sports_engine.analysis.service import AnalysisService
from sports_engine.core.config import ShadowCandidateConfig
from sports_engine.core.enums import Priority
from sports_engine.markets.odds_age_research import refresh_odds_age_research
from sports_engine.markets.pricing import CoreMarketPrices
from sports_engine.sports.football.features.dataset import PointInTimeFeatureBuilder
from sports_engine.sports.football.ingestion.odds import OddsIngestionService
from sports_engine.sports.football.normalization.fixtures import normalize_fixture
from sports_engine.sports.football.normalization.odds import normalize_odds
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate
from sports_engine.warehouse.repositories.fixtures import upsert_fixture
from sports_engine.warehouse.repositories.leagues import upsert_competition_season
from sports_engine.warehouse.repositories.odds import store_odds_snapshot


def _fixture(provider_id: int) -> dict[str, Any]:
    return {
        "fixture": {
            "id": provider_id,
            "date": "2026-10-08T12:00:00+00:00",
            "status": {"short": "NS", "long": "Not Started", "elapsed": None},
        },
        "league": {"id": 39, "season": 2026, "round": "Round 1"},
        "teams": {
            "home": {"id": 10, "name": "Home"},
            "away": {"id": 11, "name": "Away"},
        },
        "goals": {"home": None, "away": None},
    }


def _odds(provider_fixture_id: int) -> dict[str, Any]:
    return {
        "fixture": {"id": provider_fixture_id},
        "update": "2026-10-07T10:00:00+00:00",
        "bookmakers": [
            {
                "id": 1,
                "name": "Book",
                "bets": [
                    {
                        "id": 5,
                        "name": "Goals Over/Under",
                        "values": [
                            {"value": "Over 2.5", "odd": "1.90"},
                            {"value": "Under 2.5", "odd": "2.00"},
                            {"value": "Over 3.5", "odd": "2.80"},
                            {"value": "Under 3.5", "odd": "1.45"},
                        ],
                    },
                    {
                        "id": 6,
                        "name": "Asian Handicap",
                        "values": [
                            {"value": "Home -1.0", "odd": "2.10"},
                            {"value": "Away +1.0", "odd": "1.80"},
                        ],
                    },
                ],
            }
        ],
    }


def _database(tmp_path: Path) -> Any:
    connection = connect(tmp_path / "odds.duckdb")
    migrate(connection)
    season_id = upsert_competition_season(
        connection,
        {"id": 39, "name": "League"},
        {"year": 2026, "current": True, "coverage": {}},
        admitted=True,
        reason="qualified",
        priority=1,
    )
    for provider_id in (100, 101):
        upsert_fixture(connection, normalize_fixture(_fixture(provider_id)), season_id, "fixture.json.gz")
    return connection


def test_odds_snapshot_preserves_lines_probabilities_and_deduplicates(tmp_path: Path) -> None:
    connection = _database(tmp_path)
    prices = normalize_odds(_odds(100))
    assert [(price.selection_name, price.line) for price in prices] == [
        ("Over", "2.5"),
        ("Under", "2.5"),
        ("Over", "3.5"),
        ("Under", "3.5"),
        ("Home", "-1.0"),
        ("Away", "+1.0"),
    ]
    observed = datetime(2026, 10, 7, 10, tzinfo=UTC)
    assert store_odds_snapshot(
        connection,
        prices,
        source_raw_path="odds.json.gz",
        job_run_id=None,
        observed_at=observed,
    )
    assert not store_odds_snapshot(
        connection,
        list(reversed(prices)),
        source_raw_path="odds.json.gz",
        job_run_id=None,
        observed_at=observed + timedelta(seconds=30),
    )
    assert not store_odds_snapshot(
        connection,
        prices,
        source_raw_path="odds-later.json.gz",
        job_run_id=None,
        observed_at=observed + timedelta(minutes=5),
    )
    assert connection.execute("SELECT count(*) FROM odds_snapshots").fetchone() == (1,)
    rows = connection.execute(
        "SELECT s.line, p.raw_implied_probability, p.fair_probability, p.overround "
        "FROM odds_prices p JOIN bet_selections s USING (selection_id) "
        "ORDER BY s.line, p.decimal_odds"
    ).fetchall()
    assert len(rows) == 6
    assert all(row[1] > 0 and row[2] > 0 and row[3] > 1 for row in rows)
    fair_by_line = connection.execute(
        "SELECT s.line, sum(p.fair_probability) FROM odds_prices p "
        "JOIN bet_selections s USING (selection_id) JOIN bet_markets m ON m.market_id=p.market_id "
        "WHERE m.name='Goals Over/Under' GROUP BY s.line ORDER BY s.line"
    ).fetchall()
    assert fair_by_line == [("2.5", pytest.approx(1.0)), ("3.5", pytest.approx(1.0))]
    connection.close()


def test_invalid_provider_prices_are_excluded_without_losing_valid_selections() -> None:
    payload = _odds(100)
    payload["bookmakers"][0]["bets"][0]["values"].extend(
        [{"value": "Invalid", "odd": "0"}, {"value": "Malformed", "odd": "n/a"}]
    )
    prices = normalize_odds(payload)
    assert len(prices) == 6
    assert all(price.decimal_odds > 1 for price in prices)


def test_analysis_cache_preserves_persisted_no_vig_handicap_pair(tmp_path: Path) -> None:
    connection = _database(tmp_path)
    payload = _odds(100)
    payload["bookmakers"][0]["bets"][1]["id"] = 4
    # API-Football expresses both selections using the home-team line.
    payload["bookmakers"][0]["bets"][1]["values"][1]["value"] = "Away -1.0"
    observed = datetime(2026, 10, 7, 10, tzinfo=UTC)
    assert store_odds_snapshot(
        connection,
        normalize_odds(payload),
        source_raw_path="handicap.json.gz",
        job_run_id=None,
        observed_at=observed,
    )
    fixture_id = str(connection.execute("SELECT fixture_id FROM fixtures WHERE provider_fixture_id=100").fetchone()[0])
    service = AnalysisService(
        connection,
        tmp_path / "reports",
        shadow_policy=ShadowCandidateConfig(allowed_markets=["ASIAN_HANDICAP"]),
    )
    service._load_reference_quote_cache(observed + timedelta(hours=1), None)

    home = service._reference_quote_cache[(fixture_id, "ASIAN_HANDICAP", "HOME", "-1.0")][0]
    away = service._reference_quote_cache[(fixture_id, "ASIAN_HANDICAP", "AWAY", "-1.0")][0]

    assert home.fair_probability is not None
    assert away.fair_probability is not None
    assert home.fair_probability == pytest.approx((1 / 2.1) / (1 / 2.1 + 1 / 1.8))
    assert away.fair_probability == pytest.approx((1 / 1.8) / (1 / 2.1 + 1 / 1.8))
    assert home.fair_probability + away.fair_probability == pytest.approx(1.0)

    rows = service._observed_supported_market_rows(
        fixture_id,
        CoreMarketPrices.from_expected_goals(1.4, 1.1),
        [],
    )
    away_settlement = next(
        settlement
        for market, selection, line_key, _, settlement in rows
        if (market, selection, line_key) == ("ASIAN_HANDICAP", "AWAY", "-1.0")
    )
    expected = CoreMarketPrices.from_expected_goals(1.4, 1.1).asian_handicap(1.0, "away")
    wrong_sign = CoreMarketPrices.from_expected_goals(1.4, 1.1).asian_handicap(-1.0, "away")
    assert away_settlement == expected
    assert away_settlement != wrong_sign
    connection.close()


def test_double_chance_de_vig_and_selection_mapping_are_coherent(tmp_path: Path) -> None:
    connection = _database(tmp_path)
    payload = {
        "fixture": {"id": 100},
        "update": "2026-10-07T10:00:00+00:00",
        "bookmakers": [
            {
                "id": 1,
                "name": "Book",
                "bets": [
                    {
                        "id": 12,
                        "name": "Double Chance",
                        "values": [
                            {"value": "Home/Draw", "odd": "1.30"},
                            {"value": "Home/Away", "odd": "1.22"},
                            {"value": "Draw/Away", "odd": "2.10"},
                        ],
                    }
                ],
            }
        ],
    }
    observed = datetime(2026, 10, 7, 10, tzinfo=UTC)
    assert store_odds_snapshot(
        connection,
        normalize_odds(payload),
        source_raw_path="double-chance.json.gz",
        job_run_id=None,
        observed_at=observed,
    )
    fair = connection.execute(
        "SELECT sum(p.fair_probability), min(p.overround), max(p.overround) "
        "FROM odds_prices p JOIN bet_markets m USING (market_id) WHERE m.provider_market_id=12"
    ).fetchone()
    assert fair[0] == pytest.approx(2.0)
    assert fair[1] == fair[2] and fair[1] > 1.0

    fixture_id = str(connection.execute("SELECT fixture_id FROM fixtures WHERE provider_fixture_id=100").fetchone()[0])
    service = AnalysisService(
        connection,
        tmp_path / "reports",
        shadow_policy=ShadowCandidateConfig(allowed_markets=["DOUBLE_CHANCE"]),
    )
    service._load_reference_quote_cache(observed + timedelta(hours=1), None)
    assert {key[2] for key in service._reference_quote_cache if key[:2] == (fixture_id, "DOUBLE_CHANCE")} == {
        "HOME/DRAW",
        "HOME/AWAY",
        "DRAW/AWAY",
    }
    rows = service._observed_supported_market_rows(
        fixture_id,
        CoreMarketPrices.from_expected_goals(1.4, 1.1),
        [],
    )
    assert {selection for market, selection, _, _, _ in rows if market == "DOUBLE_CHANCE"} == {
        "HOME/DRAW",
        "HOME/AWAY",
        "DRAW/AWAY",
    }
    connection.close()


def test_incomplete_double_chance_book_preserves_unknown_fair_probability(tmp_path: Path) -> None:
    connection = _database(tmp_path)
    payload = {
        "fixture": {"id": 100},
        "update": "2026-10-07T10:00:00+00:00",
        "bookmakers": [
            {
                "id": 1,
                "name": "Book",
                "bets": [
                    {
                        "id": 12,
                        "name": "Double Chance",
                        "values": [
                            {"value": "Home/Draw", "odd": "1.30"},
                            {"value": "Draw/Away", "odd": "2.10"},
                        ],
                    }
                ],
            }
        ],
    }

    assert store_odds_snapshot(
        connection,
        normalize_odds(payload),
        source_raw_path="incomplete-double-chance.json.gz",
        job_run_id=None,
        observed_at=datetime(2026, 10, 7, 10, tzinfo=UTC),
    )
    rows = connection.execute(
        "SELECT p.fair_probability, p.overround FROM odds_prices p "
        "JOIN bet_markets m USING (market_id) WHERE m.provider_market_id=12"
    ).fetchall()
    assert len(rows) == 2
    assert all(fair_probability is None and overround is None for fair_probability, overround in rows)
    connection.close()


def test_point_in_time_odds_features_use_latest_price_and_detect_prior_movement(tmp_path: Path) -> None:
    connection = _database(tmp_path)

    def payload(update: str, home_odds: str) -> dict[str, Any]:
        return {
            "fixture": {"id": 100},
            "update": update,
            "bookmakers": [
                {
                    "id": 1,
                    "name": "Book",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": home_odds},
                                {"value": "Draw", "odd": "3.20"},
                                {"value": "Away", "odd": "3.80"},
                            ],
                        }
                    ],
                }
            ],
        }

    first = datetime(2026, 10, 7, 8, tzinfo=UTC)
    second = datetime(2026, 10, 7, 10, tzinfo=UTC)
    assert store_odds_snapshot(
        connection,
        normalize_odds(payload(first.isoformat(), "2.10")),
        source_raw_path="first.json.gz",
        job_run_id=None,
        observed_at=first,
    )
    assert store_odds_snapshot(
        connection,
        normalize_odds(payload(second.isoformat(), "1.90")),
        source_raw_path="second.json.gz",
        job_run_id=None,
        observed_at=second,
    )
    fixture_id = str(connection.execute("SELECT fixture_id FROM fixtures WHERE provider_fixture_id=100").fetchone()[0])
    builder = PointInTimeFeatureBuilder(
        connection,
        tmp_path / "features",
        windows=[5],
        exponential_half_life=5,
        prediction_lead_hours=24,
    )

    before_move = builder._odds_features(fixture_id, first)
    after_move = builder._odds_features(fixture_id, second)

    assert not before_move["odds_movement_known"]
    assert after_move["odds_movement_known"]
    assert after_move["bookmaker_home_fair"] != before_move["bookmaker_home_fair"]
    connection.close()


def test_odds_service_consumes_all_pages_and_skips_unknown_fixtures(tmp_path: Path) -> None:
    connection = _database(tmp_path)

    class Provider:
        def get_all_pages(
            self,
            endpoint: str,
            parameters: Mapping[str, Any],
            *,
            purpose: str,
            priority: Priority,
            job_run_id: str | None = None,
        ) -> Iterator[dict[str, Any]]:
            assert parameters == {"date": "2026-10-08"}
            yield _odds(100)
            yield _odds(999)

    result = OddsIngestionService(
        connection,
        Provider(),
        raw_path_resolver=lambda purpose, run_id: "odds.json.gz",
    ).run(date(2026, 10, 8))
    assert (result.payloads_seen, result.snapshots_written, result.fixtures_not_in_ledger) == (2, 1, 1)
    connection.close()


@pytest.mark.parametrize("universe_state", ["ACTIONABLE", "OBSERVATION"])
def test_odds_service_scopes_requests_to_scheduled_governed_leagues(tmp_path: Path, universe_state: str) -> None:
    connection = _database(tmp_path)
    season_id = connection.execute("SELECT competition_season_id FROM competition_seasons").fetchone()[0]
    connection.execute(
        "INSERT INTO competition_discoveries VALUES "
        "(?, 'api_football', 39, 2026, ?, 'League', 'England', 'League', ?, "
        "1, 0, 1, '{}', 1, 1, 1, 0, 1, '[]', 1, NULL, ?)",
        [str(uuid.uuid4()), season_id, universe_state, datetime.now(UTC)],
    )
    requested: list[Mapping[str, Any]] = []

    class Provider:
        def get_all_pages(
            self,
            endpoint: str,
            parameters: Mapping[str, Any],
            *,
            purpose: str,
            priority: Priority,
            job_run_id: str | None = None,
        ) -> Iterator[dict[str, Any]]:
            requested.append(parameters)
            yield _odds(100)

    result = OddsIngestionService(
        connection,
        Provider(),
        raw_path_resolver=lambda purpose, run_id: "odds.json.gz",
    ).run(date(2026, 10, 8), ledger_mode="production", timezone="UTC")
    assert requested == [{"date": "2026-10-08", "league": 39, "season": 2026}]
    assert result.snapshots_written == 1
    assert result.request_scopes == 1
    assert result.blocked_reason is None
    connection.close()


def test_odds_service_exposes_empty_governed_scope_instead_of_silently_skipping(tmp_path: Path) -> None:
    connection = _database(tmp_path)

    class Provider:
        def get_all_pages(self, *args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
            raise AssertionError("provider must not be called without a governed competition scope")

    result = OddsIngestionService(connection, Provider()).run(
        date(2026, 10, 8), ledger_mode="production", timezone="UTC"
    )

    assert result.request_scopes == 0
    assert result.payloads_seen == 0
    assert result.blocked_reason == "NO_GOVERNED_COMPETITION_SCOPE"
    connection.close()


def test_odds_service_restarts_safely_after_page_interruption(tmp_path: Path) -> None:
    connection = _database(tmp_path)

    class InterruptedProvider:
        def get_all_pages(self, *args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
            yield _odds(100)
            raise RuntimeError("simulated failure between pages")

    service = OddsIngestionService(
        connection,
        InterruptedProvider(),
        raw_path_resolver=lambda purpose, run_id: "odds-page-1.json.gz",
    )
    with pytest.raises(RuntimeError, match="between pages"):
        service.run(date(2026, 10, 8))
    assert connection.execute("SELECT count(*) FROM odds_snapshots").fetchone() == (1,)

    class ResumedProvider:
        def get_all_pages(self, *args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
            yield _odds(100)
            yield _odds(101)

    result = OddsIngestionService(
        connection,
        ResumedProvider(),
        raw_path_resolver=lambda purpose, run_id: "odds-resumed.json.gz",
    ).run(date(2026, 10, 8))
    assert result.payloads_seen == 2
    assert connection.execute("SELECT count(*) FROM odds_snapshots").fetchone() == (2,)
    connection.close()


def test_odds_age_research_is_persisted_without_activating_penalty(tmp_path: Path) -> None:
    connection = _database(tmp_path)
    first_payload = _odds(100)
    first_payload["update"] = "2026-10-07T08:00:00+00:00"
    second_payload = _odds(100)
    second_payload["update"] = "2026-10-07T10:00:00+00:00"
    second_payload["bookmakers"][0]["bets"][0]["values"][0]["odd"] = "2.10"
    assert store_odds_snapshot(
        connection,
        normalize_odds(first_payload),
        source_raw_path="first.json.gz",
        job_run_id=None,
        observed_at=datetime(2026, 10, 7, 8, tzinfo=UTC),
    )
    assert store_odds_snapshot(
        connection,
        normalize_odds(second_payload),
        source_raw_path="second.json.gz",
        job_run_id=None,
        observed_at=datetime(2026, 10, 7, 10, tzinfo=UTC),
    )
    completed = _fixture(100)
    completed["fixture"]["status"] = {"short": "FT", "long": "Match Finished", "elapsed": 90}
    completed["goals"] = {"home": 2, "away": 1}
    season_id = connection.execute("SELECT competition_season_id FROM competition_seasons LIMIT 1").fetchone()[0]
    upsert_fixture(connection, normalize_fixture(completed), season_id, "completed.json.gz")
    result = refresh_odds_age_research(connection, minimum_scope_sample=1)
    assert result.observations > 0 and result.scopes_written > 0
    assert connection.execute(
        "SELECT count(*), bool_or(production_penalty_qualified) FROM odds_age_research_results"
    ).fetchone() == (result.scopes_written, False)
    connection.close()
