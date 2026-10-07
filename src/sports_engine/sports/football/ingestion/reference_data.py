from collections.abc import Callable
from dataclasses import dataclass

import duckdb

from sports_engine.core.enums import Priority
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.providers.base import SportsDataProvider
from sports_engine.sports.football.normalization.squads import normalize_squad
from sports_engine.sports.football.normalization.teams import normalize_team
from sports_engine.warehouse.repositories.players import store_squad_snapshot
from sports_engine.warehouse.repositories.request_log import latest_raw_path
from sports_engine.warehouse.repositories.teams import link_competition_season_team, upsert_team
from sports_engine.warehouse.transactions import transaction


@dataclass(frozen=True, slots=True)
class ReferenceSyncResult:
    teams_written: int = 0
    squad_snapshots_written: int = 0
    players_written: int = 0


class ReferenceDataService:
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

    def sync_teams(
        self,
        *,
        competition_season_id: str,
        provider_league_id: int,
        provider_season: int,
        job_run_id: str | None = None,
    ) -> ReferenceSyncResult:
        purpose = f"team_reference:{provider_league_id}:{provider_season}"
        rows = self.provider.get(
            Endpoint.TEAMS,
            {"league": provider_league_id, "season": provider_season},
            purpose=purpose,
            priority=Priority.P4,
            job_run_id=job_run_id,
        )
        raw_path = self.raw_path_resolver(purpose, job_run_id)
        with transaction(self.connection):
            for payload in rows:
                team_id = upsert_team(
                    self.connection,
                    normalize_team(payload),
                    source_raw_path=raw_path,
                )
                link_competition_season_team(
                    self.connection,
                    competition_season_id=competition_season_id,
                    team_id=team_id,
                    source_raw_path=raw_path,
                )
        return ReferenceSyncResult(teams_written=len(rows))

    def sync_squad(
        self,
        *,
        competition_season_id: str,
        provider_team_id: int,
        job_run_id: str | None = None,
    ) -> ReferenceSyncResult:
        purpose = f"squad_reference:{provider_team_id}"
        rows = self.provider.get(
            Endpoint.SQUADS,
            {"team": provider_team_id},
            purpose=purpose,
            priority=Priority.P5,
            job_run_id=job_run_id,
        )
        if not rows:
            return ReferenceSyncResult()
        returned_team_id, players = normalize_squad(rows[0])
        if returned_team_id != provider_team_id:
            raise ValueError(f"Squad response team {returned_team_id} does not match requested team {provider_team_id}")
        raw_path = self.raw_path_resolver(purpose, job_run_id)
        with transaction(self.connection):
            store_squad_snapshot(
                self.connection,
                competition_season_id=competition_season_id,
                provider_team_id=provider_team_id,
                players=players,
                source_raw_path=raw_path,
            )
        return ReferenceSyncResult(squad_snapshots_written=1, players_written=len(players))
