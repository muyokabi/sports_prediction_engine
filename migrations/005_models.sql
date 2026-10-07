CREATE TABLE model_runs (
    model_run_id UUID PRIMARY KEY,
    model_type VARCHAR NOT NULL,
    version VARCHAR NOT NULL UNIQUE,
    status VARCHAR NOT NULL,
    training_start TIMESTAMPTZ,
    training_end TIMESTAMPTZ,
    feature_schema_hash VARCHAR NOT NULL,
    training_dataset_hash VARCHAR NOT NULL,
    hyperparameters JSON NOT NULL,
    metrics JSON NOT NULL,
    calibration_method VARCHAR,
    artifact_path VARCHAR NOT NULL,
    library_versions JSON NOT NULL,
    git_commit VARCHAR,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE backtest_decisions (
    decision_id UUID PRIMARY KEY,
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    prediction_timestamp TIMESTAMPTZ NOT NULL,
    market_snapshot_timestamp TIMESTAMPTZ,
    model_version VARCHAR NOT NULL,
    predicted_probabilities JSON NOT NULL,
    market_probabilities JSON,
    decision_rule VARCHAR,
    selected_market VARCHAR,
    decimal_odds DOUBLE,
    outcome VARCHAR,
    pnl DOUBLE
);

