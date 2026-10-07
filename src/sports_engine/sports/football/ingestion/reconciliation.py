from collections.abc import Callable
from dataclasses import dataclass

import duckdb

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import QuotaExhaustedError
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.providers.base import SportsDataProvider
from sports_engine.sports.football.normalization.fixtures import normalize_fixture
from sports_engine.warehouse import checkpoints
from sports_engine.warehouse.repositories.fixtures import upsert_fixture
from sports_engine.warehouse.repositories.leagues import admitted_seasons
from sports_engine.warehouse.repositories.request_log import latest_raw_path
from sports_engine.warehouse.transactions import transaction


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    complete: bool
    fixtures_seen: int
    observations_added: int
    next_competition_index: int


class FixtureReconciliationService:
    checkpoint_key = "football.reconciliation.next_competition_index"

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

    def run(self, *, job_run_id: str | None = None, ledger_mode: str | None = None) -> ReconciliationResult:
        seasons = admitted_seasons(self.connection, ledger_mode)
        checkpoint_key = f"{self.checkpoint_key}.{ledger_mode or 'all'}"
        saved = checkpoints.get(self.connection, checkpoint_key)
        start = int(saved) if saved is not None else 0
        if start < 0 or start >= len(seasons):
            start = 0
        seen = 0
        observations_before = self._observation_count()
        for index in range(start, len(seasons)):
            competition_season_id, league_id, season = seasons[index]
            purpose = f"fixture_reconciliation:{league_id}:{season}"
            try:
                rows = self.provider.get(
                    Endpoint.FIXTURES,
                    {"league": league_id, "season": season},
                    purpose=purpose,
                    priority=Priority.P4,
                    job_run_id=job_run_id,
                )
            except QuotaExhaustedError:
                checkpoints.put(self.connection, checkpoint_key, index, job_run_id)
                return ReconciliationResult(
                    False,
                    seen,
                    self._observation_count() - observations_before,
                    index,
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
                    seen += 1
                checkpoints.put(self.connection, checkpoint_key, index + 1, job_run_id)
        checkpoints.put(self.connection, checkpoint_key, 0, job_run_id)
        return ReconciliationResult(
            True,
            seen,
            self._observation_count() - observations_before,
            0,
        )

    def _observation_count(self) -> int:
        row = self.connection.execute("SELECT count(*) FROM fixture_observations").fetchone()
        return int(row[0]) if row else 0
