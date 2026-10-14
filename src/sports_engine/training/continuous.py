import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from sports_engine.core.config import AppConfig
from sports_engine.evaluation.reports import WalkForwardEvaluator
from sports_engine.models.registry import ModelRegistry
from sports_engine.sports.football.features.dataset import PointInTimeFeatureBuilder
from sports_engine.training.evidence import EvidenceState
from sports_engine.training.promotion import run_automated_promotion
from sports_engine.training.scheduler import UpdateDecision, assess_model_update
from sports_engine.training.trainer import ModelTrainer, TrainingResult

STATISTICAL_MODEL_TYPES = ("elo", "poisson", "dixon-coles")
ML_MODEL_TYPES = ("logistic", "catboost", "lightgbm")
CONTINUOUS_MODEL_TYPES = (*STATISTICAL_MODEL_TYPES, *ML_MODEL_TYPES)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ContinuousLearningResult:
    eligible_observations: int
    due_models: tuple[str, ...]
    trained_versions: tuple[str, ...]
    evaluation_paths: tuple[Path, ...]
    promoted_versions: tuple[str, ...]
    withheld_versions: tuple[str, ...]
    errors: tuple[str, ...]


def run_due_ml_updates(
    connection: duckdb.DuckDBPyConnection,
    config: AppConfig,
    *,
    ledger_mode: str,
    now: datetime | None = None,
) -> ContinuousLearningResult:
    """Run due-only immutable challenger generation before analysis.

    Promotion remains fail-closed until market-role, calibration, uncertainty,
    and market-baseline evidence is sufficient; candidates that do not clear
    every gate are retained as immutable challengers.
    """
    observed = now or datetime.now(UTC)
    builder = PointInTimeFeatureBuilder(
        connection,
        config.data_dir / "parquet" / "features",
        windows=config.features.windows,
        exponential_half_life=config.features.exponential_half_life,
        prediction_lead_hours=config.features.prediction_lead_hours,
        historical_ledger_modes=config.models.historical_training_ledgers,
        replay_universe_states=["ACTIONABLE"],
    )
    eligible = builder.count_training_observations(ledger_mode)
    if eligible == 0:
        # Empty history is normal immediately after installation.  There is
        # no dataset to build or candidate to train yet, and the principal
        # analysis command must remain usable while backfill accumulates it.
        promotion = run_automated_promotion(connection, config, now=observed)
        return ContinuousLearningResult(
            0,
            (),
            (),
            (),
            promotion.promoted_versions,
            promotion.withheld_versions,
            (),
        )
    decisions = tuple(
        assess_model_update(connection, model_type, eligible_observations=eligible, now=observed)
        for model_type in CONTINUOUS_MODEL_TYPES
    )
    due = tuple(decision for decision in decisions if decision.due)
    if not due:
        promotion = run_automated_promotion(connection, config, now=observed)
        return ContinuousLearningResult(
            eligible,
            (),
            (),
            (),
            promotion.promoted_versions,
            promotion.withheld_versions,
            (),
        )

    dataset_name = f"automatic-models-{observed.strftime('%Y%m%dT%H%M%S%fZ')}"
    builder.build(dataset_name, ledger_mode=ledger_mode)
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
    registry = ModelRegistry(connection)
    trained: list[str] = []
    evaluations: list[Path] = []
    withheld: list[str] = []
    errors: list[str] = []
    for decision in due:
        started = time.perf_counter()
        logger.info(
            "continuous_learning model_update_start model_type=%s mode=%s eligible_observations=%s",
            decision.model_type,
            decision.mode,
            eligible,
        )
        try:
            result = _train_due_candidate(trainer, decision, dataset_name)
            trained.append(result.version)
            trained_at = time.perf_counter()
            logger.info(
                "continuous_learning model_training_complete model_type=%s version=%s elapsed_seconds=%.1f",
                decision.model_type,
                result.version,
                trained_at - started,
            )
            report = evaluator.evaluate(decision.model_type, dataset_name=dataset_name)
            evaluations.append(report.path)
            logger.info(
                "continuous_learning model_evaluation_complete model_type=%s version=%s "
                "evaluation_seconds=%.1f total_seconds=%.1f",
                decision.model_type,
                result.version,
                time.perf_counter() - trained_at,
                time.perf_counter() - started,
            )
            # A failed evidence gate is a deterministic rejection. All other
            # candidates remain withheld; numerical rank alone cannot promote.
            if result.evidence_state == EvidenceState.INSUFFICIENT_DATA:
                registry.reject(result.version)
            else:
                withheld.append(result.version)
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"{decision.model_type}: {exc}")
            logger.exception(
                "continuous_learning model_update_failed model_type=%s elapsed_seconds=%.1f",
                decision.model_type,
                time.perf_counter() - started,
            )
    promotion = run_automated_promotion(connection, config, now=observed)
    promoted = set(promotion.promoted_versions)
    all_withheld = tuple(dict.fromkeys([*withheld, *promotion.withheld_versions]))
    return ContinuousLearningResult(
        eligible,
        tuple(decision.model_type for decision in due),
        tuple(trained),
        tuple(evaluations),
        promotion.promoted_versions,
        tuple(version for version in all_withheld if version not in promoted),
        tuple(errors),
    )


def _train_due_candidate(trainer: ModelTrainer, decision: UpdateDecision, dataset_name: str) -> TrainingResult:
    mode = decision.mode if decision.current_version else "full_refit"
    parent = decision.current_version if mode == "warm_start" else None
    try:
        return trainer.train(
            decision.model_type,
            dataset_name=dataset_name,
            calibration_method="platt" if decision.model_type in ML_MODEL_TYPES else None,
            training_mode=mode,
            parent_model_version=parent,
        )
    except ValueError:
        if mode != "warm_start":
            raise
        # Warm starts can be invalid after a feature-schema change or when the
        # new chronological slice lacks class support. A versioned full refit
        # is the safe, immutable fallback.
        return trainer.train(
            decision.model_type,
            dataset_name=dataset_name,
            calibration_method="platt" if decision.model_type in ML_MODEL_TYPES else None,
            training_mode="full_refit",
        )
