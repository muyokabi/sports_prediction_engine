from collections.abc import Callable
from dataclasses import dataclass

import duckdb

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import ProviderPlanAccessError, QuotaExhaustedError
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.providers.base import SportsDataProvider
from sports_engine.sports.football.ingestion.reference_data import ReferenceDataService
from sports_engine.sports.football.normalization.fixtures import normalize_fixture
from sports_engine.warehouse import checkpoints
from sports_engine.warehouse.repositories.fixtures import upsert_fixture
from sports_engine.warehouse.repositories.leagues import (
    admitted_seasons,
    mark_provider_season_inaccessible,
)
from sports_engine.warehouse.repositories.request_log import latest_raw_path
from sports_engine.warehouse.transactions import transaction


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    complete: bool
    competition_seasons_completed: int
    teams_written: int
    fixtures_written: int
    next_competition_index: int
    next_stage: str
    blocked_reason: str | None = None


class SeasonBootstrapService:
    checkpoint_key = "football.bootstrap.progress"

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        provider: SportsDataProvider,
        raw_path_resolver: Callable[[str, str | None], str] | None = None,
    ) -> None:
        self.connection = connection
        self.provider = provider
        self.raw_path_resolver = raw_path_resolver or (
            lambda purpose, job_run_id: latest_raw_path(connection, purpose, job_run_id)
        )
        self.references = ReferenceDataService(connection, provider, self.raw_path_resolver)

    def run(self, *, job_run_id: str | None = None, ledger_mode: str | None = None) -> BootstrapResult:
        seasons = admitted_seasons(self.connection, ledger_mode)
        checkpoint_key = f"{self.checkpoint_key}.{ledger_mode or 'all'}"
        progress = checkpoints.get(self.connection, checkpoint_key) or {"index": 0, "stage": "teams"}
        index = int(progress.get("index", 0))
        stage = str(progress.get("stage", "teams"))
        if index < 0 or index >= len(seasons):
            index, stage = 0, "teams"
        teams_written = 0
        fixtures_written = 0
        completed = 0
        for current_index in range(index, len(seasons)):
            competition_season_id, league_id, season = seasons[current_index]
            current_stage = stage if current_index == index else "teams"
            try:
                if current_stage == "teams":
                    result = self.references.sync_teams(
                        competition_season_id=competition_season_id,
                        provider_league_id=league_id,
                        provider_season=season,
                        job_run_id=job_run_id,
                    )
                    teams_written += result.teams_written
                    checkpoints.put(
                        self.connection,
                        checkpoint_key,
                        {"index": current_index, "stage": "fixtures"},
                        job_run_id,
                    )
                purpose = f"season_bootstrap:{league_id}:{season}"
                rows = self.provider.get(
                    Endpoint.FIXTURES,
                    {"league": league_id, "season": season},
                    purpose=purpose,
                    priority=Priority.P4,
                    job_run_id=job_run_id,
                )
                raw_path = self.raw_path_resolver(purpose, job_run_id)
                with transaction(self.connection):
                    for payload in rows:
                        upsert_fixture(
                            self.connection,
                            normalize_fixture(payload),
                            competition_season_id,
                            raw_path,
                        )
                        fixtures_written += 1
                    checkpoints.put(
                        self.connection,
                        checkpoint_key,
                        {"index": current_index + 1, "stage": "teams"},
                        job_run_id,
                    )
                completed += 1
            except QuotaExhaustedError:
                saved = checkpoints.get(self.connection, checkpoint_key) or {
                    "index": current_index,
                    "stage": current_stage,
                }
                return BootstrapResult(
                    False,
                    completed,
                    teams_written,
                    fixtures_written,
                    int(saved["index"]),
                    str(saved["stage"]),
                )
            except ProviderPlanAccessError as exc:
                reason = str(exc)
                mark_provider_season_inaccessible(self.connection, season, reason)
                checkpoints.put(
                    self.connection,
                    checkpoint_key,
                    {"index": current_index, "stage": current_stage},
                    job_run_id,
                )
                return BootstrapResult(
                    False,
                    completed,
                    teams_written,
                    fixtures_written,
                    current_index,
                    current_stage,
                    reason,
                )
        checkpoints.put(
            self.connection,
            checkpoint_key,
            {"index": 0, "stage": "teams"},
            job_run_id,
        )
        return BootstrapResult(True, completed, teams_written, fixtures_written, 0, "teams")
