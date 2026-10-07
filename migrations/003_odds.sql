CREATE TABLE bookmakers (
    bookmaker_id UUID PRIMARY KEY,
    provider_bookmaker_id BIGINT NOT NULL UNIQUE,
    name VARCHAR NOT NULL
);
CREATE TABLE bet_markets (
    market_id UUID PRIMARY KEY,
    provider_market_id BIGINT NOT NULL UNIQUE,
    name VARCHAR NOT NULL
);
CREATE TABLE bet_selections (
    selection_id UUID PRIMARY KEY,
    market_id UUID NOT NULL REFERENCES bet_markets(market_id),
    name VARCHAR NOT NULL,
    normalized_name VARCHAR NOT NULL,
    line VARCHAR,
    UNIQUE (market_id, normalized_name, line)
);
CREATE TABLE odds_snapshots (
    snapshot_id UUID PRIMARY KEY,
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    observed_at TIMESTAMPTZ NOT NULL,
    provider_update_time TIMESTAMPTZ,
    source_raw_path VARCHAR NOT NULL,
    job_run_id UUID REFERENCES job_runs(job_run_id),
    content_hash VARCHAR NOT NULL,
    UNIQUE (fixture_id, observed_at, content_hash)
);
CREATE TABLE odds_prices (
    snapshot_id UUID NOT NULL REFERENCES odds_snapshots(snapshot_id),
    bookmaker_id UUID NOT NULL REFERENCES bookmakers(bookmaker_id),
    market_id UUID NOT NULL REFERENCES bet_markets(market_id),
    selection_id UUID NOT NULL REFERENCES bet_selections(selection_id),
    decimal_odds DOUBLE NOT NULL,
    raw_implied_probability DOUBLE NOT NULL,
    fair_probability DOUBLE,
    overround DOUBLE,
    PRIMARY KEY (snapshot_id, bookmaker_id, market_id, selection_id),
    CHECK (decimal_odds > 1.0)
);

