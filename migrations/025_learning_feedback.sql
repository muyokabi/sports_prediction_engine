CREATE TABLE prediction_outcomes (
    prediction_id UUID NOT NULL REFERENCES institutional_predictions(prediction_id),
    engine VARCHAR NOT NULL,
    canonical_market VARCHAR NOT NULL,
    selection VARCHAR NOT NULL,
    line_key VARCHAR NOT NULL DEFAULT '',
    model_version VARCHAR NOT NULL,
    actual_outcome VARCHAR NOT NULL,
    probability DOUBLE,
    log_loss DOUBLE,
    brier DOUBLE,
    reference_decimal_odds DOUBLE,
    reference_return DOUBLE,
    settled_at TIMESTAMPTZ NOT NULL,
    settlement_version VARCHAR NOT NULL,
    PRIMARY KEY (prediction_id, engine, canonical_market, selection, line_key)
);

CREATE TABLE model_performance_rollups (
    rollup_id UUID PRIMARY KEY,
    model_version VARCHAR NOT NULL,
    engine VARCHAR NOT NULL,
    competition_id UUID,
    canonical_market VARCHAR NOT NULL,
    odds_band VARCHAR NOT NULL,
    opportunity_band VARCHAR NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    sample_size INTEGER NOT NULL,
    log_loss DOUBLE,
    brier DOUBLE,
    rps DOUBLE,
    ece DOUBLE,
    accuracy DOUBLE,
    roi DOUBLE,
    turnover DOUBLE,
    drawdown DOUBLE,
    closing_movement DOUBLE,
    abstention_rate DOUBLE,
    computed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (model_version, engine, competition_id, canonical_market, odds_band, opportunity_band, period_start, period_end)
);

CREATE TABLE model_drift_signals (
    signal_id UUID PRIMARY KEY,
    model_version VARCHAR NOT NULL,
    signal_type VARCHAR NOT NULL,
    scope JSON NOT NULL,
    observed_value DOUBLE,
    threshold DOUBLE,
    state VARCHAR NOT NULL,
    evidence JSON NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    CHECK (state IN ('NO_SIGNAL','REVIEW','RECALIBRATION_DUE','RETRAINING_DUE'))
);
