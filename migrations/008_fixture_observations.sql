CREATE TABLE fixture_observations (
    observation_id UUID PRIMARY KEY,
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    observed_at TIMESTAMPTZ NOT NULL,
    round VARCHAR,
    kickoff_utc TIMESTAMPTZ NOT NULL,
    status_short VARCHAR NOT NULL,
    status_long VARCHAR,
    elapsed INTEGER,
    home_goals INTEGER,
    away_goals INTEGER,
    source_raw_path VARCHAR NOT NULL,
    UNIQUE (fixture_id, observed_at)
);

CREATE VIEW fixtures_current AS
SELECT
    f.fixture_id,
    f.competition_season_id,
    f.provider_fixture_id,
    o.round,
    o.kickoff_utc,
    f.venue_id,
    f.referee,
    o.status_short,
    o.status_long,
    o.elapsed,
    f.home_team_id,
    f.away_team_id,
    o.home_goals,
    o.away_goals,
    f.halftime_home,
    f.halftime_away,
    f.fulltime_home,
    f.fulltime_away,
    f.extratime_home,
    f.extratime_away,
    f.penalty_home,
    f.penalty_away,
    f.eligibility,
    o.source_raw_path,
    f.normalizer_version,
    o.observed_at AS retrieved_at,
    f.updated_at
FROM fixtures f
JOIN fixture_observations o ON o.fixture_id = f.fixture_id
QUALIFY row_number() OVER (
    PARTITION BY o.fixture_id
    ORDER BY o.observed_at DESC, o.observation_id DESC
) = 1;
