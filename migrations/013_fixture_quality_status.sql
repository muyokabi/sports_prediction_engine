-- Mutable eligibility is isolated from the referenced fixture identity row because
-- DuckDB cannot reliably update a parent row that has active foreign-key children.
CREATE TABLE fixture_quality_status (
    fixture_id UUID PRIMARY KEY REFERENCES fixtures(fixture_id),
    eligibility VARCHAR NOT NULL,
    assessed_at TIMESTAMPTZ NOT NULL,
    source_raw_path VARCHAR NOT NULL
);
