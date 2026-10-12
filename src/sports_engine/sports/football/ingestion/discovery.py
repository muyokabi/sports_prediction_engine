import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import duckdb

from sports_engine.core.enums import Priority
from sports_engine.core.ids import canonical_id
from sports_engine.providers.api_football.endpoints import Endpoint
from sports_engine.providers.base import SportsDataProvider
from sports_engine.warehouse.repositories.leagues import upsert_competition_season
from sports_engine.warehouse.repositories.request_log import latest_raw_path

EXCLUDED_TERMS = frozenset({"friendly", "friendlies", "u17", "u18", "u19", "u20", "u21", "u23", "youth", "reserve"})
DEFAULT_OBSERVATION_COLLECTION_LIMIT = 40


@dataclass(frozen=True, slots=True)
class SuitabilityScore:
    data_quality: float
    market_quality: float
    sample_value: float
    operational_cost: float
    total: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompetitionDiscoveryResult:
    discovered: int
    observation: int
    rejected: int


def backfill_candidate_universe(
    connection: duckdb.DuckDBPyConnection,
    *,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Return a bounded, governed league universe for historical collection.

    Existing admitted leagues retain precedence. The remaining capacity is
    filled by the strongest observation candidates. This expands evidence
    collection without implicitly making a league production-actionable.
    """
    if limit < 1:
        raise ValueError("limit must be positive")
    rows = connection.execute(
        "SELECT provider_competition_id, name, country "
        "FROM competition_discoveries cd "
        "JOIN competition_seasons cs USING (competition_season_id) "
        "WHERE cd.universe_state IN ('ACTIONABLE', 'OBSERVATION') "
        "ORDER BY cs.admitted DESC, cd.suitability_score DESC, "
        "cd.data_quality_score DESC, cd.market_quality_score DESC, cd.name "
        "LIMIT ?",
        [limit],
    ).fetchall()
    return [
        {
            "provider_id": int(provider_id),
            "name": str(name),
            "country": str(country) if country is not None else None,
            "priority": rank,
        }
        for rank, (provider_id, name, country) in enumerate(rows, start=1)
    ]


def score_competition(league: dict[str, Any], season: dict[str, Any]) -> SuitabilityScore:
    coverage = season.get("coverage") or {}
    fixtures = coverage.get("fixtures") or {}
    flags = [
        fixtures.get("events"),
        fixtures.get("lineups"),
        fixtures.get("statistics_fixtures"),
        fixtures.get("statistics_players"),
        coverage.get("players"),
    ]
    data_quality = sum(bool(value) for value in flags) / len(flags)
    market_quality = 1.0 if coverage.get("odds") else 0.0
    sample_value = 0.7 if str(league.get("type", "")).casefold() == "league" else 0.4
    operational_cost = 0.8 if data_quality == 1.0 else 0.5
    searchable = f"{league.get('name', '')} {league.get('type', '')}".casefold()
    reasons = tuple(sorted(term for term in EXCLUDED_TERMS if term in searchable))
    total = 0.45 * data_quality + 0.30 * market_quality + 0.15 * sample_value + 0.10 * operational_cost
    if reasons:
        total = 0.0
    return SuitabilityScore(data_quality, market_quality, sample_value, operational_cost, total, reasons)


class CompetitionDiscoveryService:
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

    def run(self, *, job_run_id: str | None = None) -> CompetitionDiscoveryResult:
        purpose = "competition_discovery:current"
        payloads = self.provider.get(
            Endpoint.LEAGUES,
            {"current": "true"},
            purpose=purpose,
            priority=Priority.P4,
            job_run_id=job_run_id,
        )
        raw_path = self.raw_path_resolver(purpose, job_run_id)
        discovered = observation = rejected = 0
        for payload in payloads:
            league = payload.get("league") or {}
            country = payload.get("country") or {}
            seasons = [item for item in payload.get("seasons", []) if item.get("current")]
            if not league.get("id") or not seasons:
                continue
            season = seasons[-1]
            score = score_competition(league, season)
            qualifies = score.total >= 0.75 and score.data_quality == 1.0 and score.market_quality == 1.0
            canonical_competition_season_id = canonical_id(
                "competition_season", "api_football", f"{league['id']}:{season['year']}"
            )
            existing = self.connection.execute(
                "SELECT cs.admitted, cs.admission_reason, cs.priority, cd.universe_state "
                "FROM competition_seasons cs LEFT JOIN competition_discoveries cd "
                "USING (competition_season_id) WHERE cs.competition_season_id=?",
                [canonical_competition_season_id],
            ).fetchone()
            already_admitted = bool(existing and existing[0])
            existing_state = str(existing[3] or "ACTIONABLE") if existing is not None else "ACTIONABLE"
            state = (
                existing_state
                if already_admitted
                else "OBSERVATION"
                if qualifies
                else "REJECTED"
                if score.reasons
                else "DISCOVERED"
            )
            competition_season_id = upsert_competition_season(
                self.connection,
                {**league, "country": country.get("name") or league.get("country")},
                season,
                admitted=already_admitted,
                reason=(
                    str(existing[1])
                    if already_admitted and existing is not None
                    else f"automatic discovery: {state.lower()}"
                ),
                priority=(
                    int(existing[2]) if already_admitted and existing is not None and existing[2] is not None else None
                ),
                source_raw_path=raw_path,
                ledger_mode="production",
            )
            now = datetime.now(UTC)
            self.connection.execute(
                "INSERT INTO competition_discoveries VALUES (?, 'api_football', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, "
                "NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (provider, provider_competition_id, provider_season) "
                "DO UPDATE SET competition_season_id=excluded.competition_season_id, name=excluded.name, "
                "country=excluded.country, competition_type=excluded.competition_type, "
                "universe_state=excluded.universe_state, "
                "coverage=excluded.coverage, data_quality_score=excluded.data_quality_score, "
                "market_quality_score=excluded.market_quality_score, sample_value_score=excluded.sample_value_score, "
                "operational_cost_score=excluded.operational_cost_score, suitability_score=excluded.suitability_score, "
                "exclusion_reasons=excluded.exclusion_reasons, "
                "expected_bootstrap_requests=excluded.expected_bootstrap_requests, "
                "source_raw_path=excluded.source_raw_path, discovered_at=excluded.discovered_at",
                [
                    str(uuid.uuid4()),
                    int(league["id"]),
                    int(season["year"]),
                    competition_season_id,
                    str(league.get("name") or f"API-Football {league['id']}"),
                    country.get("name") or league.get("country"),
                    league.get("type"),
                    state,
                    json.dumps(season.get("coverage") or {}),
                    score.data_quality,
                    score.market_quality,
                    score.sample_value,
                    score.operational_cost,
                    score.total,
                    json.dumps(score.reasons),
                    8,
                    raw_path,
                    now,
                ],
            )
            discovered += 1
            observation += state == "OBSERVATION"
            rejected += state == "REJECTED"
        return CompetitionDiscoveryResult(discovered, observation, rejected)


def admit_observation_universe(connection: duckdb.DuckDBPyConnection, *, limit: int) -> list[str]:
    """Fill a bounded observation collection universe, never actionability.

    ``limit`` is the total collection ceiling, not a number to add on every
    invocation. This makes automatic daily admission idempotent.
    """
    if limit < 1:
        raise ValueError("limit must be positive")
    existing_row = connection.execute(
        "SELECT count(*) FROM competition_discoveries cd "
        "JOIN competition_seasons cs USING (competition_season_id) "
        "WHERE cd.universe_state='OBSERVATION' AND cs.admitted"
    ).fetchone()
    remaining = max(0, limit - int(existing_row[0] if existing_row else 0))
    if remaining == 0:
        return []
    rows = connection.execute(
        "SELECT competition_season_id FROM competition_discoveries cd "
        "JOIN competition_seasons cs USING (competition_season_id) "
        "WHERE cd.universe_state='OBSERVATION' AND NOT cs.admitted "
        "ORDER BY cd.suitability_score DESC, cd.data_quality_score DESC, "
        "cd.market_quality_score DESC, cd.name LIMIT ?",
        [remaining],
    ).fetchall()
    admitted = [str(row[0]) for row in rows]
    for rank, competition_season_id in enumerate(admitted, start=1):
        connection.execute(
            "UPDATE competition_seasons SET admitted=true, "
            "admission_reason='automated observation-universe admission', priority=? "
            "WHERE competition_season_id=?",
            [100 + rank, competition_season_id],
        )
    return admitted
