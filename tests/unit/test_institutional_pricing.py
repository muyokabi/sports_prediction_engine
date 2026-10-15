from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sports_engine.analysis.dates import resolve_analysis_dates
from sports_engine.analysis.dependencies import (
    DependencyState,
    FreshnessState,
    ScheduledFixture,
    assess_intervening_fixtures,
    freshness_after_change,
)
from sports_engine.markets.implied_probability import power_probabilities, shin_probabilities
from sports_engine.markets.pricing import CoreMarketPrices
from sports_engine.markets.score_distribution import ScoreDistribution
from sports_engine.markets.settlement import SettlementDistribution, check_manual_price
from sports_engine.markets.taxonomy import (
    MarketState,
    classify_api_football_market,
    persist_observed_api_football_markets,
)
from sports_engine.reporting.html import DailyAnalysisReport, FixtureAuditRow, OpportunityRow, render_daily_analysis
from sports_engine.warehouse.connection import connect
from sports_engine.warehouse.migrations import migrate


def test_dynamic_score_distribution_normalizes_and_bounds_tail() -> None:
    low = ScoreDistribution.poisson(1.4, 1.1, tail_tolerance=1e-12)
    high = ScoreDistribution.poisson(8.5, 7.0, tail_tolerance=1e-12)
    assert low.probabilities.sum() == pytest.approx(1.0)
    assert high.probabilities.sum() == pytest.approx(1.0)
    assert low.omitted_probability <= 1e-12
    assert high.omitted_probability <= 1e-12
    assert high.probabilities.shape[0] > low.probabilities.shape[0]


def test_core_markets_are_coherent() -> None:
    prices = CoreMarketPrices.from_expected_goals(1.7, 1.0)
    reconstructed = CoreMarketPrices.from_distribution(prices.distribution)
    assert prices.home + prices.draw + prices.away == pytest.approx(1.0)
    assert prices.btts_yes + prices.btts_no == pytest.approx(1.0)
    assert reconstructed.home == pytest.approx(prices.home)
    assert prices.double_chance()["1X"] == pytest.approx(prices.home + prices.draw)
    dnb = prices.draw_no_bet("home")
    assert dnb.full_win == pytest.approx(prices.home)
    assert dnb.push == pytest.approx(prices.draw)
    assert dnb.full_loss == pytest.approx(prices.away)


@pytest.mark.parametrize(
    ("line", "expected_nonzero"),
    [
        (-1.0, {"full_win", "push", "full_loss"}),
        (-0.5, {"full_win", "full_loss"}),
        (-0.25, {"full_win", "half_loss", "full_loss"}),
    ],
)
def test_asian_handicap_settlement(line: float, expected_nonzero: set[str]) -> None:
    result = CoreMarketPrices.from_expected_goals(1.4, 1.1).asian_handicap(line, "home")
    assert sum(result.as_dict().values()) == pytest.approx(1.0)
    assert {name for name in expected_nonzero if getattr(result, name) > 0} == expected_nonzero
    fair = result.fair_odds()
    assert fair is not None
    assert result.expected_return(fair) == pytest.approx(0.0)


def test_asian_quarter_total_has_half_settlement_and_minimum_odds() -> None:
    result = CoreMarketPrices.from_expected_goals(1.5, 1.2).total(2.25, "over")
    assert result.half_loss > 0
    fair = result.fair_odds()
    minimum = result.minimum_odds(0.03)
    assert fair is not None and minimum is not None and minimum > fair
    assert result.expected_return(minimum) == pytest.approx(0.03)
    complement = CoreMarketPrices.from_expected_goals(1.5, 1.2).total(2.25, "under")
    assert complement.half_win == pytest.approx(result.half_loss)
    assert complement.full_loss == pytest.approx(result.full_win)


def test_manual_execution_price_uses_settlement_aware_threshold() -> None:
    quarter = SettlementDistribution(full_win=0.45, half_win=0.10, push=0.10, half_loss=0.10, full_loss=0.25)
    minimum = quarter.minimum_odds(0.03)
    assert minimum is not None
    assert check_manual_price(quarter, minimum, required_expected_return=0.03).passes
    assert not check_manual_price(quarter, minimum - 0.01, required_expected_return=0.03).passes


def test_team_totals_and_correct_score() -> None:
    prices = CoreMarketPrices.from_expected_goals(1.2, 0.8)
    home_over = prices.team_total(0.5, team="home", side="over")
    assert home_over.full_win == pytest.approx(1 - prices.distribution.probabilities[0, :].sum())
    assert prices.correct_score(1, 0) > 0


