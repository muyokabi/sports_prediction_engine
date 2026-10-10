import hashlib
from dataclasses import dataclass
from pathlib import Path

import duckdb


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    check: str
    count: int
    severity: str = "error"


def audit_integrity(
    connection: duckdb.DuckDBPyConnection,
    artifact_root: Path | None = None,
) -> list[IntegrityIssue]:
    checks = {
        "orphan_fixtures": (
            "SELECT count(*) FROM fixtures f LEFT JOIN competition_seasons cs "
            "USING (competition_season_id) WHERE cs.competition_season_id IS NULL"
        ),
        "orphan_fixture_teams": (
            "SELECT count(*) FROM fixture_team ft LEFT JOIN teams t USING (team_id) WHERE t.team_id IS NULL"
        ),
        "orphan_player_statistics": (
            "SELECT count(*) FROM player_match_statistics p LEFT JOIN fixtures f USING (fixture_id) "
            "LEFT JOIN teams t USING (team_id) LEFT JOIN players pl USING (player_id) "
            "WHERE f.fixture_id IS NULL OR t.team_id IS NULL OR pl.player_id IS NULL"
        ),
        "orphan_odds": (
            "SELECT count(*) FROM odds_snapshots o LEFT JOIN fixtures f USING (fixture_id) WHERE f.fixture_id IS NULL"
        ),
        "duplicate_provider_mappings": (
            "SELECT count(*) FROM (SELECT provider_id, entity_type, provider_entity_id "
            "FROM provider_entity_map GROUP BY ALL HAVING count(*)>1)"
        ),
        "duplicate_provider_fixtures": (
            "SELECT count(*) FROM (SELECT provider_fixture_id FROM fixtures GROUP BY ALL HAVING count(*)>1)"
        ),
        "home_equals_away": "SELECT count(*) FROM fixtures WHERE home_team_id=away_team_id",
        "invalid_prediction_probabilities": (
            "SELECT count(*) FROM predictions WHERE probability_home NOT BETWEEN 0 AND 1 "
            "OR probability_draw NOT BETWEEN 0 AND 1 OR probability_away NOT BETWEEN 0 AND 1 "
            "OR abs(probability_home+probability_draw+probability_away-1)>0.000001"
        ),
        "impossible_scores": (
            "SELECT count(*) FROM fixtures_current WHERE home_goals<0 OR away_goals<0 "
            "OR (status_short IN ('FT','AET','PEN') "
            "AND (home_goals IS NULL OR away_goals IS NULL))"
        ),
        "inconsistent_ml_eligibility": (
            "SELECT count(*) FROM fixture_quality_status q WHERE q.eligibility='ML_ELIGIBLE' "
            "AND EXISTS (SELECT 1 FROM fixture_completeness fc WHERE fc.fixture_id=q.fixture_id "
            "AND fc.state<>'complete')"
        ),
        "unresolved_prediction_models": (
            "SELECT count(*) FROM prediction_runs pr LEFT JOIN model_runs mr "
            "ON mr.version=pr.model_version WHERE mr.model_run_id IS NULL"
        ),
        "duplicate_market_champions": (
            "SELECT count(*) FROM (SELECT market_family, role_name FROM model_market_roles "
            "WHERE state='CHAMPION' GROUP BY ALL HAVING count(*)>1)"
        ),
        "invalid_market_champion_status": (
            "SELECT count(*) FROM model_market_roles r LEFT JOIN model_runs mr ON mr.version=r.model_version "
            "WHERE r.state='CHAMPION' AND (mr.model_run_id IS NULL OR mr.status<>'champion')"
        ),
    }
    issues = []
    for name, sql in checks.items():
        row = connection.execute(sql).fetchone()
        count = int(row[0]) if row else 0
        if count:
            issues.append(IntegrityIssue(name, count))
    for path_value, expected in connection.execute(
        "SELECT parquet_path, dataset_hash FROM feature_datasets"
    ).fetchall():
        path = Path(path_value)
        if not path.is_absolute() and artifact_root is not None:
            path = artifact_root / path
        if not path.is_file():
            issues.append(IntegrityIssue("missing_feature_dataset", 1))
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            issues.append(IntegrityIssue("feature_dataset_hash_mismatch", 1))
    return issues
