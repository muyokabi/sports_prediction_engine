CREATE TABLE canonical_market_mappings (
    provider VARCHAR NOT NULL,
    provider_market_id BIGINT NOT NULL,
    provider_market_name VARCHAR NOT NULL,
    canonical_market VARCHAR NOT NULL,
    market_family VARCHAR NOT NULL,
    state VARCHAR NOT NULL,
    settlement_version VARCHAR,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (provider, provider_market_id),
    CHECK (provider = 'api_football'),
    CHECK (state IN ('SUPPORTED','RESEARCH_ONLY','INSUFFICIENT_HISTORY','UNSUPPORTED_SETTLEMENT','NO_MODEL','NO_ODDS','DISABLED'))
);

CREATE TABLE analysis_runs (
    analysis_run_id UUID PRIMARY KEY,
    requested_start_date DATE NOT NULL,
    requested_end_date DATE NOT NULL,
    presentation_timezone VARCHAR NOT NULL,
    analysis_timestamp TIMESTAMPTZ NOT NULL,
    source_cutoff TIMESTAMPTZ NOT NULL,
    state VARCHAR NOT NULL,
    expected_fixture_count INTEGER NOT NULL DEFAULT 0,
    terminal_fixture_count INTEGER NOT NULL DEFAULT 0,
    report_path VARCHAR,
    job_run_id UUID REFERENCES job_runs(job_run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (requested_end_date >= requested_start_date),
    CHECK (state IN ('RUNNING','COMPLETE','INCOMPLETE','FAILED'))
);

CREATE TABLE analysis_fixture_manifest (
    analysis_run_id UUID NOT NULL REFERENCES analysis_runs(analysis_run_id),
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    terminal_state VARCHAR,
    reason_codes JSON NOT NULL DEFAULT '[]',
    processed_at TIMESTAMPTZ,
    PRIMARY KEY (analysis_run_id, fixture_id),
    CHECK (terminal_state IS NULL OR terminal_state IN (
        'ANALYZED','NO_ODDS','NO_QUALIFIED_MODEL','INSUFFICIENT_HISTORY','STALE_DATA',
        'BLOCKED_BY_INTERVENING_FIXTURE','QUARANTINED','STARTED','POSTPONED','UNSUPPORTED','FAILED'
    ))
);

CREATE TABLE institutional_predictions (
    prediction_id UUID PRIMARY KEY,
    analysis_run_id UUID NOT NULL REFERENCES analysis_runs(analysis_run_id),
    target_fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    analysis_timestamp TIMESTAMPTZ NOT NULL,
    target_kickoff TIMESTAMPTZ NOT NULL,
    source_cutoff TIMESTAMPTZ NOT NULL,
    intervening_fixture_ids JSON NOT NULL DEFAULT '[]',
    dependency_state VARCHAR NOT NULL,
    freshness_state VARCHAR NOT NULL,
    freshness_reasons JSON NOT NULL DEFAULT '[]',
    fundamental_model_version VARCHAR,
    ml_model_version VARCHAR,
    fusion_version VARCHAR,
    feature_dataset_id UUID REFERENCES feature_datasets(dataset_id),
    odds_snapshot_ids JSON NOT NULL DEFAULT '[]',
    superseded_by_prediction_id UUID REFERENCES institutional_predictions(prediction_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE (analysis_run_id, target_fixture_id),
    CHECK (dependency_state IN ('CLEAR','BLOCKED_BY_INTERVENING_FIXTURE','DEPENDENCY_RESOLVED')),
    CHECK (freshness_state IN ('CURRENT','MODEL_STATE_STALE','MARKET_PRICE_STALE','STALE_INTERVENING_FIXTURE','SUPERSEDED'))
);

CREATE TABLE engine_probability_prices (
    prediction_id UUID NOT NULL REFERENCES institutional_predictions(prediction_id),
    engine VARCHAR NOT NULL,
    independence VARCHAR NOT NULL,
    canonical_market VARCHAR NOT NULL,
    selection VARCHAR NOT NULL,
    line_key VARCHAR NOT NULL DEFAULT '',
    line DOUBLE,
    probability DOUBLE,
    full_win_probability DOUBLE,
    half_win_probability DOUBLE,
    push_probability DOUBLE,
    half_loss_probability DOUBLE,
    full_loss_probability DOUBLE,
    fair_decimal_odds DOUBLE,
    expected_home_goals DOUBLE,
    expected_away_goals DOUBLE,
    uncertainty DOUBLE,
    model_version VARCHAR NOT NULL,
    source_odds_snapshot_ids JSON NOT NULL DEFAULT '[]',
    PRIMARY KEY (prediction_id, engine, canonical_market, selection, line_key),
    CHECK (engine IN ('FUNDAMENTAL','ML','FUSED','MARKET')),
    CHECK (independence IN ('MARKET_INDEPENDENT','MARKET_INFORMED')),
    CHECK (probability IS NULL OR probability BETWEEN 0 AND 1)
);
