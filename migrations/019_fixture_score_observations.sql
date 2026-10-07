ALTER TABLE fixture_observations ADD COLUMN halftime_home INTEGER;
ALTER TABLE fixture_observations ADD COLUMN halftime_away INTEGER;
ALTER TABLE fixture_observations ADD COLUMN fulltime_home INTEGER;
ALTER TABLE fixture_observations ADD COLUMN fulltime_away INTEGER;
ALTER TABLE fixture_observations ADD COLUMN extratime_home INTEGER;
ALTER TABLE fixture_observations ADD COLUMN extratime_away INTEGER;
ALTER TABLE fixture_observations ADD COLUMN penalty_home INTEGER;
ALTER TABLE fixture_observations ADD COLUMN penalty_away INTEGER;

UPDATE fixture_observations o SET
    halftime_home=f.halftime_home,
    halftime_away=f.halftime_away,
    fulltime_home=f.fulltime_home,
    fulltime_away=f.fulltime_away,
    extratime_home=f.extratime_home,
    extratime_away=f.extratime_away,
    penalty_home=f.penalty_home,
    penalty_away=f.penalty_away
FROM fixtures f WHERE f.fixture_id=o.fixture_id;

CREATE OR REPLACE VIEW fixtures_current AS
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
    o.halftime_home,
    o.halftime_away,
    o.fulltime_home,
    o.fulltime_away,
    o.extratime_home,
    o.extratime_away,
    o.penalty_home,
    o.penalty_away,
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
