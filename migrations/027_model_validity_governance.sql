ALTER TABLE analysis_runs ADD COLUMN report_mode VARCHAR DEFAULT 'LIVE';
ALTER TABLE analysis_runs ADD COLUMN source_live_run_id UUID;

ALTER TABLE institutional_opportunities ADD COLUMN governance_state VARCHAR DEFAULT 'RESEARCH_VALUE_SIGNAL';
ALTER TABLE institutional_opportunities ADD COLUMN uncertainty_score DOUBLE;
ALTER TABLE institutional_opportunities ADD COLUMN uncertainty_components JSON DEFAULT '{}';
ALTER TABLE institutional_opportunities ADD COLUMN threshold_version VARCHAR;
ALTER TABLE institutional_opportunities ADD COLUMN threshold_derivation JSON DEFAULT '{}';

CREATE TABLE prediction_applicability (
    prediction_id UUID PRIMARY KEY REFERENCES institutional_predictions(prediction_id),
    model_version VARCHAR NOT NULL,
    model_type VARCHAR NOT NULL,
    applicability_state VARCHAR NOT NULL,
    applicability_level VARCHAR NOT NULL,
    actionability_qualified BOOLEAN NOT NULL,
    reason_codes JSON NOT NULL,
    home_observations INTEGER NOT NULL,
    away_observations INTEGER NOT NULL,
    home_effective_observations DOUBLE NOT NULL,
    away_effective_observations DOUBLE NOT NULL,
    home_home_observations INTEGER NOT NULL,
    home_away_observations INTEGER NOT NULL,
    away_home_observations INTEGER NOT NULL,
    away_away_observations INTEGER NOT NULL,
    competition_observations INTEGER NOT NULL,
    home_last_observation TIMESTAMPTZ,
    away_last_observation TIMESTAMPTZ,
    home_in_training_universe BOOLEAN NOT NULL,
    away_in_training_universe BOOLEAN NOT NULL,
    competition_in_training_universe BOOLEAN NOT NULL,
    home_prior_fraction DOUBLE NOT NULL,
    away_prior_fraction DOUBLE NOT NULL,
    home_attack DOUBLE NOT NULL,
    home_defence DOUBLE NOT NULL,
    away_attack DOUBLE NOT NULL,
    away_defence DOUBLE NOT NULL,
    competition_baseline DOUBLE NOT NULL,
    home_advantage DOUBLE NOT NULL,
    parameter_states JSON NOT NULL,
    expected_home_goals DOUBLE NOT NULL,
    expected_away_goals DOUBLE NOT NULL,
    probabilities JSON NOT NULL,
    training_cutoff TIMESTAMPTZ,
    policy_version VARCHAR,
    assessed_at TIMESTAMPTZ NOT NULL,
    CHECK (applicability_state IN (
        'FULLY_ESTIMATED','PARTIALLY_POOLED','LOW_TEAM_HISTORY','UNSEEN_HOME_TEAM',
        'UNSEEN_AWAY_TEAM','UNSEEN_COMPETITION','PRIOR_ONLY','OUT_OF_DOMAIN'
    )),
    CHECK (applicability_level IN ('HIGH','MEDIUM','LOW','PRIOR_ONLY','OUT_OF_DOMAIN'))
);

CREATE TABLE model_market_roles (
    role_id UUID PRIMARY KEY,
    market_family VARCHAR NOT NULL,
    role_name VARCHAR NOT NULL,
    model_version VARCHAR NOT NULL,
    model_type VARCHAR NOT NULL,
    state VARCHAR NOT NULL,
    evaluation_window JSON NOT NULL,
    metrics JSON NOT NULL,
    uncertainty JSON NOT NULL,
    market_baseline JSON NOT NULL,
    selected_at TIMESTAMPTZ NOT NULL,
    UNIQUE (market_family, role_name, model_version),
    CHECK (state IN ('CHAMPION','CHALLENGER','NO_CLEAR_WINNER','RESEARCH_ONLY','REJECTED'))
);

CREATE TABLE calibration_validations (
    validation_id UUID PRIMARY KEY,
    model_version VARCHAR NOT NULL,
    market_family VARCHAR NOT NULL,
    state VARCHAR NOT NULL,
    method VARCHAR NOT NULL,
    evaluation_window JSON NOT NULL,
    metrics JSON NOT NULL,
    validated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (model_version, market_family, validated_at),
    CHECK (state IN ('CALIBRATION_VALIDATED','CALIBRATION_FAILED'))
);

CREATE TABLE shadow_opportunities (
    shadow_id UUID PRIMARY KEY,
    opportunity_id UUID NOT NULL REFERENCES institutional_opportunities(opportunity_id),
    state VARCHAR NOT NULL DEFAULT 'SHADOW_ACTIONABLE',
    qualification_evidence JSON NOT NULL,
    outcome_metrics JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    settled_at TIMESTAMPTZ,
    UNIQUE (opportunity_id),
    CHECK (state IN ('SHADOW_ACTIONABLE','SHADOW_SETTLED','SHADOW_REJECTED','PRODUCTION_APPROVED'))
);
