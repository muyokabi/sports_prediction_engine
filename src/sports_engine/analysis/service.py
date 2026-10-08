import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from sports_engine.analysis.dependencies import ScheduledFixture, assess_intervening_fixtures
from sports_engine.markets.pricing import CoreMarketPrices
from sports_engine.markets.score_distribution import ScoreDistribution
from sports_engine.models.registry import MODEL_TYPES
from sports_engine.models.statistical.dixon_coles import DixonColesModel
from sports_engine.models.statistical.poisson import PoissonModel
from sports_engine.reporting.html import DailyAnalysisReport, FixtureAuditRow, ModelHealthRow, render_daily_analysis


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
        maximum_odds_age_minutes: int = 180,
    ) -> None:
        self.connection = connection
        self.report_root = report_root
        self.maximum_odds_age = timedelta(minutes=maximum_odds_age_minutes)

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
            ("MATCH_ODDS", "HOME", "", None, prices.home),
            ("MATCH_ODDS", "DRAW", "", None, prices.draw),
            ("MATCH_ODDS", "AWAY", "", None, prices.away),
            ("BTTS", "YES", "", None, prices.btts_yes),
            ("BTTS", "NO", "", None, prices.btts_no),
            ("TOTAL_GOALS", "OVER", "2.5", 2.5, total_over.full_win),
            ("TOTAL_GOALS", "UNDER", "2.5", 2.5, total_under.full_win),
        ]
        for market, selection, line_key, line, probability in rows:
            self.connection.execute(
                "INSERT INTO engine_probability_prices "
                "(prediction_id, engine, independence, canonical_market, selection, line_key, line, probability, "
                "full_win_probability, half_win_probability, push_probability, half_loss_probability, "
                "full_loss_probability, fair_decimal_odds, expected_home_goals, expected_away_goals, uncertainty, "
                "model_version, source_odds_snapshot_ids) VALUES "
                "(?, 'FUNDAMENTAL', 'MARKET_INDEPENDENT', ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, NULL, ?, ?)",
                [
                    prediction_id,
                    market,
                    selection,
                    line_key,
                    line,
                    probability,
                    probability,
                    1.0 - probability,
                    1.0 / probability if probability > 0 else None,
                    home_xg,
                    away_xg,
                    fundamental.version,
                    encoded_odds,
                ],
            )
        return len(rows)

    @staticmethod
    def _aggregate_odds_health(rows: list[FixtureAuditRow]) -> str:
        statuses = {row.odds_status for row in rows}
        if not statuses or statuses == {"NO_ODDS"}:
            return "NO_ODDS"
        if "STALE" in statuses:
            return "STALE"
        if "NO_ODDS" in statuses:
            return "INCOMPLETE"
        return "FRESH"

    def _odds_status(self, fixture_id: str, observed: datetime) -> str:
        row = self.connection.execute(
            "SELECT max(observed_at) FROM odds_snapshots WHERE CAST(fixture_id AS VARCHAR)=? AND observed_at<=?",
            [fixture_id, observed],
        ).fetchone()
        if not row or row[0] is None:
            return "NO_ODDS"
        return "FRESH" if observed - row[0] <= self.maximum_odds_age else "STALE"

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
