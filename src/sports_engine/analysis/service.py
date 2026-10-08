import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from sports_engine.analysis.dependencies import ScheduledFixture, assess_intervening_fixtures
from sports_engine.markets.pricing import CoreMarketPrices
from sports_engine.markets.reference import ReferenceQuote, ReferenceState, classify_reference, summarize_references
from sports_engine.markets.score_distribution import ScoreDistribution
from sports_engine.markets.settlement import SettlementDistribution
from sports_engine.models.registry import MODEL_TYPES
from sports_engine.models.statistical.dixon_coles import DixonColesModel
from sports_engine.models.statistical.poisson import PoissonModel
from sports_engine.reporting.html import (
    DailyAnalysisReport,
    FixtureAuditRow,
    ModelHealthRow,
    OpportunityRow,
    render_daily_analysis,
)


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    analysis_run_id: str
    expected_fixtures: int
    terminal_fixtures: int
    state: str
    report_path: Path


@dataclass(frozen=True, slots=True)
class QualifiedFundamentalModel:
    model_type: str
    version: str
    model: PoissonModel
    feature_dataset_id: str | None


class AnalysisService:
    """Reconciles a requested fixture universe and persists explicit abstentions."""

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        report_root: Path,
        *,
        aged_reference_minutes: int = 180,
        minimum_probability_advantage: float = 0.03,
        required_robust_ev: float = 0.0,
    ) -> None:
        self.connection = connection
        self.report_root = report_root
        self.aged_reference_minutes = aged_reference_minutes
        self.minimum_probability_advantage = minimum_probability_advantage
        self.required_robust_ev = required_robust_ev
        self._reference_quote_cache: dict[tuple[str, str, str, str], list[ReferenceQuote]] = {}

    def run(
        self,
        start_date: date,
        end_date: date,
        *,
        timezone: str,
        ledger_mode: str,
        observed_at: datetime | None = None,
        job_run_id: str | None = None,
    ) -> AnalysisResult:
        if end_date < start_date:
            raise ValueError("Analysis end date cannot precede start date")
        observed = observed_at or datetime.now(UTC)
        rows = self.connection.execute(
            "SELECT CAST(f.fixture_id AS VARCHAR), f.kickoff_utc, f.status_short, "
            "CAST(f.home_team_id AS VARCHAR), h.name, CAST(f.away_team_id AS VARCHAR), a.name, c.name "
            "FROM fixtures_current f JOIN competition_seasons cs USING (competition_season_id) "
            "JOIN competitions c USING (competition_id) JOIN teams h ON h.team_id=f.home_team_id "
            "JOIN teams a ON a.team_id=f.away_team_id WHERE cs.ledger_mode=? AND cs.admitted "
            "AND CAST(timezone(?, f.kickoff_utc) AS DATE) BETWEEN ? AND ? ORDER BY f.kickoff_utc, f.fixture_id",
            [ledger_mode, timezone, start_date, end_date],
        ).fetchall()
        schedule_rows = self.connection.execute(
            "SELECT CAST(fixture_id AS VARCHAR), kickoff_utc, CAST(home_team_id AS VARCHAR), "
            "CAST(away_team_id AS VARCHAR), status_short, eligibility FROM fixtures_current"
        ).fetchall()
        schedule = [
            ScheduledFixture(
                fixture_id,
                kickoff,
                home_id,
                away_id,
                status,
                enriched=eligibility == "ML_ELIGIBLE",
                quality_passed=eligibility == "ML_ELIGIBLE",
            )
            for fixture_id, kickoff, home_id, away_id, status, eligibility in schedule_rows
        ]
        fundamental = self._load_qualified_fundamental_model()
        self._load_reference_quote_cache(observed, job_run_id)
        run_id = str(uuid.uuid4())
        self.connection.execute(
            "INSERT INTO analysis_runs (analysis_run_id, requested_start_date, requested_end_date, "
            "presentation_timezone, analysis_timestamp, source_cutoff, state, expected_fixture_count, job_run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?)",
            [run_id, start_date, end_date, timezone, observed, observed, len(rows), job_run_id],
        )
        audit_rows: list[FixtureAuditRow] = []
        prices_written = 0
        self.connection.begin()
        try:
            for fixture_id, kickoff, status, home_id, home_name, away_id, away_name, competition in rows:
                target = ScheduledFixture(fixture_id, kickoff, home_id, away_id, status)
                dependency = assess_intervening_fixtures(target, schedule, analysis_timestamp=observed)
                has_institutional_price = False
                if (
                    fundamental is not None
                    and status in {"NS", "TBD"}
                    and kickoff > observed
                    and str(dependency.state) != "BLOCKED_BY_INTERVENING_FIXTURE"
                ):
                    prices_written += self._persist_fundamental_prediction(
                        run_id,
                        target,
                        dependency.intervening_fixture_ids,
                        str(dependency.state),
                        observed,
                        fundamental,
                        job_run_id,
                    )
                    has_institutional_price = True
                terminal_state, reasons = self._terminal_state(
                    status,
                    kickoff,
                    observed,
                    dependency.state,
                    has_institutional_price=has_institutional_price,
                )
                self.connection.execute(
                    "INSERT INTO analysis_fixture_manifest "
                    "(analysis_run_id, fixture_id, terminal_state, reason_codes, processed_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [run_id, fixture_id, terminal_state, json.dumps(reasons), observed],
                )
                audit_rows.append(
                    FixtureAuditRow(
                        str(competition),
                        f"{home_name} v {away_name}",
                        kickoff,
                        terminal_state,
                        tuple(reasons),
                        self._odds_status(fixture_id, observed),
                        (
                            f"FUNDAMENTAL:{fundamental.version}"
                            if has_institutional_price and fundamental
                            else "NO_QUALIFIED_INSTITUTIONAL_PRICE"
                        ),
                        str(dependency.state),
                    )
                )
            terminal_count = len(audit_rows)
            state = "COMPLETE" if terminal_count == len(rows) else "INCOMPLETE"
            report_path = self.report_root / f"analysis-{start_date.isoformat()}-{end_date.isoformat()}-{run_id}.html"
            report_context = self._report_context(ledger_mode)
            price_targets = self._report_price_targets(run_id)
            opportunities = tuple(row for row in price_targets if row.decision in {"BET_IF_PRICE_AVAILABLE", "WATCH"})
            reference_metrics = self._reference_metrics(run_id)
            snapshots_this_run = 0
            if job_run_id:
                snapshot_row = self.connection.execute(
                    "SELECT count(*) FROM odds_snapshots WHERE CAST(job_run_id AS VARCHAR)=?",
                    [job_run_id],
                ).fetchone()
                snapshots_this_run = int(snapshot_row[0]) if snapshot_row else 0
            render_daily_analysis(
                DailyAnalysisReport(
                    start_date,
                    end_date,
                    observed,
                    tuple(audit_rows),
                    data_health="PASS" if state == "COMPLETE" else "INCOMPLETE",
                    odds_health=self._aggregate_odds_health(audit_rows),
                    model_health="QUALIFIED" if fundamental else "NO_QUALIFIED_MODEL",
                    markets_analyzed=prices_written,
                    model_versions=(fundamental.version,) if fundamental else (),
                    provider_quota=report_context["provider_quota"],
                    production_mode=ledger_mode,
                    last_data_update=report_context["last_data_update"],
                    last_odds_update=report_context["last_odds_update"],
                    admitted_leagues=report_context["admitted_leagues"],
                    observation_leagues=report_context["observation_leagues"],
                    eligible_fixtures=report_context["eligible_fixtures"],
                    model_rows=report_context["model_rows"],
                    opportunities=opportunities,
                    price_targets=price_targets,
                    qualified_opportunities=sum(row.decision == "BET_IF_PRICE_AVAILABLE" for row in opportunities),
                    reference_fixtures=int(reference_metrics["reference_fixtures"] or 0),
                    no_reference_fixtures=int(reference_metrics["no_reference_fixtures"] or 0),
                    median_reference_age_minutes=reference_metrics["median_age"],
                    newest_reference_age_minutes=reference_metrics["newest_age"],
                    oldest_reference_age_minutes=reference_metrics["oldest_age"],
                    snapshots_collected_this_run=snapshots_this_run,
                ),
                report_path,
            )
            self.connection.execute(
                "UPDATE analysis_runs SET state=?, terminal_fixture_count=?, report_path=? WHERE analysis_run_id=?",
                [state, terminal_count, str(report_path), run_id],
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            self.connection.execute("UPDATE analysis_runs SET state='FAILED' WHERE analysis_run_id=?", [run_id])
            raise
        return AnalysisResult(run_id, len(rows), terminal_count, state, report_path)

    def _load_qualified_fundamental_model(self) -> QualifiedFundamentalModel | None:
        row = self.connection.execute(
            "SELECT model_type, version, artifact_path, training_dataset_hash FROM model_runs "
            "WHERE status='champion' AND evidence_state='PRODUCTION_ACTIONABLE' "
            "AND model_type IN ('poisson','dixon-coles') ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        model_type, version, artifact_path, dataset_hash = row
        model_class = DixonColesModel if model_type == "dixon-coles" else PoissonModel
        model = model_class.load(Path(str(artifact_path)))
        dataset = self.connection.execute(
            "SELECT CAST(dataset_id AS VARCHAR) FROM feature_datasets "
            "WHERE dataset_hash=? ORDER BY created_at DESC LIMIT 1",
            [dataset_hash],
        ).fetchone()
        return QualifiedFundamentalModel(
            str(model_type),
            str(version),
            model,
            str(dataset[0]) if dataset else None,
        )

    def _persist_fundamental_prediction(
        self,
        analysis_run_id: str,
        target: ScheduledFixture,
        intervening_fixture_ids: tuple[str, ...],
        dependency_state: str,
        observed: datetime,
        fundamental: QualifiedFundamentalModel,
        job_run_id: str | None,
    ) -> int:
        home_xg, away_xg = fundamental.model.expected_goals(target.home_team_id, target.away_team_id)
        matrix = fundamental.model.score_matrix(target.home_team_id, target.away_team_id)
        prices = CoreMarketPrices.from_distribution(ScoreDistribution(home_xg, away_xg, matrix, 0.0))
        total_over = prices.total(2.5, "over")
        total_under = prices.total(2.5, "under")
        odds_snapshot_ids = [
            str(row[0])
            for row in self.connection.execute(
                "SELECT CAST(snapshot_id AS VARCHAR) FROM odds_snapshots "
                "WHERE CAST(fixture_id AS VARCHAR)=? AND observed_at<=? ORDER BY observed_at, snapshot_id",
                [target.fixture_id, observed],
            ).fetchall()
        ]
        prediction_id = str(uuid.uuid4())
        encoded_odds = json.dumps(odds_snapshot_ids)
        self.connection.execute(
            "INSERT INTO institutional_predictions "
            "(prediction_id, analysis_run_id, target_fixture_id, analysis_timestamp, target_kickoff, source_cutoff, "
            "intervening_fixture_ids, dependency_state, freshness_state, freshness_reasons, "
            "fundamental_model_version, feature_dataset_id, odds_snapshot_ids) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CURRENT', '[]', ?, ?, ?)",
            [
                prediction_id,
                analysis_run_id,
                target.fixture_id,
                observed,
                target.kickoff,
                observed,
                json.dumps(intervening_fixture_ids),
                dependency_state,
                fundamental.version,
                fundamental.feature_dataset_id,
                encoded_odds,
            ],
        )
        rows = [
            ("MATCH_ODDS", "HOME", "", None, SettlementDistribution(full_win=prices.home, full_loss=1 - prices.home)),
            ("MATCH_ODDS", "DRAW", "", None, SettlementDistribution(full_win=prices.draw, full_loss=1 - prices.draw)),
            ("MATCH_ODDS", "AWAY", "", None, SettlementDistribution(full_win=prices.away, full_loss=1 - prices.away)),
            ("BTTS", "YES", "", None, SettlementDistribution(full_win=prices.btts_yes, full_loss=prices.btts_no)),
            ("BTTS", "NO", "", None, SettlementDistribution(full_win=prices.btts_no, full_loss=prices.btts_yes)),
            ("TOTAL_GOALS", "OVER", "2.5", 2.5, total_over),
            ("TOTAL_GOALS", "UNDER", "2.5", 2.5, total_under),
        ]
        for market, selection, line_key, line, settlement in rows:
            probability = settlement.win_exposure
            self.connection.execute(
                "INSERT INTO engine_probability_prices "
                "(prediction_id, engine, independence, canonical_market, selection, line_key, line, probability, "
                "full_win_probability, half_win_probability, push_probability, half_loss_probability, "
                "full_loss_probability, fair_decimal_odds, expected_home_goals, expected_away_goals, uncertainty, "
                "model_version, source_odds_snapshot_ids) VALUES "
                "(?, 'FUNDAMENTAL', 'MARKET_INDEPENDENT', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
                [
                    prediction_id,
                    market,
                    selection,
                    line_key,
                    line,
                    probability,
                    settlement.full_win,
                    settlement.half_win,
                    settlement.push,
                    settlement.half_loss,
                    settlement.full_loss,
                    settlement.fair_odds(),
                    home_xg,
                    away_xg,
                    fundamental.version,
                    encoded_odds,
                ],
            )
            self._persist_reference_opportunity(
                prediction_id,
                target,
                market,
                selection,
                line_key,
                settlement,
                observed,
                job_run_id,
            )
        return len(rows)

    def _persist_reference_opportunity(
        self,
        prediction_id: str,
        target: ScheduledFixture,
        canonical_market: str,
        selection: str,
        line_key: str,
        settlement: SettlementDistribution,
        observed: datetime,
        job_run_id: str | None,
    ) -> None:
        quotes = self._reference_quote_cache.get(
            (target.fixture_id, canonical_market, selection, line_key),
            [],
        )
        summary = summarize_references(
            quotes,
            analysis_timestamp=observed,
            kickoff_timestamp=target.kickoff,
            aged_reference_minutes=self.aged_reference_minutes,
        )
        for quote in summary.latest_per_bookmaker:
            state = classify_reference(
                quote,
                analysis_timestamp=observed,
                kickoff_timestamp=target.kickoff,
                aged_reference_minutes=self.aged_reference_minutes,
            )
            history = [item for item in quotes if item.bookmaker_id == quote.bookmaker_id]
            first = min(history, key=lambda item: (item.effective_timestamp, item.collected_at, item.snapshot_id))
            self.connection.execute(
                "INSERT INTO market_reference_quotes VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    str(uuid.uuid4()),
                    prediction_id,
                    quote.snapshot_id,
                    quote.bookmaker_id,
                    quote.market_id,
                    quote.selection_id,
                    canonical_market,
                    selection,
                    line_key,
                    state,
                    quote.provider_updated_at,
                    quote.collected_at,
                    observed,
                    target.kickoff,
                    max(0.0, (observed - quote.effective_timestamp).total_seconds() / 60),
                    quote.decimal_odds,
                    quote.fair_probability,
                    first.decimal_odds,
                    quote.decimal_odds - first.decimal_odds,
                    len(history),
                    quote.bookmaker,
                    quote.source_raw_path,
                ],
            )
        fair_odds = settlement.fair_odds()
        if fair_odds is None:
            return
        uncertainty_adjustment = 0.0
        minimum_odds = settlement.minimum_odds(self.required_robust_ev + uncertainty_adjustment)
        if minimum_odds is None:
            return
        best = summary.best
        reference_edge = (
            settlement.win_exposure - summary.consensus_probability
            if summary.consensus_probability is not None
            else None
        )
        reference_return = settlement.expected_return(best.decimal_odds) if best else None
        robust_edge = (
            reference_return - self.required_robust_ev - uncertainty_adjustment
            if reference_return is not None
            else None
        )
        if best is None:
            decision = "PRICE_TARGET"
            reasons = ["NO_REFERENCE_ODDS"]
        elif (
            reference_edge is not None
            and reference_edge >= self.minimum_probability_advantage
            and robust_edge is not None
            and robust_edge >= 0
        ):
            decision = "BET_IF_PRICE_AVAILABLE"
            reasons = ["MANUAL_PRICE_CONFIRMATION_REQUIRED"]
        elif robust_edge is not None and robust_edge > 0:
            decision = "WATCH"
            reasons = ["REFERENCE_ADVANTAGE_BELOW_THRESHOLD"]
        else:
            decision = "NO_BET"
            reasons = ["REFERENCE_PRICE_BELOW_MINIMUM"]
        self.connection.execute(
            "INSERT INTO institutional_opportunities "
            "(opportunity_id, prediction_id, canonical_market, selection, line_key, probability_source, "
            "model_probability, model_fair_odds, minimum_acceptable_odds, minimum_odds_method, "
            "uncertainty_adjustment, required_robust_ev, reference_state, latest_reference_odds, "
            "best_latest_reference_odds, worst_latest_reference_odds, reference_consensus_probability, "
            "reference_bookmaker, reference_observed_at, reference_age_minutes, reference_snapshot_count, "
            "reference_price_movement, bookmaker_dispersion, reference_edge, robust_estimated_edge, "
            "reference_expected_return, execution_edge, decision, reason_codes, manual_price_confirmation_required) "
            "VALUES (?, ?, ?, ?, ?, 'FUNDAMENTAL', ?, ?, ?, 'settlement-distribution-v1', ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, true)",
            [
                str(uuid.uuid4()),
                prediction_id,
                canonical_market,
                selection,
                line_key,
                settlement.win_exposure,
                fair_odds,
                minimum_odds,
                uncertainty_adjustment,
                self.required_robust_ev,
                summary.state,
                best.decimal_odds if best else None,
                best.decimal_odds if best else None,
                summary.worst.decimal_odds if summary.worst else None,
                summary.consensus_probability,
                best.bookmaker if best else None,
                best.effective_timestamp if best else None,
                max(0.0, (observed - best.effective_timestamp).total_seconds() / 60) if best else None,
                summary.snapshot_count,
                summary.price_movement,
                summary.bookmaker_dispersion,
                reference_edge,
                robust_edge,
                reference_return,
                decision,
                json.dumps(reasons),
            ],
        )

    def _load_reference_quote_cache(self, observed: datetime, job_run_id: str | None) -> None:
        self._reference_quote_cache = {}
        quote_rows = self.connection.execute(
            "WITH priced AS (SELECT o.snapshot_id, o.fixture_id, o.observed_at, o.provider_update_time, "
            "o.source_raw_path, o.job_run_id, p.bookmaker_id, p.market_id, p.selection_id, p.decimal_odds, "
            "p.raw_implied_probability / sum(p.raw_implied_probability) OVER "
            "(PARTITION BY o.snapshot_id, p.bookmaker_id, p.market_id, coalesce(s.line, '')) fair_probability "
            "FROM odds_snapshots o JOIN odds_prices p USING (snapshot_id) JOIN bet_selections s USING (selection_id)) "
            "SELECT CAST(p.fixture_id AS VARCHAR), cm.canonical_market, upper(s.normalized_name), "
            "coalesce(s.line, ''), CAST(p.snapshot_id AS VARCHAR), CAST(b.bookmaker_id AS VARCHAR), b.name, "
            "CAST(m.market_id AS VARCHAR), CAST(s.selection_id AS VARCHAR), p.decimal_odds, "
            "p.fair_probability, p.observed_at, p.provider_update_time, p.source_raw_path, "
            "CAST(p.job_run_id AS VARCHAR) FROM priced p JOIN bookmakers b USING (bookmaker_id) "
            "JOIN bet_markets m USING (market_id) JOIN bet_selections s USING (selection_id) "
            "JOIN canonical_market_mappings cm ON cm.provider='api_football' "
            "AND cm.provider_market_id=m.provider_market_id WHERE p.observed_at<=? AND cm.state='SUPPORTED' "
            "ORDER BY p.observed_at, p.snapshot_id",
            [observed],
        ).fetchall()
        for row in quote_rows:
            key = (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            self._reference_quote_cache.setdefault(key, []).append(
                ReferenceQuote(
                    str(row[4]),
                    str(row[5]),
                    str(row[6]),
                    str(row[7]),
                    str(row[8]),
                    float(row[9]),
                    float(row[10]) if row[10] is not None else None,
                    row[11],
                    row[12],
                    str(row[13]),
                    bool(job_run_id and row[14] == job_run_id),
                )
            )

    @staticmethod
    def _aggregate_odds_health(rows: list[FixtureAuditRow]) -> str:
        statuses = {row.odds_status for row in rows}
        if not statuses or statuses == {ReferenceState.NO_REFERENCE_ODDS}:
            return "NO_REFERENCE_ODDS"
        if ReferenceState.NO_REFERENCE_ODDS in statuses:
            return "PARTIAL_REFERENCE_COVERAGE"
        return "LATEST_API_FOOTBALL_REFERENCES_AVAILABLE"

    def _odds_status(self, fixture_id: str, observed: datetime) -> str:
        row = self.connection.execute(
            "SELECT max(coalesce(provider_update_time, observed_at)) FROM odds_snapshots "
            "WHERE CAST(fixture_id AS VARCHAR)=? AND observed_at<=?",
            [fixture_id, observed],
        ).fetchone()
        if not row or row[0] is None:
            return ReferenceState.NO_REFERENCE_ODDS
        age_minutes = max(0.0, (observed - row[0]).total_seconds() / 60)
        return (
            ReferenceState.AGED_REFERENCE
            if age_minutes > self.aged_reference_minutes
            else ReferenceState.LATEST_PROVIDER_REFERENCE
        )

    def _report_price_targets(self, analysis_run_id: str) -> tuple[OpportunityRow, ...]:
        rows = self.connection.execute(
            "SELECT c.name, f.kickoff_utc, h.name || ' v ' || a.name, o.canonical_market, o.selection, "
            "o.line_key, o.model_probability, o.model_fair_odds, o.minimum_acceptable_odds, "
            "o.latest_reference_odds, o.reference_bookmaker, o.reference_observed_at, "
            "o.reference_age_minutes, o.reference_consensus_probability, o.reference_edge, "
            "o.robust_estimated_edge, o.reference_expected_return, o.uncertainty_adjustment, "
            "o.reference_state, o.decision, o.reference_snapshot_count, o.reference_price_movement, "
            "o.bookmaker_dispersion, o.execution_edge FROM institutional_opportunities o "
            "JOIN institutional_predictions i USING (prediction_id) JOIN fixtures_current f "
            "ON f.fixture_id=i.target_fixture_id JOIN competition_seasons cs USING (competition_season_id) "
            "JOIN competitions c USING (competition_id) JOIN teams h ON h.team_id=f.home_team_id "
            "JOIN teams a ON a.team_id=f.away_team_id WHERE CAST(i.analysis_run_id AS VARCHAR)=? "
            "ORDER BY o.robust_estimated_edge DESC NULLS LAST, f.kickoff_utc, o.canonical_market, o.selection",
            [analysis_run_id],
        ).fetchall()
        return tuple(
            OpportunityRow(
                rank=index,
                competition=str(row[0]),
                kickoff=row[1],
                fixture=str(row[2]),
                market=f"{row[3]} {row[5]}".strip(),
                selection=str(row[4]),
                model_probability=float(row[6]),
                model_fair_odds=float(row[7]),
                minimum_odds=float(row[8]),
                reference_odds=float(row[9]) if row[9] is not None else None,
                bookmaker=str(row[10]) if row[10] else None,
                reference_observed_at=row[11],
                reference_age_minutes=float(row[12]) if row[12] is not None else None,
                market_probability=float(row[13]) if row[13] is not None else None,
                reference_edge=float(row[14]) if row[14] is not None else None,
                robust_edge=float(row[15]) if row[15] is not None else None,
                reference_expected_return=float(row[16]) if row[16] is not None else None,
                uncertainty=float(row[17]),
                reference_state=str(row[18]),
                decision=str(row[19]),
                snapshot_count=int(row[20]),
                price_movement=float(row[21]) if row[21] is not None else None,
                bookmaker_dispersion=float(row[22]) if row[22] is not None else None,
                execution_edge=float(row[23]) if row[23] is not None else None,
            )
            for index, row in enumerate(rows, start=1)
        )

    def _reference_metrics(self, analysis_run_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "WITH refs AS (SELECT i.target_fixture_id, "
            "bool_or(o.latest_reference_odds IS NOT NULL) has_reference "
            "FROM institutional_predictions i JOIN institutional_opportunities o USING (prediction_id) "
            "WHERE CAST(i.analysis_run_id AS VARCHAR)=? GROUP BY i.target_fixture_id), ages AS ("
            "SELECT o.reference_age_minutes FROM institutional_predictions i "
            "JOIN institutional_opportunities o USING (prediction_id) "
            "WHERE CAST(i.analysis_run_id AS VARCHAR)=? AND o.reference_age_minutes IS NOT NULL) "
            "SELECT count(*) FILTER (WHERE has_reference), count(*) FILTER (WHERE NOT has_reference), "
            "(SELECT median(reference_age_minutes) FROM ages), (SELECT min(reference_age_minutes) FROM ages), "
            "(SELECT max(reference_age_minutes) FROM ages) FROM refs",
            [analysis_run_id, analysis_run_id],
        ).fetchone()
        if row is None:
            return {
                "reference_fixtures": 0,
                "no_reference_fixtures": 0,
                "median_age": None,
                "newest_age": None,
                "oldest_age": None,
            }
        return {
            "reference_fixtures": int(row[0] or 0),
            "no_reference_fixtures": int(row[1] or 0),
            "median_age": float(row[2]) if row[2] is not None else None,
            "newest_age": float(row[3]) if row[3] is not None else None,
            "oldest_age": float(row[4]) if row[4] is not None else None,
        }

    def _report_context(self, ledger_mode: str) -> dict[str, Any]:
        quota = self.connection.execute(
            "SELECT daily_remaining, requests_limit_daily FROM provider_capabilities ORDER BY observed_at DESC LIMIT 1"
        ).fetchone()
        counts = self.connection.execute(
            "SELECT count(*) FILTER (WHERE ledger_mode=? AND admitted), "
            "count(*) FILTER (WHERE ledger_mode=? AND NOT admitted) FROM competition_seasons",
            [ledger_mode, ledger_mode],
        ).fetchone()
        observation = self.connection.execute(
            "SELECT count(*) FROM competition_discoveries WHERE universe_state='OBSERVATION'"
        ).fetchone()
        eligible = self.connection.execute(
            "SELECT count(*) FROM fixture_quality_status WHERE eligibility='ML_ELIGIBLE'"
        ).fetchone()
        data_update = self.connection.execute("SELECT max(retrieved_at) FROM fixtures_current").fetchone()
        odds_update = self.connection.execute("SELECT max(observed_at) FROM odds_snapshots").fetchone()
        eligible_count = int(eligible[0]) if eligible else 0
        model_rows: list[ModelHealthRow] = []
        for model_type in MODEL_TYPES:
            row = self.connection.execute(
                "SELECT version, coalesce(evidence_state, 'UNASSESSED'), parent_model_version, training_cutoff, "
                "observations_included, metrics, calibration_method, created_at FROM model_runs "
                "WHERE model_type=? ORDER BY created_at DESC LIMIT 1",
                [model_type],
            ).fetchone()
            if row:
                metrics = row[5] if isinstance(row[5], dict) else json.loads(row[5])
                model_rows.append(
                    ModelHealthRow(
                        model_type,
                        str(row[0]),
                        str(row[1]),
                        str(row[2]) if row[2] else None,
                        row[3],
                        int(metrics.get("train_rows", row[4] or 0)),
                        int(metrics.get("validation_rows", 0)),
                        int(metrics.get("test_rows", 0)),
                        max(0, eligible_count - int(row[4] or 0)),
                        float(metrics["log_loss"]) if metrics.get("log_loss") is not None else None,
                        float(metrics["brier"]) if metrics.get("brier") is not None else None,
                        float(metrics["rps"]) if metrics.get("rps") is not None else None,
                        float(metrics["ece"]) if metrics.get("ece") is not None else None,
                        "CALIBRATED" if row[6] else "NOT_CALIBRATED",
                        "NO_SIGNAL",
                        "NEW_OBSERVATION_POLICY",
                    )
                )
        return {
            "provider_quota": f"{quota[0]}/{quota[1]}" if quota and quota[0] is not None else "UNKNOWN",
            "admitted_leagues": int(counts[0]) if counts else 0,
            "observation_leagues": int(observation[0]) if observation else 0,
            "eligible_fixtures": eligible_count,
            "last_data_update": data_update[0] if data_update else None,
            "last_odds_update": odds_update[0] if odds_update else None,
            "model_rows": tuple(model_rows),
        }

    @staticmethod
    def _terminal_state(
        status: str,
        kickoff: datetime,
        observed_at: datetime,
        dependency_state: str,
        *,
        has_institutional_price: bool,
    ) -> tuple[str, list[str]]:
        if status in {"PST", "CANC", "ABD", "AWD", "WO"}:
            return "POSTPONED", [status]
        if status not in {"NS", "TBD"} or kickoff <= observed_at:
            return "STARTED", [f"fixture_status={status}"]
        if dependency_state == "BLOCKED_BY_INTERVENING_FIXTURE":
            return "BLOCKED_BY_INTERVENING_FIXTURE", [dependency_state]
        if not has_institutional_price:
            return "NO_QUALIFIED_MODEL", ["NO_QUALIFIED_INSTITUTIONAL_PRICE"]
        return "ANALYZED", []