def test_power_and_shin_devig_are_valid_and_distinct() -> None:
    proportional = [1 / value / sum(1 / odd for odd in (2.2, 3.4, 3.5)) for value in (2.2, 3.4, 3.5)]
    power = power_probabilities([2.2, 3.4, 3.5])
    shin = shin_probabilities([2.2, 3.4, 3.5])
    assert power.sum() == pytest.approx(1.0)
    assert shin.sum() == pytest.approx(1.0)
    assert list(power) != pytest.approx(proportional)
    assert list(shin) != pytest.approx(proportional)


def test_market_taxonomy_never_guesses_unknown_or_name_mismatch() -> None:
    assert classify_api_football_market(4, "Asian Handicap").state == MarketState.SUPPORTED
    assert classify_api_football_market(4, "Ambiguous Handicap").state == MarketState.DISABLED
    assert classify_api_football_market(9999, "Mystery").state == MarketState.UNSUPPORTED_SETTLEMENT


def test_observed_market_taxonomy_is_persisted(tmp_path: Path) -> None:
    connection = connect(tmp_path / "taxonomy.duckdb")
    migrate(connection)
    connection.execute("INSERT INTO bet_markets VALUES (uuid(), 4, 'Asian Handicap'), (uuid(), 9999, 'Mystery')")
    assert persist_observed_api_football_markets(connection) == 2
    assert connection.execute("SELECT state FROM canonical_market_mappings WHERE provider_market_id=4").fetchone() == (
        "SUPPORTED",
    )
    assert connection.execute(
        "SELECT state FROM canonical_market_mappings WHERE provider_market_id=9999"
    ).fetchone() == ("UNSUPPORTED_SETTLEMENT",)
    connection.close()


def test_intervening_fixture_blocks_until_final_enriched_and_reconciled() -> None:
    now = datetime(2026, 10, 8, 9, tzinfo=UTC)
    target = ScheduledFixture("target", now + timedelta(days=3), "a", "b", "NS")
    intervening = ScheduledFixture("middle", now + timedelta(days=1), "a", "c", "NS")
    blocked = assess_intervening_fixtures(target, [target, intervening], analysis_timestamp=now)
    assert blocked.state == DependencyState.BLOCKED_BY_INTERVENING_FIXTURE
    resolved_fixture = ScheduledFixture("middle", intervening.kickoff, "a", "c", "FT", True, True)
    resolved = assess_intervening_fixtures(target, [target, resolved_fixture], analysis_timestamp=now)
    assert resolved.state == DependencyState.DEPENDENCY_RESOLVED
    assert freshness_after_change(change="new_odds", affects_team_state=False) == FreshnessState.MARKET_PRICE_STALE
    assert (
        freshness_after_change(change="intervening_fixture", affects_team_state=True)
        == FreshnessState.STALE_INTERVENING_FIXTURE
    )


def test_date_resolution_uses_presentation_timezone_and_bounded_range() -> None:
    now = datetime(2026, 10, 7, 22, 30, tzinfo=UTC)  # already 8 October in Nairobi
    today = resolve_analysis_dates("today", timezone="Africa/Nairobi", days=3, now=now)
    assert [value.isoformat() for value in today.dates] == ["2026-10-08", "2026-10-09", "2026-10-10"]
    assert resolve_analysis_dates("tomorrow", timezone="Africa/Nairobi", now=now).start.isoformat() == "2026-10-09"
    assert resolve_analysis_dates("2026-10-12", timezone="Africa/Nairobi", now=now).start.isoformat() == "2026-10-12"


def test_html_report_escapes_content_and_lists_full_universe(tmp_path: Path) -> None:
    now = datetime(2026, 10, 8, 9, tzinfo=UTC)
    path = render_daily_analysis(
        DailyAnalysisReport(
            now.date(),
            now.date(),
            now,
            (FixtureAuditRow("A&B", "<Home> v Away", now, "NO_QUALIFIED_MODEL", ("evidence",)),),
        ),
        tmp_path / "report.html",
    )
    document = path.read_text(encoding="utf-8")
    assert "A&amp;B" in document and "&lt;Home&gt; v Away" in document
    assert "NO_QUALIFIED_MODEL" in document
    assert "Expected fixtures" in document
    assert all(
        section in document
        for section in (
            "Overview",
            "Top forecasts",
            "Research basket",
            "Validated research",
            "Top opportunities",
            "All matches",
            "Market board",
            "Model health",
            "Data health",
            "Full universe audit",
        )
    )
    assert "No conditional market opportunities" in document
    assert "MANUAL PRICE CONFIRMATION REQUIRED" in document
    assert "not guaranteed executable prices" in document
    assert "report-data" in document
    assert "audit-league" in document
    assert "market-search" in document
    assert "filterMarket" in document
    assert "prefers-reduced-motion" in document
    assert "Football intelligence" in document


