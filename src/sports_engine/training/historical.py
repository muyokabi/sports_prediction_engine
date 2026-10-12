from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from sports_engine.core.config import AppConfig, ApplicationMode
from sports_engine.evaluation.comparison import compare_evaluation_reports
from sports_engine.evaluation.reports import WalkForwardEvaluator
from sports_engine.models.registry import MODEL_TYPES, validate_model_type
from sports_engine.sports.football.features.dataset import PointInTimeFeatureBuilder
from sports_engine.training.promotion import PromotionCycleResult, run_automated_promotion
from sports_engine.training.trainer import ModelTrainer

ML_MODEL_TYPES = ("logistic", "catboost", "lightgbm")


@dataclass(frozen=True, slots=True)
class HistoricalModelResult:
    model_type: str
    version: str | None
    evaluation_path: Path | None
    error: str | None


@dataclass(frozen=True, slots=True)
class HistoricalTrainingResult:
    dataset_id: str
    dataset_name: str
    dataset_rows: int
    replay_rows: int
    models: tuple[HistoricalModelResult, ...]
    comparison_path: Path | None
    promotion: PromotionCycleResult | None


def train_historical_models(
    connection: duckdb.DuckDBPyConnection,
    config: AppConfig,
    *,
    model_types: tuple[str, ...] = MODEL_TYPES,
    dataset_name: str | None = None,
    rolling_periods: int | None = None,
    assess_promotions: bool = True,
    include_observation_leagues: bool = False,
    now: datetime | None = None,
) -> HistoricalTrainingResult:
    """Force full-refit candidates from current plus replay point-in-time history."""
    selected = tuple(dict.fromkeys(validate_model_type(model) for model in model_types))
    if not selected:
        raise ValueError("Select at least one model type")

    replay_row = connection.execute(
        "SELECT count(*) FROM fixtures_current f JOIN competition_seasons cs "
        "USING (competition_season_id) WHERE cs.ledger_mode='replay' "
        "AND f.status_short IN ('FT','AET','PEN') "
        "AND f.home_goals IS NOT NULL AND f.away_goals IS NOT NULL"
    ).fetchone()
    replay_rows = int(replay_row[0]) if replay_row else 0
    if replay_rows == 0:
        raise ValueError(
            "No completed replay results are available. Run football fetch-backfill "
            "with --season or --past-seasons first."
        )

    observed = now or datetime.now(UTC)
    name = dataset_name or f"historical-models-{observed.strftime('%Y%m%dT%H%M%S%fZ')}"
    primary_ledger = "replay" if config.mode == ApplicationMode.DEVELOPMENT else "production"
    historical_ledgers = list(dict.fromkeys((*config.models.historical_training_ledgers, "replay")))
    artifact = PointInTimeFeatureBuilder(
        connection,
        config.data_dir / "parquet" / "features",
        windows=config.features.windows,
        exponential_half_life=config.features.exponential_half_life,
        prediction_lead_hours=config.features.prediction_lead_hours,
        historical_ledger_modes=historical_ledgers,
        replay_universe_states=None if include_observation_leagues else ["ACTIONABLE"],
    ).build(name, ledger_mode=primary_ledger)

    trainer = ModelTrainer(
        connection,
        config.artifacts_dir,
        random_seed=config.models.random_seed,
        cpu_threads=config.models.cpu_threads,
        time_decay_half_life_days=config.models.time_decay_half_life_days,
    )
    evaluator = WalkForwardEvaluator(
        connection,
        config.artifacts_dir / "evaluation",
        random_seed=config.models.random_seed,
        cpu_threads=config.models.cpu_threads,
        time_decay_half_life_days=config.models.time_decay_half_life_days,
        minimum_competition_rows=config.models.promotion.minimum_competition_evaluation_rows,
        maximum_competition_ece=config.models.promotion.maximum_competition_expected_calibration_error,
    )
    outcomes: list[HistoricalModelResult] = []
    trained_versions: list[str] = []
    for model_type in selected:
        version: str | None = None
        try:
            trained = trainer.train(
                model_type,
                dataset_name=name,
                calibration_method="platt" if model_type in ML_MODEL_TYPES else None,
                training_mode="full_refit",
            )
            version = trained.version
            trained_versions.append(version)
            report = evaluator.evaluate(
                model_type,
                dataset_name=name,
                rolling_train_periods=rolling_periods,
            )
            outcomes.append(HistoricalModelResult(model_type, version, report.path, None))
        except (OSError, RuntimeError, ValueError) as exc:
            outcomes.append(HistoricalModelResult(model_type, version, None, str(exc)))

    evaluation_paths = [item.evaluation_path for item in outcomes if item.evaluation_path is not None]
    comparison_path = (
        compare_evaluation_reports(
            evaluation_paths,
            config.artifacts_dir / "evaluation" / "comparisons",
            random_seed=config.models.random_seed,
        )
        if len(evaluation_paths) > 1
        else None
    )

    promotion = (
        run_automated_promotion(connection, config, versions=tuple(trained_versions), now=observed)
        if assess_promotions and trained_versions
        else None
    )
    return HistoricalTrainingResult(
        artifact.dataset_id,
        name,
        artifact.row_count,
        replay_rows,
        tuple(outcomes),
        comparison_path,
        promotion,
    )
