from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb

from sports_engine.core.enums import Priority
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.providers.base import SportsDataProvider
from sports_engine.sports.football.ingestion.detailed_matches import (
    DetailedIngestionResult,
    DetailedMatchIngestionService,
)
from sports_engine.sports.football.normalization.fixtures import normalize_fixture
from sports_engine.warehouse.repositories.fixtures import upsert_fixture
from sports_engine.warehouse.repositories.leagues import admitted_seasons
from sports_engine.warehouse.repositories.request_log import latest_raw_path
from sports_engine.warehouse.transactions import transaction

FINAL_STATUSES = frozenset({"FT", "AET", "PEN"})


@dataclass(frozen=True, slots=True)
class DailyUpdateResult:
    discovery_dates: tuple[date, ...]
    relevant_fixtures: int
    completed_candidates: int
    fixture_records_written: int
    enrichment: DetailedIngestionResult


class DailyUpdateService:
    """Idempotent date discovery plus batched completed-match enrichment."""

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        provider: SportsDataProvider,
        quarantine_dir: Path,
        raw_path_resolver: Callable[[str, str | None], str] | None = None,
        repair_attempt_limit: int = 3,
    ) -> None:
        self.connection = connection
        self.provider = provider
        self.quarantine_dir = quarantine_dir
        self.repair_attempt_limit = repair_attempt_limit
        self.raw_path_resolver = raw_path_resolver or (
            lambda purpose, job_run_id: latest_raw_path(connection, purpose, job_run_id)
        )

    def run(
        self,
        operational_date: date,
        *,
        ledger_mode: str,
        include_today: bool = True,
        job_run_id: str | None = None,
    ) -> DailyUpdateResult:
        target_dates = [operational_date - timedelta(days=1)]
        if include_today:
            target_dates.append(operational_date)
        target_dates.append(operational_date + timedelta(days=1))
        admitted = {
            (league_id, season): competition_season_id
            for competition_season_id, league_id, season in admitted_seasons(self.connection, ledger_mode)
        }
        relevant = 0
        written = 0
        completed_ids: list[int] = []
        for target_date in target_dates:
            purpose = f"daily_discovery:{ledger_mode}:{target_date.isoformat()}"
            rows = self.provider.get(
                Endpoint.FIXTURES,
                {"date": target_date.isoformat()},
                purpose=purpose,
                priority=Priority.P2,
                job_run_id=job_run_id,
            )
            raw_path = self.raw_path_resolver(purpose, job_run_id)
            for payload in rows:
                league = payload.get("league") or {}
                league_id = league.get("id")
                provider_season = league.get("season")
                if not isinstance(league_id, int) or not isinstance(provider_season, int):
                    continue
                key = (league_id, provider_season)
                competition_season_id = admitted.get(key)
                if competition_season_id is None:
                    continue
                relevant += 1
                record = normalize_fixture(payload)
                with transaction(self.connection):
                    upsert_fixture(
                        self.connection,
                        record,
                        competition_season_id,
                        raw_path,
                    )
                written += 1
                if record.status_short in FINAL_STATUSES and self._needs_enrichment(record.provider_fixture_id):
                    completed_ids.append(record.provider_fixture_id)
        enrichment = DetailedMatchIngestionService(
            self.connection,
            self.provider,
            self.quarantine_dir,
            self.raw_path_resolver,
        ).run(dict.fromkeys(completed_ids), job_run_id=job_run_id)
        return DailyUpdateResult(tuple(target_dates), relevant, len(completed_ids), written, enrichment)

    def _needs_enrichment(self, provider_fixture_id: int) -> bool:
        row = self.connection.execute(
            "SELECT q.eligibility, r.attempt_count, r.next_retry_after FROM fixtures f "
            "LEFT JOIN fixture_quality_status q USING (fixture_id) "
            "LEFT JOIN fixture_repair_state r USING (fixture_id) "
            "WHERE f.provider_fixture_id=?",
            [provider_fixture_id],
        ).fetchone()
        if row is None or row[0] == "ML_ELIGIBLE":
            return row is None
        attempts = int(row[1]) if row[1] is not None else 0
        retry_after = row[2]
        return attempts < self.repair_attempt_limit and (retry_after is None or retry_after <= datetime.now(UTC))
