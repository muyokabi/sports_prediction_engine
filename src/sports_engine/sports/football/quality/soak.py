import json
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from sports_engine.providers.base import SportsDataProvider
from sports_engine.sports.football.ingestion.detailed_matches import DetailedMatchIngestionService
from sports_engine.sports.football.quality.completeness import REQUIRED_COMPONENTS


@dataclass(frozen=True, slots=True)
class LeagueSoakResult:
    competition: str
    season: int
    fixtures_sampled: int
    fixtures_assessed: int
    fixtures_unassessed: int
    fully_complete: int
    ml_eligible: int
    quarantined: int
    component_availability: dict[str, int]
    missing_components: dict[str, int]
    provider_nulls: dict[str, int]
    repairs_attempted: int
    repairs_succeeded: int
    repair_success_rate: float


@dataclass(frozen=True, slots=True)
class SoakResult:
    run_id: str
    fixtures_sampled: int
    fixtures_assessed: int
    fixtures_unassessed: int
    fully_complete: int
    ml_eligible: int
    quarantined: int
    component_availability: dict[str, int]
    missing_components: dict[str, int]
    provider_nulls: dict[str, int]
    repairs_attempted: int
    repairs_succeeded: int
    repair_success_rate: float
    leagues: tuple[LeagueSoakResult, ...]
    report_path: Path


