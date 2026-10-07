from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

import duckdb

from sports_engine.core.enums import Priority
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.sports.football.normalization.odds import normalize_odds
from sports_engine.warehouse.repositories.odds import store_odds_snapshot
from sports_engine.warehouse.repositories.request_log import latest_raw_path
from sports_engine.warehouse.transactions import transaction


class PaginatedProvider(Protocol):
    def get_all_pages(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        *,
        purpose: str,
        priority: Priority,
        job_run_id: str | None = None,
    ) -> Iterator[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class OddsIngestionResult:
    payloads_seen: int
    snapshots_written: int
    fixtures_not_in_ledger: int


class OddsIngestionService:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        provider: PaginatedProvider,
        *,
        dedupe_seconds: int = 60,
        raw_path_resolver: Callable[[str, str | None], str] | None = None,
    ) -> None:
        self.connection = connection
        self.provider = provider
        self.dedupe_seconds = dedupe_seconds
        self.raw_path_resolver = raw_path_resolver or (
            lambda purpose, job_run_id: latest_raw_path(connection, purpose, job_run_id)
        )

    def run(self, target_date: date, *, job_run_id: str | None = None) -> OddsIngestionResult:
        purpose = f"odds:{target_date.isoformat()}"
        seen = written = missing = 0
        for payload in self.provider.get_all_pages(
            Endpoint.ODDS,
            {"date": target_date.isoformat()},
            purpose=purpose,
            priority=Priority.P2,
            job_run_id=job_run_id,
        ):
            seen += 1
            prices = normalize_odds(payload)
            raw_path = self.raw_path_resolver(purpose, job_run_id)
            with transaction(self.connection):
                stored = store_odds_snapshot(
                    self.connection,
                    prices,
                    source_raw_path=raw_path,
                    job_run_id=job_run_id,
                    dedupe_seconds=self.dedupe_seconds,
                )
            if stored:
                written += 1
            elif prices and not self._fixture_exists(prices[0].provider_fixture_id):
                missing += 1
        return OddsIngestionResult(seen, written, missing)

    def _fixture_exists(self, provider_fixture_id: int) -> bool:
        row = self.connection.execute(
            "SELECT count(*) FROM fixtures WHERE provider_fixture_id=?", [provider_fixture_id]
        ).fetchone()
        return bool(row and row[0])
