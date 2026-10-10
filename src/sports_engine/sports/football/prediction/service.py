import json
import pickle
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import polars as pl

from sports_engine.core.exceptions import NoEligibleModelError
from sports_engine.markets.decision import (
    BettingDecision,
    EvidencePolicy,
    MarketQuote,
    RiskPolicy,
    decide_wager,
)
from sports_engine.models.ml.catboost import CatBoostProbabilityModel
from sports_engine.models.ml.lightgbm import LightGBMProbabilityModel
from sports_engine.models.ml.logistic import LogisticProbabilityModel
from sports_engine.models.statistical.dixon_coles import DixonColesModel
from sports_engine.models.statistical.elo import EloModel
from sports_engine.models.statistical.poisson import PoissonModel
from sports_engine.sports.football.features.dataset import PointInTimeFeatureBuilder
from sports_engine.training.temporal_split import split_by_time


@dataclass(frozen=True, slots=True)
class PredictionResult:
    prediction_run_id: str
    model_version: str
    fixture_count: int
    frame: pl.DataFrame


@dataclass(frozen=True, slots=True)
class TrainingDomain:
    teams: frozenset[str]
    competitions: frozenset[str]
    lineage_available: bool


class PredictionService:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        windows: list[int],
        exponential_half_life: float,
        prediction_lead_hours: int,
        historical_ledger_modes: list[str] | None = None,
        evidence_policy: EvidencePolicy | None = None,
        risk_policy: RiskPolicy | None = None,
    ) -> None:
        self.connection = connection
        self.builder = PointInTimeFeatureBuilder(
            connection,
            Path("."),
            windows=windows,
            exponential_half_life=exponential_half_life,
            prediction_lead_hours=prediction_lead_hours,
            historical_ledger_modes=historical_ledger_modes,
        )
        self.evidence_policy = evidence_policy or EvidencePolicy(0, 0, 0, 0, 10, True, 0.40)
        self.risk_policy = risk_policy or RiskPolicy(0.01, 0.05, 5, 0.25, 0.01, 0.03, 0.0)

    def predict(
        self,
        target_date: date,
        *,
        ledger_mode: str,
        timezone: str,
        observed_at: datetime | None = None,
    ) -> PredictionResult:
        champion = self.connection.execute(
            "SELECT mr.model_type, mr.version, mr.artifact_path, mr.calibration_method, mr.metrics, "
            "mr.training_dataset_hash "
            "FROM model_runs mr LEFT JOIN model_market_roles r ON r.model_version=mr.version "
            "AND r.market_family='MATCH_ODDS' AND r.role_name='MATCH_ODDS_CHAMPION' AND r.state='CHAMPION' "
            "WHERE r.role_id IS NOT NULL OR mr.status='champion' "
            "ORDER BY CASE WHEN r.role_id IS NOT NULL THEN 0 ELSE 1 END, r.selected_at DESC NULLS LAST, "
            "mr.created_at DESC LIMIT 1"
        ).fetchone()
        if not champion:
            raise NoEligibleModelError("No champion model is registered")
        observed = observed_at or datetime.now(UTC)
        frame = self.builder.build_prediction_frame(
            datetime.combine(target_date, datetime.min.time(), tzinfo=UTC),
            ledger_mode=ledger_mode,
            observed_at=observed,
            timezone=timezone,
        )
        if frame.is_empty():
            raise ValueError(f"No unplayed {ledger_mode} fixtures found for {target_date}")
        model_type, model_version, artifact_value, calibration_method, metrics_value, dataset_hash = champion
        model_metrics = metrics_value if isinstance(metrics_value, dict) else json.loads(metrics_value)
        artifact_path = Path(artifact_value)
        manifest_path = artifact_path.with_suffix(artifact_path.suffix + ".json")
        if not artifact_path.is_file() or not manifest_path.is_file():
            raise ValueError(f"Champion artifact or manifest is missing: {artifact_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        model = self._load_model(model_type, artifact_path)
        training_domain = self._training_domain(str(model_type), model, str(dataset_hash))
        probabilities = self._predict_probabilities(model_type, model, frame, manifest)
        if calibration_method:
            calibration_path = artifact_path.parent / "calibrator.pkl"
            if not calibration_path.is_file():
                raise ValueError(f"Champion calibration artifact is missing: {calibration_path}")
            calibrator = pickle.loads(calibration_path.read_bytes())
            probabilities = calibrator.transform(probabilities)
        calibration_row = self.connection.execute(
            "SELECT state FROM calibration_validations WHERE model_version=? AND market_family='MATCH_ODDS' "
            "ORDER BY validated_at DESC LIMIT 1",
            [model_version],
        ).fetchone()
        role_row = self.connection.execute(
            "SELECT state FROM model_market_roles WHERE model_version=? AND market_family='MATCH_ODDS' "
            "AND role_name='MATCH_ODDS_CHAMPION' ORDER BY selected_at DESC LIMIT 1",
            [model_version],
        ).fetchone()
        calibration_validated = bool(calibration_row and calibration_row[0] == "CALIBRATION_VALIDATED")
        market_role_qualified = bool(role_row and role_row[0] == "CHAMPION")
        uncertainty_policy = model_metrics.get("uncertainty_policy")
        margin_policy = model_metrics.get("minimum_odds_policy")
        uncertainty_validated = isinstance(uncertainty_policy, dict) and uncertainty_policy.get("validated") is True
        margin_validated = isinstance(margin_policy, dict) and margin_policy.get("validated") is True
        prediction_run_id = str(uuid.uuid4())
        odds_time = self.connection.execute(
            "SELECT max(o.observed_at) FROM odds_snapshots o JOIN fixtures_current f USING (fixture_id) "
            "JOIN competition_seasons cs USING (competition_season_id) "
            "WHERE cs.ledger_mode=? AND CAST(timezone(?, f.kickoff_utc) AS DATE)=? "
            "AND o.observed_at<=?",
            [ledger_mode, timezone, target_date, observed],
        ).fetchone()
        self.connection.begin()
        decisions: list[BettingDecision] = []
        try:
            self.connection.execute(
                "INSERT INTO prediction_runs VALUES (?, ?, ?, ?, ?, current_timestamp)",
                [
                    prediction_run_id,
                    observed,
                    observed,
                    odds_time[0] if odds_time else None,
                    model_version,
                ],
            )
            for index, row in enumerate(frame.iter_rows(named=True)):
                market = [
                    row.get("bookmaker_home_fair"),
                    row.get("bookmaker_draw_fair"),
                    row.get("bookmaker_away_fair"),
                ]
                quotes = self._quotes(str(row["fixture_id"]), observed)
                probabilities_by_name = dict(zip(("home", "draw", "away"), probabilities[index].tolist(), strict=True))
                exposure_row = self.connection.execute(
                    "SELECT coalesce(sum(stake_fraction), 0), count(*) FROM prediction_decisions "
                    "WHERE state='BET_IF_PRICE_AVAILABLE' AND CAST(decision_timestamp AS DATE)=CAST(? AS DATE)",
                    [observed],
                ).fetchone()
                competition_row = self.connection.execute(
                    "SELECT CAST(f.competition_season_id AS VARCHAR), d.universe_state "
                    "FROM fixtures_current f LEFT JOIN competition_discoveries d "
                    "USING (competition_season_id) WHERE CAST(f.fixture_id AS VARCHAR)=? "
                    "ORDER BY d.discovered_at DESC NULLS LAST LIMIT 1",
                    [str(row["fixture_id"])],
                ).fetchone()
                applicability_state, applicability_reasons = self._fixture_applicability(
                    training_domain,
                    home_team_id=str(row["home_team_id"]),
                    away_team_id=str(row["away_team_id"]),
                    competition_season_id=str(competition_row[0]) if competition_row else None,
                )
                fixture_applicable = applicability_state == "IN_DOMAIN"
                decision = decide_wager(
                    probabilities_by_name,
                    quotes,
                    decision_time=observed,
                    fixture_kickoff=row["kickoff_utc"],
                    model_metrics=model_metrics,
                    calibrated=calibration_validated,
                    home_history=int(row.get("home_history_matches") or 0),
                    away_history=int(row.get("away_history_matches") or 0),
                    evidence=self.evidence_policy,
                    risk=self.risk_policy,
                    current_daily_exposure=float(exposure_row[0]) if exposure_row else 0.0,
                    active_recommendations=int(exposure_row[1]) if exposure_row else 0,
                    fixture_applicable=fixture_applicable,
                    competition_actionable=bool(competition_row and competition_row[1] == "ACTIONABLE"),
                    market_family_qualified=market_role_qualified,
                    uncertainty_validated=uncertainty_validated,
                    margin_threshold_validated=margin_validated,
                )
                decisions.append(decision)
                self.connection.execute(
                    "INSERT INTO predictions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        prediction_run_id,
                        row["fixture_id"],
                        *probabilities[index].tolist(),
                        *market,
                        "MARKET_AVAILABLE" if all(value is not None for value in market) else "MODEL_ONLY",
                    ],
                )
                self.connection.execute(
                    "INSERT INTO prediction_decisions "
                    "(decision_id, prediction_run_id, fixture_id, state, reason_codes, selected_market, "
                    "model_probability, market_fair_probability, reference_decimal_odds, raw_implied_probability, "
                    "reference_expected_value, minimum_acceptable_odds, odds_observation_timestamp, "
                    "decision_timestamp, stake_fraction, reference_state, execution_edge, "
                    "manual_price_confirmation_required, applicability_state, applicability_reason_codes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        str(uuid.uuid4()),
                        prediction_run_id,
                        row["fixture_id"],
                        decision.state,
                        json.dumps(decision.reasons),
                        decision.selected_market,
                        decision.model_probability,
                        decision.market_fair_probability,
                        decision.reference_decimal_odds,
                        decision.raw_implied_probability,
                        decision.reference_expected_value,
                        decision.minimum_acceptable_odds,
                        decision.odds_observed_at,
                        observed,
                        decision.stake_fraction,
                        decision.reference_state,
                        decision.execution_edge,
                        decision.manual_price_confirmation_required,
                        applicability_state,
                        json.dumps(applicability_reasons),
                    ],
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        output_columns = [
            "fixture_id",
            "kickoff_utc",
            "competition",
            "home_team_id",
            "home_team_name",
            "away_team_id",
            "away_team_name",
        ]
        for column in (
            "bookmaker_home_fair",
            "bookmaker_draw_fair",
            "bookmaker_away_fair",
        ):
            if column in frame.columns:
                output_columns.append(column)
        output = frame.select(output_columns).with_columns(
            pl.Series("probability_home", probabilities[:, 0]),
            pl.Series("probability_draw", probabilities[:, 1]),
            pl.Series("probability_away", probabilities[:, 2]),
            pl.lit(model_type).alias("model_type"),
            pl.lit(model_version).alias("model_version"),
            pl.lit(odds_time[0] if odds_time else None).alias("odds_snapshot_timestamp"),
            pl.Series("decision_state", [decision.state for decision in decisions]),
            pl.Series("decision_reasons", [list(decision.reasons) for decision in decisions]),
        )
        for outcome in ("home", "draw", "away"):
            market_column = f"bookmaker_{outcome}_fair"
            if market_column in output.columns:
                output = output.with_columns(
                    (pl.col(f"probability_{outcome}") - pl.col(market_column)).alias(
                        f"probability_difference_{outcome}"
                    )
                )
        output = output.with_columns(
            pl.when(
                pl.all_horizontal(
                    pl.col("bookmaker_home_fair").is_not_null(),
                    pl.col("bookmaker_draw_fair").is_not_null(),
                    pl.col("bookmaker_away_fair").is_not_null(),
                )
            )
            .then(pl.lit("MARKET_AVAILABLE"))
            .otherwise(pl.lit("MODEL_ONLY"))
            .alias("data_quality_status")
            if "bookmaker_home_fair" in output.columns
            else pl.lit("MODEL_ONLY").alias("data_quality_status")
        )
        return PredictionResult(prediction_run_id, model_version, frame.height, output)

    def _training_domain(self, model_type: str, model: Any, dataset_hash: str) -> TrainingDomain:
        """Recover the exact chronological training domain; missing lineage fails closed."""
        if model_type in {"poisson", "dixon-coles"}:
            teams = frozenset(str(value) for value in getattr(model, "fitted_teams", ()))
            competitions = frozenset(str(value) for value in getattr(model, "fitted_competitions", ()))
            return TrainingDomain(teams, competitions, bool(teams and competitions))
        row = self.connection.execute(
            "SELECT parquet_path FROM feature_datasets WHERE dataset_hash=? ORDER BY created_at DESC LIMIT 1",
            [dataset_hash],
        ).fetchone()
        if not row or not Path(str(row[0])).is_file():
            return TrainingDomain(frozenset(), frozenset(), False)
        frame = pl.read_parquet(Path(str(row[0])))
        required = {"fixture_id", "prediction_timestamp", "home_team_id", "away_team_id"}
        if not required <= set(frame.columns):
            return TrainingDomain(frozenset(), frozenset(), False)
        fold = split_by_time(frame["prediction_timestamp"].to_list())
        training = frame[fold.train]
        teams = frozenset(
            str(value) for column in ("home_team_id", "away_team_id") for value in training[column].to_list()
        )
        fixture_ids = [str(value) for value in training["fixture_id"].to_list()]
        if not fixture_ids:
            return TrainingDomain(teams, frozenset(), False)
        placeholders = ",".join("?" for _ in fixture_ids)
        rows = self.connection.execute(
            "SELECT DISTINCT CAST(competition_season_id AS VARCHAR) FROM fixtures_current "
            f"WHERE CAST(fixture_id AS VARCHAR) IN ({placeholders})",
            fixture_ids,
        ).fetchall()
        competitions = frozenset(str(value[0]) for value in rows)
        return TrainingDomain(teams, competitions, bool(teams and competitions))

    @staticmethod
    def _fixture_applicability(
        domain: TrainingDomain,
        *,
        home_team_id: str,
        away_team_id: str,
        competition_season_id: str | None,
    ) -> tuple[str, tuple[str, ...]]:
        if not domain.lineage_available:
            return "OUT_OF_DOMAIN", ("TRAINING_LINEAGE_UNAVAILABLE",)
        home_seen = home_team_id in domain.teams
        away_seen = away_team_id in domain.teams
        if not home_seen and not away_seen:
            return "PRIOR_ONLY", ("UNSEEN_HOME_TEAM", "UNSEEN_AWAY_TEAM")
        if not home_seen:
            return "UNSEEN_HOME_TEAM", ("UNSEEN_HOME_TEAM",)
        if not away_seen:
            return "UNSEEN_AWAY_TEAM", ("UNSEEN_AWAY_TEAM",)
        if competition_season_id not in domain.competitions:
            return "UNSEEN_COMPETITION", ("UNSEEN_COMPETITION",)
        return "IN_DOMAIN", ()

    def _quotes(self, fixture_id: str, prediction_time: datetime) -> list[MarketQuote]:
        rows = self.connection.execute(
            "WITH ranked AS (SELECT s.normalized_name, p.fair_probability, p.decimal_odds, o.observed_at, "
            "b.name, row_number() OVER (PARTITION BY b.bookmaker_id, s.selection_id "
            "ORDER BY coalesce(o.provider_update_time, o.observed_at) DESC, o.observed_at DESC, o.snapshot_id DESC) rn "
            "FROM odds_snapshots o JOIN odds_prices p USING (snapshot_id) JOIN bookmakers b USING (bookmaker_id) "
            "JOIN bet_markets m USING (market_id) JOIN bet_selections s USING (selection_id) "
            "WHERE o.fixture_id=? AND o.observed_at<=? AND lower(m.name) IN ('match winner','1x2')) "
            "SELECT normalized_name, fair_probability, decimal_odds, observed_at, name FROM ranked WHERE rn=1",
            [fixture_id, prediction_time],
        ).fetchall()
        return [
            MarketQuote(str(outcome), float(fair), float(price), observed, str(bookmaker))
            for outcome, fair, price, observed, bookmaker in rows
            if outcome in {"home", "draw", "away"} and fair is not None
        ]

    @staticmethod
    def _load_model(model_type: str, path: Path) -> Any:
        loaders: dict[str, Any] = {
            "elo": EloModel,
            "poisson": PoissonModel,
            "dixon-coles": DixonColesModel,
            "logistic": LogisticProbabilityModel,
            "catboost": CatBoostProbabilityModel,
            "lightgbm": LightGBMProbabilityModel,
        }
        try:
            return loaders[model_type].load(path)
        except KeyError as exc:
            raise ValueError(f"Unsupported champion model type {model_type!r}") from exc

    @staticmethod
    def _predict_probabilities(
        model_type: str, model: Any, frame: pl.DataFrame, manifest: dict[str, Any]
    ) -> np.ndarray:
        if model_type in {"elo", "poisson", "dixon-coles"}:
            fixtures = list(
                zip(
                    frame["home_team_id"].cast(pl.String).to_list(),
                    frame["away_team_id"].cast(pl.String).to_list(),
                    strict=True,
                )
            )
            return np.asarray(model.predict_proba(fixtures))
        columns = manifest.get("feature_columns")
        if not isinstance(columns, list) or not columns:
            raise ValueError("Champion manifest has no feature column contract")
        missing = set(columns) - set(frame.columns)
        if missing:
            raise ValueError(f"Tomorrow feature dataset is missing model features: {sorted(missing)}")
        probabilities = np.asarray(model.predict_proba(frame.select(columns).cast(pl.Float64).to_numpy()))
        ordered = np.zeros((frame.height, 3))
        for source, target in enumerate(np.asarray(model.estimator.classes_, dtype=int)):
            ordered[:, target] = probabilities[:, source]
        return ordered
