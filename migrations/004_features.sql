CREATE TABLE feature_datasets (
    dataset_id UUID PRIMARY KEY,
    name VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    feature_cutoff_start TIMESTAMPTZ,
    feature_cutoff_end TIMESTAMPTZ,
    schema_hash VARCHAR NOT NULL,
    dataset_hash VARCHAR NOT NULL,
    parquet_path VARCHAR NOT NULL,
    config JSON NOT NULL
);
CREATE TABLE prediction_runs (
    prediction_run_id UUID PRIMARY KEY,
    prediction_timestamp TIMESTAMPTZ NOT NULL,
    feature_cutoff_timestamp TIMESTAMPTZ NOT NULL,
    odds_snapshot_timestamp TIMESTAMPTZ,
    model_version VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE predictions (
    prediction_run_id UUID NOT NULL REFERENCES prediction_runs(prediction_run_id),
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    probability_home DOUBLE NOT NULL,
    probability_draw DOUBLE NOT NULL,
    probability_away DOUBLE NOT NULL,
    market_home_fair DOUBLE,
    market_draw_fair DOUBLE,
    market_away_fair DOUBLE,
    quality_status VARCHAR NOT NULL,
    PRIMARY KEY (prediction_run_id, fixture_id)
);

