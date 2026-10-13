from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, PositiveFloat, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

from sports_engine.core.exceptions import ConfigurationError
from sports_engine.core.paths import project_root, resolve_project_path


class HttpConfig(BaseModel):
    timeout_seconds: PositiveFloat = 30.0
    retry_count: int = Field(default=3, ge=0, le=10)
    backoff_base_seconds: PositiveFloat = 0.5
    max_concurrency: PositiveInt = 1


class QuotaConfig(BaseModel):
    minimum_daily_reserve: int = Field(default=10, ge=0)
    minimum_minute_reserve: int = Field(default=2, ge=0)


class FeatureConfig(BaseModel):
    windows: list[PositiveInt] = [3, 5, 10]
    exponential_half_life: PositiveFloat = 5.0
    prediction_lead_hours: PositiveInt = 24


class ModelPromotionConfig(BaseModel):
    enabled: bool = True
    policy_version: str = "match-odds-v1"
    market_family: str = "MATCH_ODDS"
    minimum_evaluation_rows: PositiveInt = 200
    minimum_baseline_rows: PositiveInt = 200
    market_baseline_mode: Literal["required", "when_available"] = "required"
    eligible_model_types: list[str] = ["poisson", "dixon-coles", "logistic", "catboost", "lightgbm"]
    minimum_walk_forward_folds: PositiveInt = 4
    maximum_expected_calibration_error: float = Field(default=0.08, ge=0, le=1)
    maximum_fold_expected_calibration_error: float = Field(default=0.12, ge=0, le=1)
    maximum_rps_upper_bound: float = Field(default=0.26, ge=0, le=1)
    maximum_calibration_regression: float = Field(default=0.01, ge=0, le=1)
    require_significant_market_outperformance: bool = True
    base_required_expected_return: float = Field(default=0.02, ge=0, le=1)
    minimum_uncertainty_adjustment: float = Field(default=0.01, ge=0, le=1)
    maximum_uncertainty_adjustment: float = Field(default=0.10, ge=0, le=1)
    minimum_competition_evaluation_rows: PositiveInt = 100
    maximum_competition_expected_calibration_error: float = Field(default=0.08, ge=0, le=1)


class ModelConfig(BaseModel):
    random_seed: int = 20261007
    cpu_threads: PositiveInt = 2
    time_decay_half_life_days: PositiveFloat = 365.0
    minimum_team_history: PositiveInt = 10
    require_calibration_for_betting: bool = True
    minimum_prediction_confidence: float = Field(default=0.40, ge=0, le=1)
    historical_training_ledgers: list[str] = ["replay"]
    promotion: ModelPromotionConfig = ModelPromotionConfig()


class BackfillConfig(BaseModel):
    maximum_requests_per_run: int = Field(default=1000, ge=0)
    maximum_daily_requests_per_run: int = Field(default=100, ge=0)
    repair_attempt_limit: PositiveInt = 3


class OddsConfig(BaseModel):
    target_days_ahead: PositiveInt = 1
    snapshot_dedupe_seconds: int = Field(default=60, ge=0)
    aged_reference_minutes: PositiveInt = 180


class RiskConfig(BaseModel):
    maximum_bankroll_fraction_per_wager: float = Field(default=0.01, gt=0, le=1)
    maximum_daily_exposure: float = Field(default=0.05, gt=0, le=1)
    maximum_simultaneous_recommendations: PositiveInt = 5
    fractional_kelly: float = Field(default=0.25, ge=0, le=1)
    hard_stake_cap: float = Field(default=0.01, gt=0, le=1)
    minimum_probability_advantage: float = Field(default=0.03, ge=0, le=1)
    minimum_expected_value: float = Field(default=0.0, ge=0)


class ShadowCandidateConfig(BaseModel):
    """Exploratory gates for prospective paper tracking, never live execution."""

    enabled: bool = True
    policy_version: str = "shadow-bootstrap-v1"
    allowed_markets: list[str] = ["MATCH_ODDS", "BTTS", "TOTAL_GOALS"]
    minimum_probability_advantage: float = Field(default=0.03, ge=0, le=1)
    minimum_reference_expected_return: float = Field(default=0.03, ge=0, le=1)
    required_expected_return: float = Field(default=0.03, ge=0, le=1)
    uncertainty_buffer: float = Field(default=0.02, ge=0, le=1)
    minimum_effective_team_matches: float = Field(default=5.0, ge=0)
    maximum_prior_fraction: float = Field(default=0.40, ge=0, le=1)
    maximum_absolute_probability_gap: float = Field(default=0.15, gt=0, le=1)
    minimum_reference_bookmakers: PositiveInt = 2
    maximum_candidates_per_fixture: PositiveInt = 1
    maximum_candidates_per_run: PositiveInt = 10
    stale_run_minutes: PositiveInt = 60


class ApplicationMode(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class ProviderAccessConfig(BaseModel):
    replay_season: int = Field(default=2024, ge=2000, le=2100)


class CleanupConfig(BaseModel):
    enabled: bool = True
    interval_hours: PositiveInt = 24
    retention_days: int = Field(default=7, ge=0, le=365)


class AppConfig(BaseModel):
    mode: ApplicationMode = ApplicationMode.DEVELOPMENT
    timezone: str = "UTC"
    data_dir: Path = Path("data")
    artifacts_dir: Path = Path("artifacts")
    state_dir: Path = Path("state")
    logs_dir: Path = Path("logs")
    database_path: Path = Path("data/warehouse/sports.duckdb")
    raw_retention_days: PositiveInt | None = None
    cleanup: CleanupConfig = CleanupConfig()
    http: HttpConfig = HttpConfig()
    quota: QuotaConfig = QuotaConfig()
    features: FeatureConfig = FeatureConfig()
    models: ModelConfig = ModelConfig()
    backfill: BackfillConfig = BackfillConfig()
    odds: OddsConfig = OddsConfig()
    risk: RiskConfig = RiskConfig()
    shadow_candidates: ShadowCandidateConfig = ShadowCandidateConfig()
    provider_access: ProviderAccessConfig = ProviderAccessConfig()

    def absolute_paths(self) -> "AppConfig":
        copy = self.model_copy(deep=True)
        for attr in ("data_dir", "artifacts_dir", "state_dir", "logs_dir", "database_path"):
            setattr(copy, attr, resolve_project_path(getattr(copy, attr)))
        return copy


class Environment(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    api_football_key: str | None = None
    api_football_base_url: str = "https://v3.football.api-sports.io"
    sports_engine_config: Path = Path("config/app.yaml")


@lru_cache(maxsize=4)
def load_config(path: str | Path | None = None) -> AppConfig:
    requested = Path(path) if path else Environment().sports_engine_config
    config_path = requested if requested.is_absolute() else project_root() / requested
    try:
        payload: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        return AppConfig.model_validate(payload).absolute_paths()
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Cannot load configuration {config_path}: {exc}") from exc
