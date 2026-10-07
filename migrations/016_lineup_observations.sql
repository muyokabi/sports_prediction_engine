CREATE TABLE lineup_observations (
    observation_id UUID PRIMARY KEY,
    lineup_id UUID NOT NULL REFERENCES lineups(lineup_id),
    observed_at TIMESTAMPTZ NOT NULL,
    coach_id UUID,
    formation VARCHAR,
    source_payload JSON NOT NULL,
    source_raw_path VARCHAR NOT NULL
);
