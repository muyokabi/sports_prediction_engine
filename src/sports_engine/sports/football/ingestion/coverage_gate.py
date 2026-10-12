from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import duckdb

from sports_engine.core.enums import Priority
from sports_engine.core.exceptions import QuotaExhaustedError
from sports_engine.providers.api_football.coverage import CoverageDecision, assess_coverage
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.providers.base import SportsDataProvider
from sports_engine.warehouse import checkpoints
from sports_engine.warehouse.repositories.leagues import upsert_competition_season
from sports_engine.warehouse.repositories.request_log import latest_raw_path
from sports_engine.warehouse.transactions import transaction


def evaluate_season(season_payload: dict[str, Any]) -> CoverageDecision:
    return assess_coverage(season_payload.get("coverage") or {})


@dataclass(frozen=True, slots=True)
class CoverageAuditItem:
    provider_id: int
    name: str
    season: int | None
    accepted: bool
    reason: str
    replay_eligible: bool = False


@dataclass(frozen=True, slots=True)
class CoverageAuditResult:
    items: tuple[CoverageAuditItem, ...]
    complete: bool
    next_candidate_index: int


@dataclass(frozen=True, slots=True)
class SeasonCatalogResult:
    """Selected provider seasons registered from one API-Football catalog call."""

    items: tuple[CoverageAuditItem, ...]
    provider_seasons: tuple[int, ...]
    competition_seasons_registered: int


class SeasonCatalogService:
    """Register selected current or historical league-seasons quota-efficiently.

    API-Football's leagues catalog already contains every season and its
    season-specific coverage.  Fetch it once and filter locally instead of
    spending one request per league-season.
    """

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

    def run(
        self,
        candidates: list[dict[str, Any]],
        *,
        current: bool = False,
        exact_season: int | None = None,
        past_seasons: int | None = None,
        job_run_id: str | None = None,
    ) -> SeasonCatalogResult:
        selectors = sum((current, exact_season is not None, past_seasons is not None))
        if selectors != 1:
            raise ValueError("Select exactly one of current, exact_season, or past_seasons")
        if past_seasons is not None and past_seasons < 1:
            raise ValueError("past_seasons must be positive")

        mode = "current" if current else "historical"
        purpose = f"selected_season_catalog:{mode}"
        rows = self.provider.get(
            Endpoint.LEAGUES,
            {"current": "true" if current else "false"},
            purpose=purpose,
            priority=Priority.P4,
            job_run_id=job_run_id,
        )
        raw_path = self.raw_path_resolver(purpose, job_run_id)
        catalog: dict[int, dict[str, Any]] = {}
        for row in rows:
            league_id = (row.get("league") or {}).get("id")
            if league_id is not None:
                catalog[int(league_id)] = row
        items: list[CoverageAuditItem] = []
        registered = 0
        selected_years: set[int] = set()
        for candidate in candidates:
            provider_id = int(candidate["provider_id"])
            payload = catalog.get(provider_id)
            if payload is None:
                items.append(CoverageAuditItem(provider_id, str(candidate["name"]), None, False, "league not returned"))
                continue
            league = payload.get("league") or {}
            seasons = list(payload.get("seasons") or [])
            if current:
                selected = [season for season in seasons if season.get("current")]
            elif exact_season is not None:
                selected = [season for season in seasons if season.get("year") == exact_season]
            else:
                completed = [season for season in seasons if not season.get("current")]
                selected = sorted(completed, key=lambda season: int(season["year"]), reverse=True)[:past_seasons]
            if not selected:
                requested = "current season" if current else exact_season or f"last {past_seasons} completed seasons"
                items.append(
                    CoverageAuditItem(
                        provider_id,
                        str(candidate["name"]),
                        None,
                        False,
                        f"{requested} not returned",
                    )
                )
                continue
            for season in selected:
                decision = evaluate_season(season)
                fixture_coverage = decision.profile.fixtures
                replay_eligible = not current and all(
                    (
                        fixture_coverage.events,
                        fixture_coverage.lineups,
                        fixture_coverage.statistics_fixtures,
                        fixture_coverage.statistics_players,
                    )
                )
                reason = "mandatory coverage present" if decision.accepted else ", ".join(decision.reasons)
                if replay_eligible and not decision.accepted:
                    reason = f"replay-only match data eligible; production gate rejected: {reason}"
                with transaction(self.connection):
                    upsert_competition_season(
                        self.connection,
                        league,
                        season,
                        admitted=decision.accepted,
                        reason=reason,
                        priority=candidate.get("priority"),
                        source_raw_path=raw_path,
                        ledger_mode="production" if current else "replay",
                        replay_eligible=replay_eligible,
                    )
                year = int(season["year"])
                selected_years.add(year)
                registered += 1
                items.append(
                    CoverageAuditItem(
                        provider_id,
                        str(candidate["name"]),
                        year,
                        decision.accepted,
                        reason,
                        replay_eligible,
                    )
                )
        return SeasonCatalogResult(tuple(items), tuple(sorted(selected_years, reverse=True)), registered)


