CREATE TABLE injury_collection_runs (
    collection_id UUID PRIMARY KEY,
    target_date DATE NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    source_raw_path VARCHAR,
    complete BOOLEAN NOT NULL,
    job_run_id UUID REFERENCES job_runs(job_run_id)
);

CREATE TABLE injury_observations (
    injury_observation_id UUID PRIMARY KEY,
    provider_fixture_id BIGINT NOT NULL,
    fixture_id UUID REFERENCES fixtures(fixture_id),
    team_id UUID NOT NULL REFERENCES teams(team_id),
    player_id UUID NOT NULL REFERENCES players(player_id),
    observed_at TIMESTAMPTZ NOT NULL,
    injury_type VARCHAR,
    reason VARCHAR,
    source_payload JSON NOT NULL,
    source_raw_path VARCHAR NOT NULL,
    job_run_id UUID REFERENCES job_runs(job_run_id)
);
