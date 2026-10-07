CREATE TABLE fixture_repair_state (
    fixture_id UUID PRIMARY KEY REFERENCES fixtures(fixture_id),
    attempt_count INTEGER NOT NULL,
    last_attempt_at TIMESTAMPTZ NOT NULL,
    next_retry_after TIMESTAMPTZ NOT NULL,
    last_missing JSON NOT NULL
);
