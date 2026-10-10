import hashlib
import json
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from sports_engine.core.enums import Eligibility, Priority
from sports_engine.core.exceptions import ProviderError, QuotaExhaustedError
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.providers.api_football.errors import ApiFootballPlanRestrictionError
from sports_engine.providers.base import SportsDataProvider
from sports_engine.sports.football.ingestion.match_enrichment import fixture_batches
from sports_engine.sports.football.quality.completeness import QualityAssessment, assess_match_package
from sports_engine.warehouse import checkpoints
from sports_engine.warehouse.repositories.match_packages import persist_match_package
from sports_engine.warehouse.repositories.request_log import latest_raw_path
from sports_engine.warehouse.transactions import transaction


@dataclass(frozen=True, slots=True)
class DetailedIngestionResult:
    complete: bool
    fixtures_received: int
    fixtures_eligible: int
    fixtures_quarantined: int
    next_batch_index: int


class DetailedMatchIngestionService:
    checkpoint_key = "football.detailed_match_ingestion.next_batch_index"

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        provider: SportsDataProvider,
        quarantine_dir: Path,
        raw_path_resolver: Callable[[str, str | None], str] | None = None,
    ) -> None:
        self.connection = connection
        self.provider = provider
        self.quarantine_dir = quarantine_dir
        self.raw_path_resolver = raw_path_resolver or (
            lambda purpose, job_run_id: latest_raw_path(connection, purpose, job_run_id)
        )

    def run(self, fixture_ids: Iterable[int], *, job_run_id: str | None = None) -> DetailedIngestionResult:
        batches = list(fixture_batches(fixture_ids))
        batch_signature = hashlib.sha256(
            ",".join(str(value) for batch in batches for value in batch).encode()
        ).hexdigest()
        saved = checkpoints.get(self.connection, self.checkpoint_key)
        start = (
            int(saved.get("index", 0)) if isinstance(saved, dict) and saved.get("signature") == batch_signature else 0
        )
        if start < 0 or start >= len(batches):
            start = 0
        received = eligible = quarantined = 0
        for index in range(start, len(batches)):
            batch = batches[index]
            purpose = f"detailed_matches:{'-'.join(str(value) for value in batch)}"
            try:
                rows = self.provider.get(
                    Endpoint.FIXTURES,
                    {"ids": "-".join(str(value) for value in batch)},
                    purpose=purpose,
                    priority=Priority.P1,
                    job_run_id=job_run_id,
                )
                packages = [(payload, self.raw_path_resolver(purpose, job_run_id)) for payload in rows]
            except ApiFootballPlanRestrictionError:
                packages = []
                try:
                    for provider_fixture_id in batch:
                        fallback_purpose = f"detailed_match_fallback:{provider_fixture_id}"
                        fallback_rows = self.provider.get(
                            Endpoint.FIXTURES,
                            {"id": provider_fixture_id},
                            purpose=fallback_purpose,
                            priority=Priority.P3,
                            job_run_id=job_run_id,
                        )
                        raw_path = self.raw_path_resolver(fallback_purpose, job_run_id)
                        packages.extend((payload, raw_path) for payload in fallback_rows)
                except QuotaExhaustedError:
                    self._save_checkpoint(index, batch_signature, job_run_id)
                    return DetailedIngestionResult(False, received, eligible, quarantined, index)
            except QuotaExhaustedError:
                self._save_checkpoint(index, batch_signature, job_run_id)
                return DetailedIngestionResult(False, received, eligible, quarantined, index)
            processed: list[tuple[dict[str, object], QualityAssessment, str]] = []
            for payload, raw_path in packages:
                received += 1
                assessment = assess_match_package(payload)
                try:
                    payload = self._repair_missing_components(
                        payload,
                        assessment.missing,
                        job_run_id=job_run_id,
                    )
                    assessment = assess_match_package(payload)
                except QuotaExhaustedError:
                    self._save_checkpoint(index, batch_signature, job_run_id)
                    return DetailedIngestionResult(False, received - len(processed) - 1, eligible, quarantined, index)
                if assessment.eligibility != Eligibility.ML_ELIGIBLE:
                    self._quarantine(payload, assessment.missing, raw_path)
                processed.append((payload, assessment, raw_path))
            # A provider page is the recovery unit. Persist the full batch and
            # advance its checkpoint atomically so interruption cannot skip the
            # uncommitted tail of a twenty-fixture page.
            with transaction(self.connection):
                for payload, assessment, raw_path in processed:
                    fixture_id = persist_match_package(
                        self.connection,
                        payload,
                        assessment,
                        source_raw_path=raw_path,
                    )
                    if assessment.eligibility == Eligibility.ML_ELIGIBLE:
                        eligible += 1
                        self.connection.execute(
                            "DELETE FROM fixture_repair_state WHERE fixture_id=?",
                            [fixture_id],
                        )
                    else:
                        quarantined += 1
                        attempt = self._record_repair_attempt(fixture_id, assessment.missing)
                        self.connection.execute(
                            "INSERT INTO data_quality_issues "
                            "(issue_id, fixture_id, category, severity, reason, details, detected_at, "
                            "attempt_count, next_retry_after) "
                            "VALUES (?, ?, 'match_completeness', 'error', ?, ?, ?, ?, ?)",
                            [
                                uuid.uuid4(),
                                fixture_id,
                                "mandatory match data incomplete",
                                json.dumps({"missing": assessment.missing, "source_raw_path": raw_path}),
                                datetime.now(UTC),
                                attempt[0],
                                attempt[1],
                            ],
                        )
                self._save_checkpoint(index + 1, batch_signature, job_run_id)
        self._save_checkpoint(0, batch_signature, job_run_id)
        return DetailedIngestionResult(True, received, eligible, quarantined, 0)

    def _save_checkpoint(self, index: int, signature: str, job_run_id: str | None) -> None:
        checkpoints.put(
            self.connection,
            self.checkpoint_key,
            {"index": index, "signature": signature},
            job_run_id,
        )

    def _record_repair_attempt(self, fixture_id: str, missing: tuple[str, ...]) -> tuple[int, datetime]:
        row = self.connection.execute(
            "SELECT attempt_count FROM fixture_repair_state WHERE fixture_id=?",
            [fixture_id],
        ).fetchone()
        attempt_count = (int(row[0]) if row else 0) + 1
        observed = datetime.now(UTC)
        next_retry = observed + timedelta(hours=min(24, 2 ** (attempt_count - 1)))
        self.connection.execute(
            "INSERT INTO fixture_repair_state VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (fixture_id) DO UPDATE SET attempt_count=excluded.attempt_count, "
            "last_attempt_at=excluded.last_attempt_at, next_retry_after=excluded.next_retry_after, "
            "last_missing=excluded.last_missing",
            [fixture_id, attempt_count, observed, next_retry, json.dumps(missing)],
        )
        return attempt_count, next_retry

    def _repair_missing_components(
        self,
        payload: dict[str, object],
        missing: tuple[str, ...],
        *,
        job_run_id: str | None,
    ) -> dict[str, object]:
        fixture = payload.get("fixture")
        if not isinstance(fixture, dict) or fixture.get("id") is None:
            return payload
        provider_fixture_id = int(fixture["id"])
        repairs: list[tuple[str, Endpoint, str]] = []
        if any(name in missing for name in ("events", "goalscorers", "assists", "cards", "substitutions")):
            repairs.append(("events", Endpoint.EVENTS, "events"))
        if any(name in missing for name in ("home_lineup", "away_lineup", "home_bench", "away_bench")):
            repairs.append(("lineups", Endpoint.LINEUPS, "lineups"))
        if any(name in missing for name in ("home_team_stats", "away_team_stats")):
            repairs.append(("statistics", Endpoint.STATISTICS, "statistics"))
        if any(name in missing for name in ("home_player_stats", "away_player_stats")):
            repairs.append(("players", Endpoint.PLAYERS, "players"))
        repaired = dict(payload)
        for field, endpoint, suffix in repairs:
            purpose = f"detailed_match_repair:{provider_fixture_id}:{suffix}"
            try:
                repaired[field] = self.provider.get(
                    endpoint,
                    {"fixture": provider_fixture_id},
                    purpose=purpose,
                    priority=Priority.P3,
                    job_run_id=job_run_id,
                )
            except ProviderError:
                continue
        return repaired

    def _quarantine(self, payload: dict[str, object], missing: tuple[str, ...], raw_path: str) -> Path:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        fixture = payload.get("fixture")
        provider_id = fixture.get("id") if isinstance(fixture, dict) else "unknown"
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        path = self.quarantine_dir / f"fixture_{provider_id}_{digest[:12]}.json"
        if not path.exists():
            path.write_text(
                json.dumps(
                    {"missing": missing, "source_raw_path": raw_path, "payload": payload},
                    indent=2,
                    sort_keys=True,
                    default=str,
                ),
                encoding="utf-8",
            )
        return path
