import hashlib
import json
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol

import duckdb

from sports_engine.core.enums import Priority
from sports_engine.core.ids import canonical_id
from sports_engine.providers.api_football.endpoints import Endpoint
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
class InjuryIngestionResult:
    observations_written: int
    ignored_unknown_teams: int


class InjuryIngestionService:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        provider: PaginatedProvider,
        raw_path_resolver: Callable[[str, str | None], str] | None = None,
    ) -> None:
        self.connection = connection
        self.provider = provider
        self.raw_path_resolver = raw_path_resolver or (
            lambda purpose, job_run_id: latest_raw_path(connection, purpose, job_run_id)
        )

    def run(self, target_date: date, *, job_run_id: str | None = None) -> InjuryIngestionResult:
        purpose = f"injuries:{target_date.isoformat()}"
        observed = datetime.now(UTC)
        written = ignored = 0
        for payload in self.provider.get_all_pages(
            Endpoint.INJURIES,
            {"date": target_date.isoformat()},
            purpose=purpose,
            priority=Priority.P2,
            job_run_id=job_run_id,
        ):
            raw_path = self.raw_path_resolver(purpose, job_run_id)
            if self._store(payload, observed, raw_path, job_run_id):
                written += 1
            else:
                ignored += 1
        raw_path = self.raw_path_resolver(purpose, job_run_id)
        self.connection.execute(
            "INSERT INTO injury_collection_runs VALUES (?, ?, ?, ?, true, ?)",
            [uuid.uuid4(), target_date, observed, raw_path or None, job_run_id],
        )
        return InjuryIngestionResult(written, ignored)

    def _store(
        self,
        payload: dict[str, Any],
        observed: datetime,
        raw_path: str,
        job_run_id: str | None,
    ) -> bool:
        team = payload.get("team") or {}
        player = payload.get("player") or {}
        fixture = payload.get("fixture") or {}
        if team.get("id") is None or player.get("id") is None or fixture.get("id") is None:
            return False
        team_id = canonical_id("team", "api_football", int(team["id"]))
        known_team = self.connection.execute("SELECT count(*) FROM teams WHERE team_id=?", [team_id]).fetchone()
        if not known_team or not known_team[0]:
            return False
        player_id = canonical_id("player", "api_football", int(player["id"]))
        fixture_row = self.connection.execute(
            "SELECT fixture_id FROM fixtures WHERE provider_fixture_id=?", [fixture["id"]]
        ).fetchone()
        content_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        observation_id = canonical_id(
            "injury_observation",
            "api_football",
            f"{fixture['id']}:{player['id']}:{observed.isoformat()}:{content_hash}",
        )
        with transaction(self.connection):
            self.connection.execute(
                "INSERT INTO players (player_id, name, updated_at, source_raw_path, retrieved_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT (player_id) DO UPDATE SET name=excluded.name, "
                "updated_at=excluded.updated_at, source_raw_path=excluded.source_raw_path, "
                "retrieved_at=excluded.retrieved_at",
                [player_id, player.get("name") or f"Player {player['id']}", observed, raw_path, observed],
            )
            self.connection.execute(
                "INSERT INTO injury_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    observation_id,
                    fixture["id"],
                    fixture_row[0] if fixture_row else None,
                    team_id,
                    player_id,
                    observed,
                    player.get("type"),
                    player.get("reason"),
                    json.dumps(payload),
                    raw_path,
                    job_run_id,
                ],
            )
        return True
