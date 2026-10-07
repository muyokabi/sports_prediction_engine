CREATE TABLE schema_versions (
    version INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    checksum VARCHAR NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE providers (
    provider_id UUID PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    base_url VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);

CREATE TABLE provider_entity_map (
    provider_id UUID NOT NULL REFERENCES providers(provider_id),
    entity_type VARCHAR NOT NULL,
    provider_entity_id VARCHAR NOT NULL,
    canonical_entity_id UUID NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (provider_id, entity_type, provider_entity_id)
);

CREATE TABLE job_runs (
    job_run_id UUID PRIMARY KEY,
    job_name VARCHAR NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status VARCHAR NOT NULL,
    metrics JSON,
    error_message VARCHAR
);

CREATE TABLE api_request_log (
    request_id UUID PRIMARY KEY,
    provider VARCHAR NOT NULL,
    endpoint VARCHAR NOT NULL,
    query_hash VARCHAR NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    http_status INTEGER,
    api_errors JSON,
    response_results INTEGER,
    page_current INTEGER,
    page_total INTEGER,
    requests_limit_daily INTEGER,
    requests_remaining_daily INTEGER,
    requests_limit_minute INTEGER,
    requests_remaining_minute INTEGER,
    purpose VARCHAR NOT NULL,
    priority VARCHAR NOT NULL,
    job_run_id UUID REFERENCES job_runs(job_run_id),
    elapsed_ms DOUBLE,
    raw_path VARCHAR
);

CREATE TABLE checkpoints (
    checkpoint_key VARCHAR PRIMARY KEY,
    value JSON NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    job_run_id UUID REFERENCES job_runs(job_run_id)
);

CREATE TABLE data_quality_issues (
    issue_id UUID PRIMARY KEY,
    fixture_id UUID,
    category VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    reason VARCHAR NOT NULL,
    details JSON,
    detected_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_retry_after TIMESTAMPTZ,
    resolution VARCHAR,
    resolved_at TIMESTAMPTZ
);

INSERT INTO providers (provider_id, name, base_url)
VALUES ('8d39dc64-2491-5b70-9fb8-2b0b379b2026', 'api_football', 'https://v3.football.api-sports.io');

