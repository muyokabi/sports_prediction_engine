CREATE TABLE model_probability_scope_validations (
    validation_id UUID PRIMARY KEY,
    model_version VARCHAR NOT NULL,
    model_type VARCHAR NOT NULL,
    market_family VARCHAR NOT NULL,
    scope_type VARCHAR NOT NULL,
    scope_key VARCHAR NOT NULL,
    state VARCHAR NOT NULL,
    policy_version VARCHAR NOT NULL,
    evaluation_path VARCHAR NOT NULL,
    rows_evaluated INTEGER NOT NULL,
    metrics JSON NOT NULL,
    reason_codes JSON NOT NULL,
    validated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (model_version, market_family, scope_type, scope_key, policy_version, evaluation_path),
    CHECK (scope_type IN ('GLOBAL','COMPETITION')),
    CHECK (state IN ('VALIDATED','FAILED','INSUFFICIENT_SAMPLE'))
);
