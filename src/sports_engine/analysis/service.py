import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from sports_engine.analysis.dependencies import ScheduledFixture, assess_intervening_fixtures
from sports_engine.core.config import ShadowCandidateConfig
from sports_engine.markets.pricing import CoreMarketPrices
from sports_engine.markets.reference import ReferenceQuote, ReferenceState, classify_reference, summarize_references
from sports_engine.markets.score_distribution import ScoreDistribution
from sports_engine.markets.settlement import SettlementDistribution
from sports_engine.models.applicability import ApplicabilityAssessment, assess_score_model_applicability
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
    registry_status: str
    model: PoissonModel
    feature_dataset_id: str | None
    training_cutoff: datetime | None
    metrics: dict[str, Any]
    half_life_days: float


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
        maximum_production_candidates_per_run: int = 5,
        shadow_policy: ShadowCandidateConfig | None = None,
    ) -> None:
        self.connection = connection
        self.report_root = report_root
        self.aged_reference_minutes = aged_reference_minutes
        self.minimum_probability_advantage = minimum_probability_advantage
        self.required_robust_ev = required_robust_ev
        self.maximum_production_candidates_per_run = maximum_production_candidates_per_run
        self.shadow_policy = shadow_policy or ShadowCandidateConfig()
        self._reference_quote_cache: dict[tuple[str, str, str, str], list[ReferenceQuote]] = {}
        self._calibration_cache: dict[tuple[str, str], bool] = {}
        self._market_role_cache: dict[tuple[str, str], bool] = {}
        self._probability_scope_cache: dict[tuple[str, str, str], bool] = {}

    def run(
        self,
        start_date: date,
        end_date: date,
        *,
        timezone: str,
        ledger_mode: str,
        observed_at: datetime | None = None,
        job_run_id: str | None = None,
        report_mode: str = "LIVE",
        source_live_run_id: str | None = None,
    ) -> AnalysisResult:
        if end_date < start_date:
            raise ValueError("Analysis end date cannot precede start date")
        observed = observed_at or datetime.now(UTC)
        self._fail_stale_analysis_runs(observed)
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
            "presentation_timezone, analysis_timestamp, source_cutoff, state, expected_fixture_count, job_run_id, "
            "report_mode, source_live_run_id) VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?, ?, ?)",
            [
                run_id,
                start_date,
                end_date,
                timezone,
                observed,
                observed,
                len(rows),
                job_run_id,
                report_mode,
                source_live_run_id,
            ],
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
                    written, applicability = self._persist_fundamental_prediction(
                        run_id,
                        target,
                        dependency.intervening_fixture_ids,
                        str(dependency.state),
                        observed,
                        fundamental,
                        job_run_id,
                        str(competition),
                    )
                    prices_written += written
                    has_institutional_price = True
                else:
                    applicability = None
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
                        applicability=applicability,
                    )
                )
            terminal_count = len(audit_rows)
            state = "COMPLETE" if terminal_count == len(rows) else "INCOMPLETE"
            self._enforce_production_candidate_caps(run_id)
            self._enforce_shadow_candidate_caps(run_id)
            report_path = self.report_root / f"analysis-{start_date.isoformat()}-{end_date.isoformat()}-{run_id}.html"
            report_context = self._report_context(ledger_mode)
            price_targets = self._report_price_targets(run_id)
            opportunities = tuple(
                row for row in price_targets if row.decision in {"PRODUCTION_ACTIONABLE", "SHADOW_ACTIONABLE"}
            )[:10]
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
                    model_health=(
                        "CHAMPION_QUALIFIED"
                        if fundamental and fundamental.registry_status == "champion"
                        else "SHADOW_CHALLENGER"
                        if fundamental
                        else "NO_QUALIFIED_MODEL"
                    ),
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
                    qualified_opportunities=sum(row.decision == "PRODUCTION_ACTIONABLE" for row in price_targets),
                    reference_fixtures=int(reference_metrics["reference_fixtures"] or 0),
                    no_reference_fixtures=int(reference_metrics["no_reference_fixtures"] or 0),
                    median_reference_age_minutes=reference_metrics["median_age"],
                    newest_reference_age_minutes=reference_metrics["newest_age"],
                    oldest_reference_age_minutes=reference_metrics["oldest_age"],
                    snapshots_collected_this_run=snapshots_this_run,
                    report_mode=report_mode,
                    source_live_run_id=source_live_run_id,
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

    def _fail_stale_analysis_runs(self, observed: datetime) -> None:
        """Close orphaned runs left RUNNING after a killed process."""
        cutoff = observed - timedelta(minutes=self.shadow_policy.stale_run_minutes)
        self.connection.execute(
            "UPDATE analysis_runs SET state='FAILED' WHERE state='RUNNING' AND analysis_timestamp<?",
            [cutoff],
        )

    def _load_qualified_fundamental_model(self) -> QualifiedFundamentalModel | None:
        row = self.connection.execute(
            "SELECT m.model_type, m.version, m.status, m.artifact_path, m.training_dataset_hash, "
            "m.training_cutoff, m.metrics, m.hyperparameters FROM model_market_roles r "
            "JOIN model_runs m ON m.version=r.model_version "
            "WHERE r.market_family='MATCH_ODDS' AND r.role_name='MATCH_ODDS_CHAMPION' "
            "AND r.state='CHAMPION' AND m.evidence_state='PRODUCTION_ACTIONABLE' "
            "AND m.model_type IN ('poisson','dixon-coles') ORDER BY r.selected_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            # Preserve research output before the first audited role is granted,
            # but never mistake the newest challenger for the execution model.
            row = self.connection.execute(
                "SELECT model_type, version, status, artifact_path, training_dataset_hash, training_cutoff, metrics, "
                "hyperparameters FROM model_runs "
                "WHERE status IN ('champion','candidate') AND evidence_state='PRODUCTION_ACTIONABLE' "
                "AND model_type IN ('poisson','dixon-coles') "
                "ORDER BY training_cutoff DESC NULLS LAST, (status='champion') DESC, created_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        (
            model_type,
            version,
            registry_status,
            artifact_path,
            dataset_hash,
            training_cutoff,
            metrics_value,
            hyperparameters_value,
        ) = row
        model_class = DixonColesModel if model_type == "dixon-coles" else PoissonModel
        model = model_class.load(Path(str(artifact_path)))
        dataset = self.connection.execute(
            "SELECT CAST(dataset_id AS VARCHAR) FROM feature_datasets "
            "WHERE dataset_hash=? ORDER BY created_at DESC LIMIT 1",
            [dataset_hash],
        ).fetchone()
        metrics = metrics_value if isinstance(metrics_value, dict) else json.loads(metrics_value)
        hyperparameters = (
            hyperparameters_value if isinstance(hyperparameters_value, dict) else json.loads(hyperparameters_value)
        )
        return QualifiedFundamentalModel(
            str(model_type),
            str(version),
            str(registry_status),
            model,
            str(dataset[0]) if dataset else None,
            training_cutoff,
            metrics,
            float(hyperparameters.get("time_decay_half_life_days", 365.0)),
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
        competition: str,
    ) -> tuple[int, ApplicabilityAssessment]:
        home_xg, away_xg = fundamental.model.expected_goals(target.home_team_id, target.away_team_id)
        matrix = fundamental.model.score_matrix(target.home_team_id, target.away_team_id)
        prices = CoreMarketPrices.from_distribution(ScoreDistribution(home_xg, away_xg, matrix, 0.0))
        probabilities = {
            "home": prices.home,
            "draw": prices.draw,
            "away": prices.away,
            "btts_yes": prices.btts_yes,
            "btts_no": prices.btts_no,
            "over_2_5": prices.total(2.5, "over").win_exposure,
            "under_2_5": prices.total(2.5, "under").win_exposure,
        }
        applicability = assess_score_model_applicability(
            self.connection,
            fixture_id=target.fixture_id,
            home_team_id=target.home_team_id,
            away_team_id=target.away_team_id,
            model=fundamental.model,
            model_type=fundamental.model_type,
            model_metrics=fundamental.metrics,
            training_cutoff=fundamental.training_cutoff,
            half_life_days=fundamental.half_life_days,
            probabilities=probabilities,
        )
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
        self._persist_applicability(prediction_id, fundamental, applicability, observed)
        rows = [
            ("MATCH_ODDS", "HOME", "", None, SettlementDistribution(full_win=prices.home, full_loss=1 - prices.home)),
            ("MATCH_ODDS", "DRAW", "", None, SettlementDistribution(full_win=prices.draw, full_loss=1 - prices.draw)),
            ("MATCH_ODDS", "AWAY", "", None, SettlementDistribution(full_win=prices.away, full_loss=1 - prices.away)),
            ("BTTS", "YES", "", None, SettlementDistribution(full_win=prices.btts_yes, full_loss=prices.btts_no)),
            ("BTTS", "NO", "", None, SettlementDistribution(full_win=prices.btts_no, full_loss=prices.btts_yes)),
            ("TOTAL_GOALS", "OVER", "2.5", 2.5, total_over),
            ("TOTAL_GOALS", "UNDER", "2.5", 2.5, total_under),
        ]
        rows.extend(self._observed_supported_market_rows(target.fixture_id, prices, rows))
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
                fundamental,
                applicability,
                competition,
            )
        return len(rows), applicability

    def _observed_supported_market_rows(
        self,
        fixture_id: str,
        prices: CoreMarketPrices,
        existing: list[tuple[str, str, str, float | None, SettlementDistribution]],
    ) -> list[tuple[str, str, str, float | None, SettlementDistribution]]:
        """Price only provider-observed lines whose settlement is explicit."""
        existing_keys = {(market, selection, line_key) for market, selection, line_key, _, _ in existing}
        observed_keys = sorted({key[1:] for key in self._reference_quote_cache if key[0] == fixture_id})
        rows: list[tuple[str, str, str, float | None, SettlementDistribution]] = []
        double_chance = {
            "HOME/DRAW": prices.home + prices.draw,
            "HOME/AWAY": prices.home + prices.away,
            "DRAW/AWAY": prices.draw + prices.away,
        }
        for market, selection, line_key in observed_keys:
            if market not in self.shadow_policy.allowed_markets:
                continue
            if (market, selection, line_key) in existing_keys:
                continue
            settlement: SettlementDistribution | None = None
            line: float | None = None
            try:
                if market == "ASIAN_HANDICAP" and selection in {"HOME", "AWAY"}:
                    line = float(line_key)
                    # The provider's line is expressed from the home-team
                    # perspective even on the away selection.
                    selected_line = line if selection == "HOME" else -line
                    settlement = prices.asian_handicap(selected_line, selection.casefold())
                elif market == "TOTAL_GOALS" and selection in {"OVER", "UNDER"}:
                    line = float(line_key)
                    settlement = prices.total(line, selection.casefold())
                elif market in {"HOME_TEAM_TOTAL", "AWAY_TEAM_TOTAL"} and selection in {"OVER", "UNDER"}:
                    line = float(line_key)
                    team = "home" if market == "HOME_TEAM_TOTAL" else "away"
                    settlement = prices.team_total(line, team=team, side=selection.casefold())
                elif market == "DOUBLE_CHANCE" and selection in double_chance:
                    probability = double_chance[selection]
                    settlement = SettlementDistribution(full_win=probability, full_loss=1 - probability)
                elif market == "CORRECT_SCORE" and ":" in selection:
                    home_goals, away_goals = (int(value) for value in selection.split(":", 1))
                    probability = prices.correct_score(home_goals, away_goals)
                    settlement = SettlementDistribution(full_win=probability, full_loss=1 - probability)
            except ValueError:
                settlement = None
            if settlement is not None and settlement.fair_odds() is not None:
                rows.append((market, selection, line_key, line, settlement))
        return rows

    def _persist_applicability(
        self,
        prediction_id: str,
        fundamental: QualifiedFundamentalModel,
        assessment: ApplicabilityAssessment,
        observed: datetime,
    ) -> None:
        self.connection.execute(
            "INSERT INTO prediction_applicability VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ",
            [
                prediction_id,
                fundamental.version,
                fundamental.model_type,
                assessment.state,
                assessment.level,
                assessment.actionability_qualified,
                json.dumps(assessment.reasons),
                assessment.home.observations,
                assessment.away.observations,
                assessment.home.effective_observations,
                assessment.away.effective_observations,
                assessment.home.home_observations,
                assessment.home.away_observations,
                assessment.away.home_observations,
                assessment.away.away_observations,
                assessment.competition_observations,
                assessment.home.last_observation,
                assessment.away.last_observation,
                assessment.home.in_training_universe,
                assessment.away.in_training_universe,
                assessment.competition_in_training_universe,
                assessment.home.prior_fraction,
                assessment.away.prior_fraction,
                assessment.home_attack,
                assessment.home_defence,
                assessment.away_attack,
                assessment.away_defence,
                assessment.competition_baseline,
                assessment.home_advantage,
                json.dumps(assessment.parameter_states),
                assessment.expected_home_goals,
                assessment.expected_away_goals,
                json.dumps(assessment.probabilities),
                fundamental.training_cutoff,
                assessment.policy_version,
                observed,
            ],
        )

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
        fundamental: QualifiedFundamentalModel,
        applicability: ApplicabilityAssessment,
        competition: str,
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
        uncertainty_components = {
            "prior_dependence": (applicability.home.prior_fraction + applicability.away.prior_fraction) / 2,
            "applicability_failure": 0.0 if applicability.actionability_qualified else 1.0,
            "calibration_unvalidated": 0.0,
            "market_role_unqualified": 0.0,
            "competition_probability_unvalidated": 0.0,
        }
        gate_key = (fundamental.version, canonical_market)
        if gate_key not in self._calibration_cache:
            calibration = self.connection.execute(
                "SELECT state FROM calibration_validations WHERE model_version=? AND market_family=? "
                "ORDER BY validated_at DESC LIMIT 1",
                list(gate_key),
            ).fetchone()
            self._calibration_cache[gate_key] = bool(calibration and calibration[0] == "CALIBRATION_VALIDATED")
        if gate_key not in self._market_role_cache:
            role = self.connection.execute(
                "SELECT state FROM model_market_roles WHERE model_version=? AND market_family=? "
                "AND role_name=? ORDER BY selected_at DESC LIMIT 1",
                [*gate_key, f"{canonical_market}_CHAMPION"],
            ).fetchone()
            self._market_role_cache[gate_key] = bool(role and role[0] == "CHAMPION")
        calibration_validated = self._calibration_cache[gate_key]
        role_qualified = self._market_role_cache[gate_key]
        scope_key = (fundamental.version, canonical_market, competition)
        if scope_key not in self._probability_scope_cache:
            scope = self.connection.execute(
                "SELECT state FROM model_probability_scope_validations WHERE model_version=? "
                "AND market_family=? AND scope_type='COMPETITION' AND scope_key=? "
                "ORDER BY validated_at DESC LIMIT 1",
                list(scope_key),
            ).fetchone()
            self._probability_scope_cache[scope_key] = bool(scope and scope[0] == "VALIDATED")
        competition_probability_validated = self._probability_scope_cache[scope_key]
        uncertainty_components["calibration_unvalidated"] = 0.0 if calibration_validated else 1.0
        uncertainty_components["market_role_unqualified"] = 0.0 if role_qualified else 1.0
        uncertainty_components["competition_probability_unvalidated"] = (
            0.0 if competition_probability_validated else 1.0
        )
        uncertainty_score = sum(uncertainty_components.values()) / len(uncertainty_components)
        threshold_policy = fundamental.metrics.get("minimum_odds_policy")
        uncertainty_policy = fundamental.metrics.get("uncertainty_policy")
        threshold_payload = threshold_policy if isinstance(threshold_policy, dict) else {}
        uncertainty_payload = uncertainty_policy if isinstance(uncertainty_policy, dict) else {}
        threshold_validated = threshold_payload.get("validated") is True
        uncertainty_validated = uncertainty_payload.get("validated") is True
        required_margin = float(threshold_payload.get("required_expected_return", 0.0)) if threshold_validated else 0.0
        uncertainty_adjustment = (
            float(uncertainty_payload.get("expected_return_adjustment", 0.0)) if uncertainty_validated else 0.0
        )
        shadow_margin = self.shadow_policy.required_expected_return + self.shadow_policy.uncertainty_buffer
        applied_margin = (
            required_margin + uncertainty_adjustment if threshold_validated and uncertainty_validated else shadow_margin
        )
        minimum_odds = settlement.minimum_odds(applied_margin)
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
            reference_return - required_margin - uncertainty_adjustment
            if reference_return is not None and threshold_validated and uncertainty_validated
            else None
        )
        governance_reasons = list(applicability.reasons)
        if not calibration_validated:
            governance_reasons.append("CALIBRATION_NOT_VALIDATED")
        if not role_qualified:
            governance_reasons.append("NO_MARKET_FAMILY_CHAMPION")
        if not competition_probability_validated:
            governance_reasons.append("COMPETITION_PROBABILITY_NOT_VALIDATED")
        if not threshold_validated:
            governance_reasons.append("NO_EVIDENCE_QUALIFIED_MARGIN_THRESHOLD")
        if not uncertainty_validated:
            governance_reasons.append("UNCERTAINTY_NOT_VALIDATED")
        if reference_edge is not None and abs(reference_edge) > self.shadow_policy.maximum_absolute_probability_gap:
            governance_reasons.append("EXTREME_MODEL_MARKET_DISAGREEMENT")
        if len(summary.latest_per_bookmaker) < self.shadow_policy.minimum_reference_bookmakers:
            governance_reasons.append("INSUFFICIENT_REFERENCE_BOOKMAKER_BREADTH")
        if summary.state == ReferenceState.AGED_REFERENCE:
            governance_reasons.append("AGED_REFERENCE_RECHECK_REQUIRED")
        shadow_qualified = self._shadow_qualified(
            applicability,
            canonical_market,
            summary.state,
            reference_edge,
            reference_return,
            len(summary.latest_per_bookmaker),
        )
        if best is None:
            decision, governance_state = "PRICE_TARGET", "RESEARCH_ONLY"
            reasons = ["NO_REFERENCE_ODDS", *governance_reasons]
        elif reference_edge is not None and reference_edge >= self.minimum_probability_advantage:
            fully_qualified = (
                applicability.actionability_qualified
                and calibration_validated
                and role_qualified
                and competition_probability_validated
                and threshold_validated
                and uncertainty_validated
                and robust_edge is not None
                and robust_edge >= 0
                and abs(reference_edge) <= self.shadow_policy.maximum_absolute_probability_gap
                and len(summary.latest_per_bookmaker) >= self.shadow_policy.minimum_reference_bookmakers
            )
            if fully_qualified:
                decision = "BET_IF_PRICE_AVAILABLE"
                governance_state = "PRODUCTION_ACTIONABLE"
                reasons = ["LIVE_PRICE_CONFIRMATION_REQUIRED"]
            elif shadow_qualified:
                decision = "WATCH"
                governance_state = "SHADOW_ACTIONABLE"
                reasons = ["MANUAL_PRICE_CONFIRMATION_REQUIRED", *governance_reasons]
                reasons.insert(1, "SHADOW_ONLY_NOT_PRODUCTION_APPROVED")
            else:
                decision = "NO_BET"
                governance_state = "RESEARCH_VALUE_SIGNAL"
                reasons = ["MANUAL_PRICE_CONFIRMATION_REQUIRED", *governance_reasons]
        elif reference_return is not None and reference_return > 0:
            decision, governance_state = "NO_BET", "RESEARCH_VALUE_SIGNAL"
            reasons = ["REFERENCE_ADVANTAGE_BELOW_THRESHOLD", *governance_reasons]
        else:
            decision, governance_state = "NO_BET", "RESEARCH_ONLY"
            reasons = ["REFERENCE_PRICE_BELOW_MINIMUM", *governance_reasons]
        opportunity_id = str(uuid.uuid4())
        self.connection.execute(
            "INSERT INTO institutional_opportunities "
            "(opportunity_id, prediction_id, canonical_market, selection, line_key, probability_source, "
            "model_probability, model_fair_odds, minimum_acceptable_odds, minimum_odds_method, "
            "uncertainty_adjustment, required_robust_ev, reference_state, latest_reference_odds, "
            "best_latest_reference_odds, worst_latest_reference_odds, reference_consensus_probability, "
            "reference_bookmaker, reference_observed_at, reference_age_minutes, reference_snapshot_count, "
            "reference_price_movement, bookmaker_dispersion, reference_edge, robust_estimated_edge, "
            "reference_expected_return, execution_edge, decision, reason_codes, manual_price_confirmation_required, "
            "governance_state, uncertainty_score, uncertainty_components, threshold_version, threshold_derivation) "
            "VALUES (?, ?, ?, ?, ?, 'FUNDAMENTAL', ?, ?, ?, 'settlement-distribution-v1', ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, true, ?, ?, ?, ?, ?)",
            [
                opportunity_id,
                prediction_id,
                canonical_market,
                selection,
                line_key,
                settlement.win_exposure,
                fair_odds,
                minimum_odds,
                uncertainty_adjustment,
                required_margin,
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
                governance_state,
                uncertainty_score,
                json.dumps(uncertainty_components),
                (str(threshold_payload.get("version")) if threshold_validated else self.shadow_policy.policy_version),
                json.dumps(
                    threshold_payload
                    if threshold_validated
                    else {
                        "validated": False,
                        "shadow_only": True,
                        "version": self.shadow_policy.policy_version,
                        "required_expected_return": self.shadow_policy.required_expected_return,
                        "uncertainty_buffer": self.shadow_policy.uncertainty_buffer,
                    }
                ),
            ],
        )
        if governance_state == "SHADOW_ACTIONABLE":
            qualification_evidence = {
                "fixture_applicability": applicability.actionability_qualified,
                "calibration_validated": calibration_validated,
                "market_role_qualified": role_qualified,
                "competition_probability_validated": competition_probability_validated,
                "threshold_validated": threshold_validated,
                "uncertainty_validated": uncertainty_validated,
                "reference_state": summary.state,
                "reason_codes": reasons,
                "threshold": threshold_payload,
                "uncertainty": uncertainty_components,
                "production_qualified": fully_qualified,
                "model_registry_status": fundamental.registry_status,
                "shadow_policy": self.shadow_policy.model_dump(mode="json"),
            }
            self.connection.execute(
                "INSERT INTO shadow_opportunities "
                "(shadow_id, opportunity_id, state, qualification_evidence, created_at) "
                "VALUES (?, ?, 'SHADOW_ACTIONABLE', ?, ?)",
                [str(uuid.uuid4()), opportunity_id, json.dumps(qualification_evidence), observed],
            )

    def _shadow_qualified(
        self,
        applicability: ApplicabilityAssessment,
        canonical_market: str,
        reference_state: ReferenceState,
        reference_edge: float | None,
        reference_return: float | None,
        reference_bookmakers: int,
    ) -> bool:
        """Admit an auditable paper candidate without claiming production validity."""
        policy = self.shadow_policy
        usable_reference = reference_state in {
            ReferenceState.CURRENT_REFERENCE,
            ReferenceState.LATEST_PROVIDER_REFERENCE,
            # Age is disclosed for manual price confirmation; API-Football is
            # a reference observation, not an executable quote. An arbitrary
            # clock threshold must not erase otherwise valid research evidence.
            ReferenceState.AGED_REFERENCE,
        }
        structurally_in_domain = (
            applicability.state in {"FULLY_ESTIMATED", "PARTIALLY_POOLED"}
            and applicability.home.in_training_universe
            and applicability.away.in_training_universe
            and applicability.competition_in_training_universe
            and applicability.competition_state == "ACTIONABLE"
            and min(applicability.home.effective_observations, applicability.away.effective_observations)
            >= policy.minimum_effective_team_matches
            and max(applicability.home.prior_fraction, applicability.away.prior_fraction)
            <= policy.maximum_prior_fraction
        )
        return bool(
            policy.enabled
            and canonical_market in policy.allowed_markets
            and usable_reference
            and structurally_in_domain
            and reference_edge is not None
            and reference_edge >= policy.minimum_probability_advantage
            and reference_edge <= policy.maximum_absolute_probability_gap
            and reference_return is not None
            and reference_return >= policy.minimum_reference_expected_return
            and reference_bookmakers >= policy.minimum_reference_bookmakers
        )

    def _enforce_shadow_candidate_caps(self, analysis_run_id: str) -> None:
        rows = self.connection.execute(
            "SELECT CAST(o.opportunity_id AS VARCHAR), CAST(i.target_fixture_id AS VARCHAR), "
            "o.reference_expected_return, o.reference_observed_at FROM institutional_opportunities o "
            "JOIN institutional_predictions i USING (prediction_id) "
            "WHERE CAST(i.analysis_run_id AS VARCHAR)=? AND o.governance_state='SHADOW_ACTIONABLE' "
            "ORDER BY o.reference_observed_at DESC NULLS LAST, "
            "o.reference_expected_return DESC NULLS LAST, o.opportunity_id",
            [analysis_run_id],
        ).fetchall()
        retained: set[str] = set()
        fixture_counts: dict[str, int] = {}
        for opportunity_id, fixture_id, _, _ in rows:
            if len(retained) >= self.shadow_policy.maximum_candidates_per_run:
                continue
            used = fixture_counts.get(str(fixture_id), 0)
            if used >= self.shadow_policy.maximum_candidates_per_fixture:
                continue
            retained.add(str(opportunity_id))
            fixture_counts[str(fixture_id)] = used + 1
        for opportunity_id, _, _, _ in rows:
            if str(opportunity_id) in retained:
                continue
            reason_row = self.connection.execute(
                "SELECT reason_codes FROM institutional_opportunities WHERE opportunity_id=?",
                [opportunity_id],
            ).fetchone()
            raw_reasons = reason_row[0] if reason_row else []
            reasons = json.loads(raw_reasons) if isinstance(raw_reasons, str) else list(raw_reasons)
            reasons.append("SHADOW_PORTFOLIO_CAP")
            self.connection.execute(
                "UPDATE institutional_opportunities SET governance_state='RESEARCH_VALUE_SIGNAL', "
                "decision='NO_BET', reason_codes=? WHERE opportunity_id=?",
                [json.dumps(list(dict.fromkeys(reasons))), opportunity_id],
            )
            self.connection.execute(
                "UPDATE shadow_opportunities SET state='SHADOW_REJECTED' WHERE opportunity_id=?",
                [opportunity_id],
            )

    def _enforce_production_candidate_caps(self, analysis_run_id: str) -> None:
        """Prevent correlated duplicate bets and bound daily execution exposure."""
        rows = self.connection.execute(
            "SELECT CAST(o.opportunity_id AS VARCHAR), CAST(i.target_fixture_id AS VARCHAR) "
            "FROM institutional_opportunities o JOIN institutional_predictions i USING (prediction_id) "
            "WHERE CAST(i.analysis_run_id AS VARCHAR)=? AND o.governance_state='PRODUCTION_ACTIONABLE' "
            "ORDER BY o.reference_observed_at DESC NULLS LAST, o.robust_estimated_edge DESC NULLS LAST, "
            "o.opportunity_id",
            [analysis_run_id],
        ).fetchall()
        retained: set[str] = set()
        retained_fixtures: set[str] = set()
        for opportunity_id, fixture_id in rows:
            if len(retained) >= self.maximum_production_candidates_per_run:
                continue
            if str(fixture_id) in retained_fixtures:
                continue
            retained.add(str(opportunity_id))
            retained_fixtures.add(str(fixture_id))
        for opportunity_id, _ in rows:
            if str(opportunity_id) in retained:
                continue
            reason_row = self.connection.execute(
                "SELECT reason_codes FROM institutional_opportunities WHERE opportunity_id=?",
                [opportunity_id],
            ).fetchone()
            raw_reasons = reason_row[0] if reason_row else []
            reasons = json.loads(raw_reasons) if isinstance(raw_reasons, str) else list(raw_reasons)
            reasons.append("PRODUCTION_PORTFOLIO_CAP")
            self.connection.execute(
                "UPDATE institutional_opportunities SET governance_state='RESEARCH_VALUE_SIGNAL', "
                "decision='NO_BET', reason_codes=? WHERE opportunity_id=?",
                [json.dumps(list(dict.fromkeys(reasons))), opportunity_id],
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
                    # DuckDB's parallel floating SUM can differ in the final
                    # binary digit between identical reads. Canonicalize the
                    # no-vig reference at persisted precision so unchanged
                    # inputs produce byte-stable downstream decisions.
                    round(float(row[10]), 15) if row[10] is not None else None,
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
            "o.reference_state, CASE WHEN o.decision='PRICE_TARGET' THEN o.decision "
            "ELSE coalesce(o.governance_state, o.decision) END, o.reference_snapshot_count, "
            "o.reference_price_movement, "
            "o.bookmaker_dispersion, o.execution_edge, o.reason_codes FROM institutional_opportunities o "
            "JOIN institutional_predictions i USING (prediction_id) JOIN fixtures_current f "
            "ON f.fixture_id=i.target_fixture_id JOIN competition_seasons cs USING (competition_season_id) "
            "JOIN competitions c USING (competition_id) JOIN teams h ON h.team_id=f.home_team_id "
            "JOIN teams a ON a.team_id=f.away_team_id WHERE CAST(i.analysis_run_id AS VARCHAR)=? "
            "ORDER BY CASE coalesce(o.governance_state, o.decision) "
            "WHEN 'PRODUCTION_ACTIONABLE' THEN 0 WHEN 'SHADOW_ACTIONABLE' THEN 1 ELSE 2 END, "
            "o.reference_observed_at DESC NULLS LAST, o.robust_estimated_edge DESC NULLS LAST, "
            "o.reference_expected_return DESC NULLS LAST, f.kickoff_utc, o.canonical_market, o.selection",
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
                reasons=tuple(json.loads(row[24])) if row[24] else (),
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