class CompletenessSoakService:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        provider: SportsDataProvider,
        quarantine_dir: Path,
        report_dir: Path,
        raw_path_resolver: Callable[[str, str | None], str] | None = None,
    ) -> None:
        self.connection = connection
        self.provider = provider
        self.quarantine_dir = quarantine_dir
        self.report_dir = report_dir
        self.raw_path_resolver = raw_path_resolver

    def run(
        self,
        *,
        ledger_mode: str,
        league_limit: int,
        fixtures_per_league: int,
        repair_attempt_limit: int,
        job_run_id: str | None,
    ) -> SoakResult:
        candidates = self.connection.execute(
            "WITH date_ranked AS (SELECT c.name competition, cs.provider_season, cs.priority, "
            "cs.competition_season_id, f.provider_fixture_id, f.kickoff_utc, "
            "coalesce(r.attempt_count,0) attempts, row_number() OVER (PARTITION BY cs.competition_season_id, "
            "CAST(f.kickoff_utc AS DATE) ORDER BY coalesce(r.attempt_count,0), f.kickoff_utc DESC) date_position "
            "FROM fixtures_current f JOIN competition_seasons cs USING (competition_season_id) "
            "JOIN competitions c USING (competition_id) LEFT JOIN fixture_quality_status q USING (fixture_id) "
            "LEFT JOIN fixture_repair_state r USING (fixture_id) WHERE cs.ledger_mode=? "
            "AND f.status_short IN ('FT','AET','PEN') AND coalesce(q.eligibility,'PENDING_REPAIR')<>'ML_ELIGIBLE' "
            "AND coalesce(r.attempt_count,0)<?), ranked AS (SELECT *, row_number() OVER (PARTITION BY "
            "competition_season_id ORDER BY attempts, hash(provider_fixture_id)) row_position, "
            "dense_rank() OVER (ORDER BY priority, competition) league_rank FROM date_ranked WHERE date_position=1) "
            "SELECT competition, provider_season, provider_fixture_id, attempts "
            "FROM ranked WHERE row_position<=? AND league_rank<=? ORDER BY league_rank, row_position",
            [ledger_mode, repair_attempt_limit, fixtures_per_league, league_limit],
        ).fetchall()
        if not candidates:
            raise ValueError("No completed fixtures are available for the requested soak sample")
        fixture_ids = [int(row[2]) for row in candidates]
        DetailedMatchIngestionService(
            self.connection,
            self.provider,
            self.quarantine_dir,
            raw_path_resolver=self.raw_path_resolver,
        ).run(fixture_ids, job_run_id=job_run_id)
        leagues = []
        for competition, season in sorted({(str(row[0]), int(row[1])) for row in candidates}):
            selected = [row for row in candidates if row[0] == competition and row[1] == season]
            ids = [int(row[2]) for row in selected]
            placeholders = ",".join("?" for _ in ids)
            states = self.connection.execute(
                f"SELECT fc.component, fc.state, count(*) FROM fixture_completeness fc "
                f"JOIN fixtures f USING (fixture_id) WHERE f.provider_fixture_id IN ({placeholders}) "
                "GROUP BY fc.component, fc.state",
                ids,
            ).fetchall()
            availability = {
                component: sum(
                    int(count) for value, state, count in states if value == component and state == "complete"
                )
                for component in REQUIRED_COMPONENTS
            }
            missing = {str(component): int(count) for component, state, count in states if state != "complete"}
            eligible_row = self.connection.execute(
                f"SELECT count(*) FILTER (WHERE q.eligibility='ML_ELIGIBLE'), count(q.fixture_id) "
                f"FROM fixtures f LEFT JOIN fixture_quality_status q USING (fixture_id) "
                f"WHERE f.provider_fixture_id IN ({placeholders})",
                ids,
            ).fetchone()
            nulls = self._provider_nulls(ids)
            eligible = int(eligible_row[0]) if eligible_row else 0
            assessed = int(eligible_row[1]) if eligible_row else 0
            repair_row = self.connection.execute(
                f"SELECT count(*) FILTER (WHERE r.attempt_count>0), "
                f"count(*) FILTER (WHERE r.attempt_count>0 AND q.eligibility='ML_ELIGIBLE') "
                f"FROM fixtures f LEFT JOIN fixture_repair_state r USING (fixture_id) "
                f"LEFT JOIN fixture_quality_status q USING (fixture_id) "
                f"WHERE f.provider_fixture_id IN ({placeholders})",
                ids,
            ).fetchone()
            repairs = int(repair_row[0]) if repair_row else 0
            repairs_succeeded = int(repair_row[1]) if repair_row else 0
            leagues.append(
                LeagueSoakResult(
                    competition=competition,
                    season=season,
                    fixtures_sampled=len(ids),
                    fixtures_assessed=assessed,
                    fixtures_unassessed=len(ids) - assessed,
                    fully_complete=eligible,
                    ml_eligible=eligible,
                    quarantined=assessed - eligible,
                    component_availability=availability,
                    missing_components=missing,
                    provider_nulls=nulls,
                    repairs_attempted=repairs,
                    repairs_succeeded=repairs_succeeded,
                    repair_success_rate=repairs_succeeded / repairs if repairs else 0.0,
                )
            )
        run_id = str(uuid.uuid4())
        self.report_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.report_dir / f"completeness-soak-{run_id}.json"
        repairs = sum(item.repairs_attempted for item in leagues)
        repaired = sum(item.repairs_succeeded for item in leagues)
        result = SoakResult(
            run_id=run_id,
            fixtures_sampled=len(fixture_ids),
            fixtures_assessed=sum(item.fixtures_assessed for item in leagues),
            fixtures_unassessed=sum(item.fixtures_unassessed for item in leagues),
            fully_complete=sum(item.fully_complete for item in leagues),
            ml_eligible=sum(item.ml_eligible for item in leagues),
            quarantined=sum(item.quarantined for item in leagues),
            component_availability=self._sum_metrics(leagues, "component_availability"),
            missing_components=self._sum_metrics(leagues, "missing_components"),
            provider_nulls=self._sum_metrics(leagues, "provider_nulls"),
            repairs_attempted=repairs,
            repairs_succeeded=repaired,
            repair_success_rate=repaired / repairs if repairs else 0.0,
            leagues=tuple(leagues),
            report_path=report_path,
        )
        report_path.write_text(
            json.dumps({**asdict(result), "observed_at": datetime.now(UTC)}, indent=2, default=str),
            encoding="utf-8",
        )
        return result

    @staticmethod
    def _sum_metrics(leagues: list[LeagueSoakResult], field: str) -> dict[str, int]:
        keys = {key for league in leagues for key in getattr(league, field)}
        return {key: sum(getattr(league, field).get(key, 0) for league in leagues) for key in sorted(keys)}

    def _provider_nulls(self, provider_fixture_ids: list[int]) -> dict[str, int]:
        placeholders = ",".join("?" for _ in provider_fixture_ids)
        fields = {
            "shots": "total_shots",
            "shots_on_target": "shots_on_goal",
            "corners": "corner_kicks",
            "possession": "ball_possession",
            "passes": "total_passes",
            "fouls": "fouls",
            "offsides": "offsides",
        }
        result: dict[str, int] = {}
        for label, column in fields.items():
            row = self.connection.execute(
                f"SELECT count(DISTINCT f.fixture_id) FROM fixtures f "
                f"JOIN team_match_statistics s USING (fixture_id) "
                f"WHERE f.provider_fixture_id IN ({placeholders}) AND s.{column} IS NULL",
                provider_fixture_ids,
            ).fetchone()
            result[label] = int(row[0]) if row else 0
        player_fields = {
            "player_minutes": "minutes",
            "player_ratings": "rating",
            "player_shots": "shots_total",
            "player_passes": "passes_total",
            "player_tackles": "tackles_total",
            "player_interceptions": "interceptions",
            "player_duels": "duels_total",
        }
        for label, column in player_fields.items():
            row = self.connection.execute(
                f"SELECT count(DISTINCT f.fixture_id) FROM fixtures f "
                f"JOIN player_match_statistics s USING (fixture_id) "
                f"WHERE f.provider_fixture_id IN ({placeholders}) AND s.{column} IS NULL",
                provider_fixture_ids,
            ).fetchone()
            result[label] = int(row[0]) if row else 0
        return result
