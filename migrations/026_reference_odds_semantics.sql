CREATE TABLE market_reference_quotes (
    reference_quote_id UUID PRIMARY KEY,
    prediction_id UUID NOT NULL REFERENCES institutional_predictions(prediction_id),
    snapshot_id UUID NOT NULL REFERENCES odds_snapshots(snapshot_id),
    bookmaker_id UUID NOT NULL REFERENCES bookmakers(bookmaker_id),
    market_id UUID NOT NULL REFERENCES bet_markets(market_id),
    selection_id UUID NOT NULL REFERENCES bet_selections(selection_id),
    canonical_market VARCHAR NOT NULL,
    selection VARCHAR NOT NULL,
    line_key VARCHAR NOT NULL DEFAULT '',
    reference_state VARCHAR NOT NULL,
    provider_update_timestamp TIMESTAMPTZ,
    collected_at TIMESTAMPTZ NOT NULL,
    prediction_timestamp TIMESTAMPTZ NOT NULL,
    kickoff_timestamp TIMESTAMPTZ NOT NULL,
    quote_age_minutes DOUBLE NOT NULL,
    decimal_odds DOUBLE NOT NULL,
    market_fair_probability DOUBLE,
    first_observed_decimal_odds DOUBLE,
    price_movement DOUBLE,
    snapshot_count INTEGER NOT NULL,
    source_bookmaker VARCHAR NOT NULL,
    source_raw_path VARCHAR NOT NULL,
    CHECK (reference_state IN (
        'CURRENT_REFERENCE','LATEST_PROVIDER_REFERENCE','AGED_REFERENCE','HISTORICAL_REFERENCE',
        'NO_REFERENCE_ODDS','INVALID_REFERENCE','POST_KICKOFF_INVALID'
    )),
    CHECK (decimal_odds > 1),
    UNIQUE (prediction_id, bookmaker_id, canonical_market, selection, line_key)
);

CREATE TABLE institutional_opportunities (
    opportunity_id UUID PRIMARY KEY,
    prediction_id UUID NOT NULL REFERENCES institutional_predictions(prediction_id),
    canonical_market VARCHAR NOT NULL,
    selection VARCHAR NOT NULL,
    line_key VARCHAR NOT NULL DEFAULT '',
    probability_source VARCHAR NOT NULL,
    model_probability DOUBLE NOT NULL,
    model_fair_odds DOUBLE NOT NULL,
    minimum_acceptable_odds DOUBLE NOT NULL,
    minimum_odds_method VARCHAR NOT NULL,
    uncertainty_adjustment DOUBLE NOT NULL,
    required_robust_ev DOUBLE NOT NULL,
    reference_state VARCHAR NOT NULL,
    latest_reference_odds DOUBLE,
    best_latest_reference_odds DOUBLE,
    worst_latest_reference_odds DOUBLE,
    reference_consensus_probability DOUBLE,
    reference_bookmaker VARCHAR,
    reference_observed_at TIMESTAMPTZ,
    reference_age_minutes DOUBLE,
    reference_snapshot_count INTEGER NOT NULL DEFAULT 0,
    reference_price_movement DOUBLE,
    bookmaker_dispersion DOUBLE,
    reference_edge DOUBLE,
    robust_estimated_edge DOUBLE,
    reference_expected_return DOUBLE,
    execution_edge DOUBLE,
    decision VARCHAR NOT NULL,
    reason_codes JSON NOT NULL DEFAULT '[]',
    manual_price_confirmation_required BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (model_probability BETWEEN 0 AND 1),
    CHECK (model_fair_odds > 1),
    CHECK (minimum_acceptable_odds > 1),
    CHECK (execution_edge IS NULL),
    CHECK (decision IN ('PRICE_TARGET','BET_IF_PRICE_AVAILABLE','WATCH','NO_BET')),
    UNIQUE (prediction_id, canonical_market, selection, line_key)
);

CREATE TABLE odds_age_research_results (
    research_id UUID PRIMARY KEY,
    scope_type VARCHAR NOT NULL,
    scope_key VARCHAR NOT NULL,
    market_family VARCHAR NOT NULL,
    sample_size INTEGER NOT NULL,
    median_age_minutes DOUBLE,
    mean_absolute_probability_movement DOUBLE,
    median_absolute_probability_movement DOUBLE,
    mean_bookmaker_dispersion DOUBLE,
    age_movement_correlation DOUBLE,
    production_penalty_qualified BOOLEAN NOT NULL DEFAULT false,
    evidence JSON NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (scope_type, scope_key, market_family, computed_at)
);

CREATE TABLE prediction_decisions_v2 (
    decision_id UUID PRIMARY KEY,
    prediction_run_id UUID NOT NULL REFERENCES prediction_runs(prediction_run_id),
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    state VARCHAR NOT NULL,
    reason_codes JSON NOT NULL,
    selected_market VARCHAR,
    model_probability DOUBLE,
    market_fair_probability DOUBLE,
    reference_decimal_odds DOUBLE,
    raw_implied_probability DOUBLE,
    reference_expected_value DOUBLE,
    minimum_acceptable_odds DOUBLE,
    odds_observation_timestamp TIMESTAMPTZ,
    decision_timestamp TIMESTAMPTZ NOT NULL,
    stake_fraction DOUBLE,
    reference_state VARCHAR,
    execution_edge DOUBLE,
    manual_price_confirmation_required BOOLEAN NOT NULL DEFAULT true,
    CHECK (state IN ('BET','NO_BET','PRICE_TARGET','BET_IF_PRICE_AVAILABLE','WATCH')),
    CHECK (stake_fraction IS NULL OR stake_fraction BETWEEN 0 AND 1),
    CHECK (execution_edge IS NULL),
    UNIQUE (prediction_run_id, fixture_id)
);

INSERT INTO prediction_decisions_v2 (
    decision_id, prediction_run_id, fixture_id, state, reason_codes, selected_market, model_probability,
    market_fair_probability, reference_decimal_odds, raw_implied_probability, reference_expected_value,
    minimum_acceptable_odds, odds_observation_timestamp, decision_timestamp, stake_fraction,
    reference_state, execution_edge, manual_price_confirmation_required
)
SELECT decision_id, prediction_run_id, fixture_id, state, reason_codes, selected_market, model_probability,
       market_fair_probability, offered_decimal_odds, raw_implied_probability, estimated_expected_value,
       minimum_acceptable_odds, odds_observation_timestamp, decision_timestamp, stake_fraction,
       NULL, NULL, true
FROM prediction_decisions;

DROP TABLE prediction_decisions;
ALTER TABLE prediction_decisions_v2 RENAME TO prediction_decisions;