def test_html_exposes_forecasts_and_equal_stake_learning_basket(tmp_path: Path) -> None:
    now = datetime(2026, 10, 14, 9, tzinfo=UTC)

    def row(
        fixture: str,
        selection: str,
        probability: float,
        odds: float,
        expected_return: float,
        reasons: tuple[str, ...],
        *,
        level: str = "MEDIUM",
    ) -> OpportunityRow:
        fair_odds = 1 / probability
        return OpportunityRow(
            rank=1,
            competition="Learning League",
            kickoff=now,
            fixture=fixture,
            market="MATCH_ODDS",
            selection=selection,
            model_probability=probability,
            model_fair_odds=fair_odds,
            minimum_odds=fair_odds * 1.05,
            reference_odds=odds,
            bookmaker="Reference Book",
            reference_observed_at=now,
            reference_age_minutes=10.0,
            market_probability=1 / odds,
            reference_edge=probability - 1 / odds,
            robust_edge=None,
            reference_expected_return=expected_return,
            uncertainty=0.0,
            reference_state="LATEST_PROVIDER_REFERENCE",
            decision="RESEARCH_VALUE_SIGNAL",
            snapshot_count=3,
            reasons=reasons,
            applicability_state="PARTIALLY_POOLED",
            applicability_level=level,
        )

    path = render_daily_analysis(
        DailyAnalysisReport(
            now.date(),
            now.date(),
            now,
            (),
            price_targets=(
                row(
                    "A v B",
                    "HOME",
                    0.30,
                    4.20,
                    0.26,
                    ("COMPETITION_PROBABILITY_NOT_VALIDATED", "NO_MARKET_FAMILY_CHAMPION"),
                ),
                row("A v B", "AWAY", 0.45, 2.60, 0.17, ("COMPETITION_PROBABILITY_NOT_VALIDATED",)),
                row("C v D", "AWAY", 0.40, 3.00, 0.20, ("COMPETITION_PROBABILITY_NOT_VALIDATED",)),
                row(
                    "E v F",
                    "HOME",
                    0.42,
                    3.10,
                    0.30,
                    ("CALIBRATION_NOT_VALIDATED", "COMPETITION_PROBABILITY_NOT_VALIDATED"),
                ),
                row("Prior v Unknown", "HOME", 0.60, 2.00, 0.20, ("PRIOR_ONLY",), level="PRIOR_ONLY"),
            ),
        ),
        tmp_path / "report.html",
    )

    document = path.read_text(encoding="utf-8")
    forecasts = document.split('<section id="forecasts"', 1)[1].split("</section>", 1)[0]
    basket = document.split('<section id="basket"', 1)[1].split("</section>", 1)[0]

    assert "A v B" in forecasts and "C v D" in forecasts and "E v F" in forecasts
    assert "Prior v Unknown" not in forecasts
    assert "A v B" in basket and basket.count("A v B") == 1
    assert "C v D" in basket
    assert "E v F" not in basket
    assert basket.index("A v B") < basket.index("C v D")
    assert "Competition-scope validation may remain unresolved" in basket
    assert "4.0 winner covers a three-selection basket with profit" in basket
    assert "Equal-stake selections</span><span class=\"value\">2" in basket
    assert "Model expected net</span><span class=\"value\">+0.46u" in basket
    assert "One-hit whole-basket cover</span><span class=\"value\">2" in basket


