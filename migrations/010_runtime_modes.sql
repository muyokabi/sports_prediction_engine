ALTER TABLE competition_seasons ADD COLUMN ledger_mode VARCHAR;
UPDATE competition_seasons SET ledger_mode = 'production' WHERE ledger_mode IS NULL;

ALTER TABLE job_runs ADD COLUMN application_mode VARCHAR;

CREATE TABLE provider_capabilities (
    capability_id UUID PRIMARY KEY,
    provider VARCHAR NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    subscription_plan VARCHAR,
    subscription_active BOOLEAN,
    requests_current INTEGER,
    requests_limit_daily INTEGER,
    production_season INTEGER,
    production_accessible BOOLEAN,
    replay_season INTEGER,
    replay_accessible BOOLEAN,
    raw_path VARCHAR
);
