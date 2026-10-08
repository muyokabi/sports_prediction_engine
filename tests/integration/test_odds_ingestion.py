from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from sports_engine.core.enums import Priority
from sports_engine.markets.odds_age_research import refresh_odds_age_research
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
