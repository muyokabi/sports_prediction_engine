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

from sports_engine.models.ml.catboost import CatBoostProbabilityModel
from sports_engine.models.ml.lightgbm import LightGBMProbabilityModel
from sports_engine.models.ml.logistic import LogisticProbabilityModel
from sports_engine.models.statistical.dixon_coles import DixonColesModel
from sports_engine.models.statistical.elo import EloModel
from sports_engine.models.statistical.poisson import PoissonModel
from sports_engine.sports.football.features.dataset import PointInTimeFeatureBuilder


@dataclass(frozen=True, slots=True)
class PredictionResult:
    prediction_run_id: str
    model_version: str
    fixture_count: int
    frame: pl.DataFrame


class PredictionService:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        windows: list[int],
        exponential_half_life: float,
        prediction_lead_hours: int,
    ) -> None:
        self.connection = connection
        self.builder = PointInTimeFeatureBuilder(
            connection,
            Path("."),
            windows=windows,
            exponential_half_life=exponential_half_life,
            prediction_lead_hours=prediction_lead_hours,
        )

    def predict(
        self,
        target_date: date,
        *,
        ledger_mode: str,
        timezone: str,
        observed_at: datetime | None = None,
    ) -> PredictionResult:
        champion = self.connection.execute(
            "SELECT model_type, version, artifact_path, calibration_method FROM model_runs "
            "WHERE status='champion' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not champion:
            raise ValueError("No champion model is registered")
        observed = observed_at or datetime.now(UTC)
        frame = self.builder.build_prediction_frame(
            datetime.combine(target_date, datetime.min.time(), tzinfo=UTC),
            ledger_mode=ledger_mode,
            observed_at=observed,
            timezone=timezone,
        )
        if frame.is_empty():
            raise ValueError(f"No unplayed {ledger_mode} fixtures found for {target_date}")
        model_type, model_version, artifact_value, calibration_method = champion
        artifact_path = Path(artifact_value)
        manifest_path = artifact_path.with_suffix(artifact_path.suffix + ".json")
        if not artifact_path.is_file() or not manifest_path.is_file():
            raise ValueError(f"Champion artifact or manifest is missing: {artifact_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        model = self._load_model(model_type, artifact_path)
        probabilities = self._predict_probabilities(model_type, model, frame, manifest)
        if calibration_method:
            calibration_path = artifact_path.parent / "calibrator.pkl"
            if not calibration_path.is_file():
                raise ValueError(f"Champion calibration artifact is missing: {calibration_path}")
            calibrator = pickle.loads(calibration_path.read_bytes())
            probabilities = calibrator.transform(probabilities)
        prediction_run_id = str(uuid.uuid4())
        odds_time = self.connection.execute(
            "SELECT max(o.observed_at) FROM odds_snapshots o JOIN fixtures_current f USING (fixture_id) "
            "JOIN competition_seasons cs USING (competition_season_id) "
            "WHERE cs.ledger_mode=? AND CAST(timezone(?, f.kickoff_utc) AS DATE)=? "
            "AND o.observed_at<=?",
            [ledger_mode, timezone, target_date, observed],
        ).fetchone()
        self.connection.begin()
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
