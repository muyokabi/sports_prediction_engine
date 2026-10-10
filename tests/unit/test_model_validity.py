from datetime import UTC, datetime, timedelta
from math import log
from pathlib import Path

import duckdb
import numpy as np
import polars as pl
import pytest

from sports_engine.analysis.service import AnalysisService
from sports_engine.core.config import ShadowCandidateConfig
from sports_engine.evaluation.uncertainty import (
    chronological_block_bootstrap,
    paired_metric_difference,
    per_fixture_loss,
)
from sports_engine.markets.pricing import CoreMarketPrices
from sports_engine.markets.reference import ReferenceState
from sports_engine.models.applicability import ApplicabilityAssessment, TeamEvidence, assess_score_model_applicability
from sports_engine.models.statistical.poisson import PoissonModel
from sports_engine.sports.football.prediction.service import PredictionService, TrainingDomain


def test_shadow_bootstrap_breaks_production_gate_circularity_without_approving_execution(tmp_path: Path) -> None:
    service = AnalysisService(
        duckdb.connect(":memory:"),
        tmp_path,
        shadow_policy=ShadowCandidateConfig(),
    )
    evidence = TeamEvidence(20, 18.0, 10, 10, datetime(2026, 1, 1, tzinfo=UTC), True, 0.05)
    assessment = ApplicabilityAssessment(
        "PARTIALLY_POOLED",
        "MEDIUM",
        False,
        ("NO_VALIDATED_MODEL_SPECIFIC_APPLICABILITY_POLICY",),
        evidence,
        evidence,
        100,
        True,
        "ACTIONABLE",
        0.1,
        -0.1,
        0.1,
        -0.1,
        0.2,
        0.1,
        {},
        1.4,
        1.1,
        {},
        None,
    )
    assert service._shadow_qualified(
        assessment,
        "MATCH_ODDS",
        ReferenceState.CURRENT_REFERENCE,
        reference_edge=0.05,
        reference_return=0.06,
        reference_bookmakers=3,
    )
    assert not assessment.actionability_qualified
    assert service._shadow_qualified(
        assessment,
        "MATCH_ODDS",
        ReferenceState.AGED_REFERENCE,
        reference_edge=0.05,
        reference_return=0.06,
        reference_bookmakers=3,
    )
    assert not service._shadow_qualified(
        assessment,
        "MATCH_ODDS",
        ReferenceState.CURRENT_REFERENCE,
        reference_edge=0.20,
        reference_return=0.80,
        reference_bookmakers=3,
    )
    assert not service._shadow_qualified(
        assessment,
        "MATCH_ODDS",
        ReferenceState.CURRENT_REFERENCE,
        reference_edge=0.05,
        reference_return=0.06,
        reference_bookmakers=1,
    )


def test_provider_away_handicap_line_is_inverted_for_selected_team_settlement(tmp_path: Path) -> None:
    service = AnalysisService(
        duckdb.connect(":memory:"),
        tmp_path,
        shadow_policy=ShadowCandidateConfig(allowed_markets=["ASIAN_HANDICAP"]),
    )
    service._reference_quote_cache = {("fixture", "ASIAN_HANDICAP", "AWAY", "+2.5"): []}
    prices = CoreMarketPrices.from_expected_goals(1.5, 1.0)
    rows = service._observed_supported_market_rows("fixture", prices, [])
    assert len(rows) == 1
    assert rows[0][0:4] == ("ASIAN_HANDICAP", "AWAY", "+2.5", 2.5)
    assert rows[0][4] == prices.asian_handicap(-2.5, "away")


def test_unseen_teams_resolve_to_identical_global_prior_and_are_detectable() -> None:
    model = PoissonModel(intercept=log(1.3), home_advantage=0.15)
    first = model.predict_proba([("unseen-a", "unseen-b")])[0]
    second = model.predict_proba([("unseen-c", "unseen-d")])[0]
    assert first == pytest.approx(second)
    assert "unseen-a" not in model.fitted_teams
    assert model.team_attack.get("unseen-a") is None


def test_chronological_bootstrap_reports_uncertainty_and_paired_difference() -> None:
    targets = np.asarray([0, 1, 2, 0, 1, 2])
    candidate = np.asarray([[0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8]] * 2)
    comparator = np.full((6, 3), 1 / 3)
    losses = per_fixture_loss(targets, candidate, "log_loss")
    interval = chronological_block_bootstrap(losses, samples=200, seed=7)
    difference = paired_metric_difference(targets, candidate, comparator, "log_loss", samples=200, seed=7)
    assert interval.lower <= interval.estimate <= interval.upper
    assert difference.upper < 0
    assert "chronological-block-bootstrap" in difference.method


