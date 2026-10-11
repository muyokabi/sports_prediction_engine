from dataclasses import dataclass
from datetime import UTC, datetime
from math import exp, log
from typing import Any

import duckdb

from sports_engine.models.statistical.poisson import PoissonModel

FINAL_STATUSES = ("FT", "AET", "PEN")


@dataclass(frozen=True, slots=True)
class TeamEvidence:
    observations: int
    effective_observations: float
    home_observations: int
    away_observations: int
    last_observation: datetime | None
    in_training_universe: bool
    prior_fraction: float


@dataclass(frozen=True, slots=True)
class ApplicabilityAssessment:
    state: str
    level: str
    actionability_qualified: bool
    reasons: tuple[str, ...]
    home: TeamEvidence
    away: TeamEvidence
    competition_observations: int
    competition_in_training_universe: bool
    competition_state: str
    home_attack: float
    home_defence: float
    away_attack: float
    away_defence: float
    competition_baseline: float
    home_advantage: float
    parameter_states: dict[str, str]
    expected_home_goals: float
    expected_away_goals: float
    probabilities: dict[str, float]
    policy_version: str | None


def assess_score_model_applicability(
    connection: duckdb.DuckDBPyConnection,
    *,
    fixture_id: str,
    home_team_id: str,
    away_team_id: str,
    model: PoissonModel,
    model_type: str,
    model_metrics: dict[str, Any],
    training_cutoff: datetime | None,
    half_life_days: float,
    probabilities: dict[str, float],
) -> ApplicabilityAssessment:
    """Explain exactly which fitted or prior terms produced a score-model price.

    Actionability is deliberately fail-closed. A team-history threshold is used only
    when a chronologically validated, model-specific applicability policy is embedded
    in the model metrics. Merely being present in the fitted dictionary is not enough.
    """
    cutoff = training_cutoff or datetime.max.replace(tzinfo=UTC)
    lineage_available = bool(getattr(model, "fitted_fixture_ids", ()))
    home = _team_evidence(home_team_id, cutoff, half_life_days, model, lineage_available=lineage_available)
    away = _team_evidence(away_team_id, cutoff, half_life_days, model, lineage_available=lineage_available)
    competition_id, competition_state = _competition_evidence(connection, fixture_id)
    competition_counts = getattr(model, "fitted_competition_counts", {})
    competition_observations = int(competition_counts.get(competition_id, 0)) if competition_id else 0
    fitted_competitions = set(getattr(model, "fitted_competitions", ()))
    competition_seen = competition_id is not None and competition_id in fitted_competitions
    policy = model_metrics.get("applicability_policy")
    policy_payload = policy if isinstance(policy, dict) else {}
    policy_validated = policy_payload.get("validated") is True
    minimum_effective = float(policy_payload.get("minimum_effective_matches", 0.0)) if policy_validated else 0.0
    policy_version = str(policy_payload.get("version")) if policy_validated and policy_payload.get("version") else None

    reasons: list[str] = []
    if not lineage_available:
        state, level = "OUT_OF_DOMAIN", "OUT_OF_DOMAIN"
        reasons.append("TRAINING_FIXTURE_LINEAGE_UNAVAILABLE")
    elif not home.in_training_universe and not away.in_training_universe:
        state, level = "PRIOR_ONLY", "PRIOR_ONLY"
        reasons.extend(("UNSEEN_HOME_TEAM", "UNSEEN_AWAY_TEAM", "GLOBAL_PRIOR_SUBSTITUTION"))
    elif not home.in_training_universe:
        state, level = "UNSEEN_HOME_TEAM", "PRIOR_ONLY"
        reasons.extend(("UNSEEN_HOME_TEAM", "GLOBAL_PRIOR_SUBSTITUTION"))
    elif not away.in_training_universe:
        state, level = "UNSEEN_AWAY_TEAM", "PRIOR_ONLY"
        reasons.extend(("UNSEEN_AWAY_TEAM", "GLOBAL_PRIOR_SUBSTITUTION"))
    elif not competition_seen:
        state, level = "UNSEEN_COMPETITION", "OUT_OF_DOMAIN"
        reasons.append("UNSEEN_COMPETITION")
    elif policy_validated and min(home.effective_observations, away.effective_observations) < minimum_effective:
        state, level = "LOW_TEAM_HISTORY", "LOW"
        reasons.append("MODEL_SPECIFIC_TEAM_EVIDENCE_GATE_FAILED")
    else:
        state = "PARTIALLY_POOLED" if model.regularization > 0 else "FULLY_ESTIMATED"
        level = "MEDIUM" if state == "PARTIALLY_POOLED" else "HIGH"

    if competition_state != "ACTIONABLE":
        reasons.append(f"COMPETITION_{competition_state}")
    if not policy_validated:
        reasons.append("NO_VALIDATED_MODEL_SPECIFIC_APPLICABILITY_POLICY")

    actionability = not reasons and state in {"FULLY_ESTIMATED", "PARTIALLY_POOLED"}
    parameter_state = "SHRUNK" if model.regularization > 0 else "FITTED"
    parameter_states = {
        "home_attack": parameter_state if home.in_training_universe else "PRIOR_ONLY",
        "home_defence": parameter_state if home.in_training_universe else "PRIOR_ONLY",
        "away_attack": parameter_state if away.in_training_universe else "PRIOR_ONLY",
        "away_defence": parameter_state if away.in_training_universe else "PRIOR_ONLY",
        "competition_baseline": "PARTIAL_POOL" if competition_seen else "PRIOR_ONLY",
        "home_advantage": "FITTED",
    }
    home_xg, away_xg = model.expected_goals(home_team_id, away_team_id)
    return ApplicabilityAssessment(
        state,
        level,
        actionability,
        tuple(dict.fromkeys(reasons)),
        home,
        away,
        competition_observations,
        competition_seen,
        competition_state,
        float(model.team_attack.get(home_team_id, 0.0)),
        float(model.team_defense.get(home_team_id, 0.0)),
        float(model.team_attack.get(away_team_id, 0.0)),
        float(model.team_defense.get(away_team_id, 0.0)),
        float(model.intercept),
        float(model.home_advantage),
        parameter_states,
        home_xg,
        away_xg,
        probabilities,
        policy_version,
    )