class CoverageAuditService:
    checkpoint_key = "football.coverage_audit.next_candidate_index"

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

    def run(
        self,
        candidates: list[dict[str, Any]],
        *,
        job_run_id: str | None = None,
        ledger_mode: str = "production",
        replay_season: int | None = None,
    ) -> CoverageAuditResult:
        if ledger_mode == "replay" and replay_season is None:
            raise ValueError("replay_season is required for replay coverage audits")
        checkpoint_key = (
            self.checkpoint_key
            if ledger_mode == "production"
            else f"{self.checkpoint_key}.{ledger_mode}.{replay_season}"
        )
        saved_index = checkpoints.get(self.connection, checkpoint_key)
        start_index = int(saved_index) if saved_index is not None else 0
        if start_index < 0 or start_index >= len(candidates):
            start_index = 0
        items: list[CoverageAuditItem] = []
        for index in range(start_index, len(candidates)):
            candidate = candidates[index]
            purpose = f"coverage_audit:{ledger_mode}:{replay_season or 'current'}:{candidate['provider_id']}"
            parameters = {"id": candidate["provider_id"], "current": "true"}
            if ledger_mode == "replay":
                parameters = {"id": candidate["provider_id"], "season": replay_season}
            try:
                rows = self.provider.get(
                    Endpoint.LEAGUES,
                    parameters,
                    purpose=purpose,
                    priority=Priority.P4,
                    job_run_id=job_run_id,
                )
            except QuotaExhaustedError:
                checkpoints.put(self.connection, checkpoint_key, index, job_run_id)
                return CoverageAuditResult(tuple(items), False, index)
            if not rows:
                items.append(
                    CoverageAuditItem(
                        candidate["provider_id"],
                        candidate["name"],
                        None,
                        False,
                        "no current season returned",
                    )
                )
                checkpoints.put(self.connection, checkpoint_key, index + 1, job_run_id)
                continue
            country = rows[0].get("country") or {}
            league = {
                **rows[0]["league"],
                "country": country.get("name") or rows[0]["league"].get("country"),
            }
            seasons = [
                season
                for season in rows[0].get("seasons", [])
                if (season.get("current") if ledger_mode == "production" else season.get("year") == replay_season)
            ]
            if not seasons:
                items.append(
                    CoverageAuditItem(
                        candidate["provider_id"],
                        candidate["name"],
                        None,
                        False,
                        "requested season not returned",
                    )
                )
                checkpoints.put(self.connection, checkpoint_key, index + 1, job_run_id)
                continue
            season = seasons[-1]
            decision = evaluate_season(season)
            fixture_coverage = decision.profile.fixtures
            replay_eligible = ledger_mode == "replay" and all(
                (
                    fixture_coverage.events,
                    fixture_coverage.lineups,
                    fixture_coverage.statistics_fixtures,
                    fixture_coverage.statistics_players,
                )
            )
            reason = "mandatory coverage present" if decision.accepted else ", ".join(decision.reasons)
            if replay_eligible and not decision.accepted:
                reason = f"replay-only match data eligible; production gate rejected: {reason}"
            raw_path = self.raw_path_resolver(purpose, job_run_id)
            with transaction(self.connection):
                upsert_competition_season(
                    self.connection,
                    league,
                    season,
                    admitted=decision.accepted,
                    reason=reason,
                    priority=candidate.get("priority"),
                    source_raw_path=raw_path,
                    ledger_mode=ledger_mode,
                    replay_eligible=replay_eligible,
                )
                checkpoints.put(self.connection, checkpoint_key, index + 1, job_run_id)
            items.append(
                CoverageAuditItem(
                    candidate["provider_id"],
                    candidate["name"],
                    season["year"],
                    decision.accepted,
                    reason,
                    replay_eligible,
                )
            )
        checkpoints.put(self.connection, checkpoint_key, 0, job_run_id)
        return CoverageAuditResult(tuple(items), True, 0)