def test_competition_applicability_uses_exact_training_lineage_not_warehouse_presence() -> None:
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE competition_seasons (competition_season_id VARCHAR, admitted BOOLEAN); "
        "CREATE TABLE competition_discoveries (competition_season_id VARCHAR, universe_state VARCHAR, "
        "discovered_at TIMESTAMPTZ); "
        "CREATE TABLE fixtures_current (fixture_id VARCHAR, competition_season_id VARCHAR, "
        "home_team_id VARCHAR, away_team_id VARCHAR, status_short VARCHAR, kickoff_utc TIMESTAMPTZ)"
    )
    connection.execute("INSERT INTO competition_seasons VALUES ('trained', true), ('warehouse-only', true)")
    connection.execute(
        "INSERT INTO competition_discoveries VALUES "
        "('trained', 'ACTIONABLE', '2026-01-01'), ('warehouse-only', 'ACTIONABLE', '2026-01-01')"
    )
    connection.execute(
        "INSERT INTO fixtures_current VALUES "
        "('history-a', 'warehouse-only', 'home', 'prior-a', 'FT', '2026-01-01'), "
        "('history-b', 'warehouse-only', 'prior-b', 'away', 'FT', '2026-01-02'), "
        "('target', 'warehouse-only', 'home', 'away', 'NS', '2026-03-01')"
    )
    model = PoissonModel(
        intercept=log(1.3),
        home_advantage=0.1,
        fitted_teams=("home", "away"),
        fitted_competitions=("trained",),
        team_attack={"home": 0.1, "away": -0.1},
        team_defense={"home": -0.1, "away": 0.1},
    )
    assessment = assess_score_model_applicability(
        connection,
        fixture_id="target",
        home_team_id="home",
        away_team_id="away",
        model=model,
        model_type="poisson",
        model_metrics={"applicability_policy": {"validated": True, "minimum_effective_matches": 0, "version": "test"}},
        training_cutoff=datetime(2026, 2, 1, tzinfo=UTC),
        half_life_days=365,
        probabilities={"home": 0.4, "draw": 0.3, "away": 0.3},
    )

    assert assessment.competition_observations == 2
    assert not assessment.competition_in_training_universe
    assert assessment.state == "UNSEEN_COMPETITION"
    assert not assessment.actionability_qualified


def test_legacy_prediction_path_fails_closed_outside_exact_training_domain() -> None:
    domain = TrainingDomain(
        frozenset({"home", "away"}),
        frozenset({"trained-competition"}),
        True,
    )
    state, reasons = PredictionService._fixture_applicability(
        domain,
        home_team_id="home",
        away_team_id="away",
        competition_season_id="warehouse-only",
    )
    assert state == "UNSEEN_COMPETITION"
    assert reasons == ("UNSEEN_COMPETITION",)


def test_legacy_prediction_path_never_assumes_missing_lineage_is_in_domain() -> None:
    state, reasons = PredictionService._fixture_applicability(
        TrainingDomain(frozenset(), frozenset(), False),
        home_team_id="home",
        away_team_id="away",
        competition_season_id="competition",
    )
    assert state == "OUT_OF_DOMAIN"
    assert reasons == ("TRAINING_LINEAGE_UNAVAILABLE",)


def test_ml_training_domain_uses_only_chronological_training_partition(tmp_path: Path) -> None:
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE feature_datasets (dataset_hash VARCHAR, parquet_path VARCHAR, created_at TIMESTAMPTZ); "
        "CREATE TABLE fixtures_current (fixture_id VARCHAR, competition_season_id VARCHAR)"
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "fixture_id": [f"fixture-{index}" for index in range(6)],
            "prediction_timestamp": [start + timedelta(days=index) for index in range(6)],
            "home_team_id": [f"home-{index}" for index in range(6)],
            "away_team_id": [f"away-{index}" for index in range(6)],
        }
    )
    path = tmp_path / "training.parquet"
    frame.write_parquet(path)
    connection.execute("INSERT INTO feature_datasets VALUES ('hash', ?, ?)", [str(path), start])
    connection.executemany(
        "INSERT INTO fixtures_current VALUES (?, ?)",
        [(f"fixture-{index}", "train-comp" if index < 3 else "future-comp") for index in range(6)],
    )
    service = PredictionService(connection, windows=[3], exponential_half_life=5, prediction_lead_hours=24)
    domain = service._training_domain("logistic", object(), "hash")
    assert domain.lineage_available
    assert domain.competitions == frozenset({"train-comp"})
    assert domain.teams == frozenset(
        {*(f"home-{index}" for index in range(3)), *(f"away-{index}" for index in range(3))}
    )
