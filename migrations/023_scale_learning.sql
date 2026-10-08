ALTER TABLE model_runs ADD COLUMN evidence_state VARCHAR;
ALTER TABLE model_runs ADD COLUMN parent_model_version VARCHAR;
ALTER TABLE model_runs ADD COLUMN training_mode VARCHAR;
ALTER TABLE model_runs ADD COLUMN training_cutoff TIMESTAMPTZ;
ALTER TABLE model_runs ADD COLUMN observations_included INTEGER;

CREATE TABLE model_evidence_assessments (
    assessment_id UUID PRIMARY KEY,
    model_type VARCHAR NOT NULL,
    dataset_id UUID NOT NULL REFERENCES feature_datasets(dataset_id),
    model_version VARCHAR,
    evidence_state VARCHAR NOT NULL,
    reason_codes JSON NOT NULL,
    measurements JSON NOT NULL,
    policy JSON NOT NULL,
    assessed_at TIMESTAMPTZ NOT NULL,
    CHECK (evidence_state IN ('INSUFFICIENT_DATA','RESEARCH_TRAINABLE','VALIDATION_ELIGIBLE','PRODUCTION_CANDIDATE','PRODUCTION_ACTIONABLE'))
);

CREATE TABLE model_update_events (
    event_id UUID PRIMARY KEY,
    model_type VARCHAR NOT NULL,
    current_version VARCHAR,
    trigger_type VARCHAR NOT NULL,
    observations_since_training INTEGER NOT NULL,
    due BOOLEAN NOT NULL,
    reason_codes JSON NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL
);