def test_html_ranks_one_in_domain_research_selection_per_fixture(tmp_path: Path) -> None:
    now = datetime(2026, 10, 8, 9, tzinfo=UTC)

    def row(
        fixture: str,
        market: str,
        probability: float,
        level: str,
        reference_odds: float = 2.10,
        reasons: tuple[str, ...] = ("RESEARCH_ONLY_NOT_ACTIONABLE",),
    ) -> OpportunityRow:
        return OpportunityRow(
            rank=1,
            competition="League",
            kickoff=now,
            fixture=fixture,
            market=market,
            selection="HOME",
            model_probability=probability,
            model_fair_odds=1 / probability,
            minimum_odds=1 / probability + 0.1,
            reference_odds=reference_odds,
            bookmaker="Reference Book",
            reference_observed_at=now,
            reference_age_minutes=12.0,
            market_probability=0.48,
            reference_edge=0.22,
            robust_edge=0.17,
            reference_expected_return=0.47,
            uncertainty=0.05,
            reference_state="LATEST_PROVIDER_REFERENCE",
            decision="RESEARCH_ONLY",
            snapshot_count=4,
            price_movement=0.08,
            bookmaker_dispersion=0.04,
            reasons=reasons,
            applicability_state="FULLY_ESTIMATED" if level == "HIGH" else "PARTIALLY_POOLED",
            applicability_level=level,
        )

    path = render_daily_analysis(
        DailyAnalysisReport(
            now.date(),
            now.date(),
            now,
            (),
            price_targets=(
                row("A v B", "MATCH_ODDS", 0.70, "HIGH", 2.10),
                row("A v B", "TOTAL_GOALS 2.5", 0.80, "HIGH", 1.50),
                row("C v D", "MATCH_ODDS", 0.90, "OUT_OF_DOMAIN"),
                row("E v F", "MATCH_ODDS", 0.65, "MEDIUM"),
                row("G v H", "MATCH_ODDS", 0.70, "HIGH", 1.01),
                row("I v J", "MATCH_ODDS", 0.95, "HIGH", reasons=("AGED_REFERENCE_RECHECK_REQUIRED",)),
                row("K v L", "MATCH_ODDS", 0.60, "HIGH"),
            ),
        ),
        tmp_path / "report.html",
    )

    document = path.read_text(encoding="utf-8")
    section = document.split('<section id="research"', 1)[1].split("</section>", 1)[0]
    assert "Top 10 evidence-qualified research selections" in section
    assert section.count("A v B") == 1
    assert "MATCH_ODDS" in section
    assert "E v F" in section
    assert "C v D" not in section
    assert "G v H" not in section
    assert section.index("K v L") < section.index("I v J")
    assert "not a guarantee or statistical confidence interval" in section
    assert "Fair odds" in section
    assert "Minimum odds" in section
    assert "Expected return @ API ref" in section
    assert "Execution edge" in section
    assert "Minimum-odds test" in section
    assert "Price cushion" in section
    assert "Minimum-odds basis" in section
    assert "Bookmaker-breadth gate" in section
    assert "Shortlist evidence warnings" in section
    assert "Validated uncertainty adjustment" in section
    assert "Reference observed" in section
    assert "Valid observations" in section
    assert "Movement" in section
    assert "Dispersion" in section
    assert "Reference Book" in section
    assert "+47.0%" in section
    assert ">PASS<" in section
    assert "RESEARCH_ONLY_NOT_ACTIONABLE" in section
    assert "AGED_REFERENCE_RECHECK_REQUIRED" in section
    assert "NO_SHORTLIST_WARNING" in section
    assert "Quality funnel:" in section
    assert "Leading row-level blockers:" in section
    assert "not guaranteed executable EV" in section
    assert "If fewer than ten qualify, the table is not padded" in section


def test_html_research_shortlist_rejects_missing_evidence(tmp_path: Path) -> None:
    now = datetime(2026, 10, 8, 9, tzinfo=UTC)

    def candidate(fixture: str, level: str, reasons: tuple[str, ...]) -> OpportunityRow:
        return OpportunityRow(
            rank=1,
            competition="League",
            kickoff=now,
            fixture=fixture,
            market="MATCH_ODDS",
            selection="HOME",
            model_probability=0.60,
            model_fair_odds=1.67,
            minimum_odds=1.75,
            reference_odds=2.00,
            bookmaker="Reference Book",
            reference_observed_at=now,
            reference_age_minutes=5.0,
            market_probability=0.50,
            reference_edge=0.10,
            robust_edge=None,
            reference_expected_return=0.20,
            uncertainty=0.0,
            reference_state="LATEST_PROVIDER_REFERENCE",
            decision="RESEARCH_VALUE_SIGNAL",
            snapshot_count=3,
            reasons=reasons,
            applicability_state="PARTIALLY_POOLED" if level == "MEDIUM" else level,
            applicability_level=level,
        )

    path = render_daily_analysis(
        DailyAnalysisReport(
            now.date(),
            now.date(),
            now,
            (),
            price_targets=(
                candidate("Eligible", "MEDIUM", ("NO_MARKET_FAMILY_CHAMPION",)),
                candidate("Prior", "PRIOR_ONLY", ()),
                candidate("Uncalibrated", "HIGH", ("CALIBRATION_NOT_VALIDATED",)),
                candidate("Thin book", "HIGH", ("INSUFFICIENT_REFERENCE_BOOKMAKER_BREADTH",)),
                candidate("Prior leak", "HIGH", ("GLOBAL_PRIOR_SUBSTITUTION",)),
            ),
        ),
        tmp_path / "report.html",
    )
    section = path.read_text(encoding="utf-8").split('<section id="research"', 1)[1].split("</section>", 1)[0]
    assert "Eligible" in section
    assert "Prior" not in section
    assert "Uncalibrated" not in section
    assert "Thin book" not in section
    assert "Prior leak" not in section
    assert "WEAK_FIXTURE_APPLICABILITY" in section
    assert "CALIBRATION_NOT_VALIDATED" in section
