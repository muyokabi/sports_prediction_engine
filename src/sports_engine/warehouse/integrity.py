import hashlib
from dataclasses import dataclass
from pathlib import Path

import duckdb

from sports_engine.sports.football.quality.completeness import REQUIRED_COMPONENTS


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    check: str
    count: int
    severity: str = "error"


def audit_integrity(
    connection: duckdb.DuckDBPyConnection,
    artifact_root: Path | None = None,
) -> list[IntegrityIssue]:
    required_components = ",".join(f"'{component}'" for component in REQUIRED_COMPONENTS)
    required_count = len(REQUIRED_COMPONENTS)
    role_event_table = connection.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema='main' AND table_name='model_market_role_events'"
    ).fetchone()
    has_role_events = bool(role_event_table and role_event_table[0])
    role_state_query = (
        "(SELECT state FROM model_market_role_events r "
        "WHERE r.model_version=p.fundamental_model_version AND r.market_family=o.canonical_market "
        "AND r.role_name=o.canonical_market || '_CHAMPION' AND r.occurred_at<=o.created_at "
        "ORDER BY occurred_at DESC LIMIT 1)"
        if has_role_events
        else "(SELECT state FROM model_market_roles r "
        "WHERE r.model_version=p.fundamental_model_version AND r.market_family=o.canonical_market "
        "AND r.role_name=o.canonical_market || '_CHAMPION' ORDER BY selected_at DESC LIMIT 1)"
    )
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
        "invalid_engine_probability_components": (
            "SELECT count(*) FROM engine_probability_prices WHERE probability IS NULL "
            "OR full_win_probability IS NULL OR half_win_probability IS NULL OR push_probability IS NULL "
            "OR half_loss_probability IS NULL OR full_loss_probability IS NULL OR fair_decimal_odds IS NULL "
            "OR expected_home_goals IS NULL OR expected_away_goals IS NULL "
            "OR probability NOT BETWEEN 0 AND 1 OR full_win_probability NOT BETWEEN 0 AND 1 "
            "OR half_win_probability NOT BETWEEN 0 AND 1 OR push_probability NOT BETWEEN 0 AND 1 "
            "OR half_loss_probability NOT BETWEEN 0 AND 1 OR full_loss_probability NOT BETWEEN 0 AND 1 "
            "OR abs(full_win_probability+half_win_probability+push_probability+half_loss_probability+"
            "full_loss_probability-1)>0.000001 OR fair_decimal_odds<=1 "
            "OR expected_home_goals<0 OR expected_away_goals<0"
        ),
        "invalid_match_odds_probability_sum": (
            "SELECT count(*) FROM (SELECT prediction_id, engine, sum(probability) probability_sum, "
            "count(*) row_count "
            "FROM engine_probability_prices WHERE canonical_market='MATCH_ODDS' GROUP BY prediction_id, engine "
            "HAVING row_count<>3 OR abs(probability_sum-1)>0.000001)"
        ),
        "invalid_institutional_prediction_time": (
            "SELECT count(*) FROM institutional_predictions WHERE source_cutoff>analysis_timestamp "
            "OR analysis_timestamp>=target_kickoff"
        ),
        "post_kickoff_reference_quotes": (
            "SELECT count(*) FROM market_reference_quotes WHERE reference_state='POST_KICKOFF_INVALID' "
            "OR collected_at>=kickoff_timestamp "
            "OR (provider_update_timestamp IS NOT NULL AND provider_update_timestamp>=kickoff_timestamp)"
        ),
        "unqualified_production_opportunities": (
            "SELECT count(*) FROM institutional_opportunities o "
            "JOIN institutional_predictions p USING (prediction_id) "
            "JOIN fixtures f ON f.fixture_id=p.target_fixture_id "
            "JOIN competition_seasons cs USING (competition_season_id) "
            "LEFT JOIN prediction_applicability a USING (prediction_id) "
            "LEFT JOIN model_runs mr ON mr.version=p.fundamental_model_version "
            "WHERE o.governance_state='PRODUCTION_ACTIONABLE' AND ("
            "o.decision<>'BET_IF_PRICE_AVAILABLE' OR o.robust_estimated_edge IS NULL "
            "OR o.robust_estimated_edge<0 OR a.actionability_qualified IS DISTINCT FROM true "
            "OR mr.evidence_state<>'PRODUCTION_ACTIONABLE' "
            "OR coalesce((SELECT state FROM calibration_validations cv "
            "WHERE cv.model_version=p.fundamental_model_version AND cv.market_family=o.canonical_market "
            "AND cv.validated_at<=o.created_at "
            "ORDER BY validated_at DESC LIMIT 1), '')<>'CALIBRATION_VALIDATED' "
            f"OR coalesce({role_state_query}, '')<>'CHAMPION' "
            "OR coalesce((SELECT state FROM model_probability_scope_validations s "
            "WHERE s.model_version=p.fundamental_model_version AND s.market_family=o.canonical_market "
            "AND s.scope_type='COMPETITION' AND s.scope_key=CAST(cs.competition_id AS VARCHAR) "
            "AND s.validated_at<=o.created_at "
            "ORDER BY validated_at DESC LIMIT 1), '')<>'VALIDATED')"
        ),
        "impossible_scores": (
            "SELECT count(*) FROM fixtures_current WHERE home_goals<0 OR away_goals<0 "
            "OR (status_short IN ('FT','AET','PEN') "
            "AND (home_goals IS NULL OR away_goals IS NULL))"
        ),
        "inconsistent_ml_eligibility": (
            "SELECT count(*) FROM fixture_quality_status q WHERE q.eligibility='ML_ELIGIBLE' "
            "AND (EXISTS (SELECT 1 FROM fixture_completeness fc WHERE fc.fixture_id=q.fixture_id "
            f"AND fc.component IN ({required_components}) AND fc.state<>'complete') "
            "OR (SELECT count(*) FROM fixture_completeness fc WHERE fc.fixture_id=q.fixture_id "
            f"AND fc.component IN ({required_components}) AND fc.state='complete')<>{required_count})"
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