def _team_evidence(
    team_id: str,
    cutoff: datetime,
    half_life_days: float,
    model: PoissonModel,
    *,
    lineage_available: bool,
) -> TeamEvidence:
    history = getattr(model, "fitted_team_history", {})
    rows = [row for row in history.get(team_id, ()) if row[0] <= cutoff] if lineage_available else []
    decay = log(2) / max(half_life_days, 1e-9)
    effective = sum(exp(-decay * max(0.0, (cutoff - row[0]).total_seconds() / 86_400)) for row in rows)
    in_universe = lineage_available and team_id in model.fitted_teams
    # A transparent shrinkage proxy, not a posterior quantity or confidence interval.
    prior_fraction = 1.0 if not in_universe else model.regularization / (model.regularization + effective)
    return TeamEvidence(
        len(rows),
        float(effective),
        sum(bool(row[1]) for row in rows),
        sum(not bool(row[1]) for row in rows),
        rows[-1][0] if rows else None,
        in_universe,
        float(prior_fraction),
    )


def _competition_evidence(connection: duckdb.DuckDBPyConnection, fixture_id: str) -> tuple[str | None, str]:
    row = connection.execute(
        "SELECT f.competition_season_id, coalesce(d.universe_state, "
        "CASE WHEN cs.admitted THEN 'COLLECTED' ELSE 'DISCOVERED' END) "
        "FROM fixtures_current f JOIN competition_seasons cs USING (competition_season_id) "
        "LEFT JOIN competition_discoveries d USING (competition_season_id) "
        "WHERE CAST(f.fixture_id AS VARCHAR)=? ORDER BY d.discovered_at DESC NULLS LAST LIMIT 1",
        [fixture_id],
    ).fetchone()
    if row is None:
        return None, "OUT_OF_DOMAIN"
    return str(row[0]), str(row[1])
