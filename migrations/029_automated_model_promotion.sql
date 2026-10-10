CREATE TABLE model_promotion_assessments (
    assessment_id UUID PRIMARY KEY,
    model_version VARCHAR NOT NULL,
    model_type VARCHAR NOT NULL,
    market_family VARCHAR NOT NULL,
    policy_version VARCHAR NOT NULL,
    state VARCHAR NOT NULL,
    reason_codes JSON NOT NULL,
    gate_results JSON NOT NULL,
    evaluation_path VARCHAR,
    assessed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (model_version, market_family, policy_version, evaluation_path),
    CHECK (state IN ('PROMOTED','WITHHELD','REJECTED'))
);
