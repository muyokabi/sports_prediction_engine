CREATE TABLE competitions (
    competition_id UUID PRIMARY KEY,
    name VARCHAR NOT NULL,
    country VARCHAR,
    competition_type VARCHAR,
    logo_url VARCHAR,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE seasons (
    season_id UUID PRIMARY KEY,
    label VARCHAR NOT NULL,
    start_date DATE,
    end_date DATE,
    current BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE competition_seasons (
    competition_season_id UUID PRIMARY KEY,
    competition_id UUID NOT NULL REFERENCES competitions(competition_id),
    season_id UUID NOT NULL REFERENCES seasons(season_id),
    provider_season INTEGER NOT NULL,
    admitted BOOLEAN NOT NULL DEFAULT false,
    admission_reason VARCHAR,
    coverage JSON NOT NULL,
    priority INTEGER,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (competition_id, provider_season)
);
CREATE TABLE teams (
    team_id UUID PRIMARY KEY,
    name VARCHAR NOT NULL,
    country VARCHAR,
    founded INTEGER,
    national BOOLEAN,
    logo_url VARCHAR,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE players (
    player_id UUID PRIMARY KEY,
    name VARCHAR NOT NULL,
    firstname VARCHAR,
    lastname VARCHAR,
    birth_date DATE,
    nationality VARCHAR,
    height VARCHAR,
    weight VARCHAR,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE venues (
    venue_id UUID PRIMARY KEY,
    name VARCHAR,
    city VARCHAR,
    address VARCHAR,
    capacity INTEGER,
    surface VARCHAR,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE coaches (
    coach_id UUID PRIMARY KEY,
    name VARCHAR NOT NULL,
    nationality VARCHAR,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE fixtures (
    fixture_id UUID PRIMARY KEY,
    competition_season_id UUID NOT NULL REFERENCES competition_seasons(competition_season_id),
    provider_fixture_id BIGINT NOT NULL UNIQUE,
    round VARCHAR,
    kickoff_utc TIMESTAMPTZ NOT NULL,
    venue_id UUID REFERENCES venues(venue_id),
    referee VARCHAR,
    status_short VARCHAR NOT NULL,
    status_long VARCHAR,
    elapsed INTEGER,
    home_team_id UUID NOT NULL REFERENCES teams(team_id),
    away_team_id UUID NOT NULL REFERENCES teams(team_id),
    home_goals INTEGER,
    away_goals INTEGER,
    halftime_home INTEGER,
    halftime_away INTEGER,
    fulltime_home INTEGER,
    fulltime_away INTEGER,
    extratime_home INTEGER,
    extratime_away INTEGER,
    penalty_home INTEGER,
    penalty_away INTEGER,
    eligibility VARCHAR NOT NULL DEFAULT 'PENDING_REPAIR',
    source_raw_path VARCHAR NOT NULL,
    normalizer_version VARCHAR NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (home_team_id <> away_team_id)
);
CREATE TABLE fixture_status_history (
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    observed_at TIMESTAMPTZ NOT NULL,
    status_short VARCHAR NOT NULL,
    status_long VARCHAR,
    elapsed INTEGER,
    source_raw_path VARCHAR NOT NULL,
    PRIMARY KEY (fixture_id, observed_at)
);
CREATE TABLE fixture_schedule_snapshots (
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    observed_at TIMESTAMPTZ NOT NULL,
    kickoff_utc TIMESTAMPTZ NOT NULL,
    venue_id UUID REFERENCES venues(venue_id),
    round VARCHAR,
    source_raw_path VARCHAR NOT NULL,
    PRIMARY KEY (fixture_id, observed_at)
);
CREATE TABLE fixture_team (
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    team_id UUID NOT NULL REFERENCES teams(team_id),
    opponent_team_id UUID NOT NULL REFERENCES teams(team_id),
    venue_role VARCHAR NOT NULL,
    goals_for INTEGER,
    goals_against INTEGER,
    PRIMARY KEY (fixture_id, team_id),
    CHECK (venue_role IN ('HOME', 'AWAY'))
);
CREATE TABLE fixture_events (
    event_id UUID PRIMARY KEY,
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    team_id UUID REFERENCES teams(team_id),
    player_id UUID REFERENCES players(player_id),
    assist_player_id UUID REFERENCES players(player_id),
    elapsed INTEGER,
    extra INTEGER,
    event_type VARCHAR NOT NULL,
    detail VARCHAR,
    comments VARCHAR,
    provider_sequence INTEGER,
    source_payload JSON NOT NULL
);
CREATE TABLE lineups (
    lineup_id UUID PRIMARY KEY,
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    team_id UUID NOT NULL REFERENCES teams(team_id),
    coach_id UUID REFERENCES coaches(coach_id),
    formation VARCHAR,
    source_payload JSON NOT NULL,
    UNIQUE (fixture_id, team_id)
);
CREATE TABLE lineup_players (
    lineup_id UUID NOT NULL REFERENCES lineups(lineup_id),
    player_id UUID NOT NULL REFERENCES players(player_id),
    squad_number INTEGER,
    position VARCHAR,
    grid VARCHAR,
    role VARCHAR NOT NULL,
    PRIMARY KEY (lineup_id, player_id, role),
    CHECK (role IN ('STARTING_XI', 'BENCH'))
);
CREATE TABLE team_match_statistics (
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    team_id UUID NOT NULL REFERENCES teams(team_id),
    shots_on_goal DOUBLE, shots_off_goal DOUBLE, total_shots DOUBLE, blocked_shots DOUBLE,
    shots_inside_box DOUBLE, shots_outside_box DOUBLE, fouls DOUBLE, corner_kicks DOUBLE,
    offsides DOUBLE, ball_possession DOUBLE, yellow_cards DOUBLE, red_cards DOUBLE,
    goalkeeper_saves DOUBLE, total_passes DOUBLE, passes_accurate DOUBLE, passes_percentage DOUBLE,
    additional_stats JSON NOT NULL,
    PRIMARY KEY (fixture_id, team_id)
);
CREATE TABLE player_match_statistics (
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    team_id UUID NOT NULL REFERENCES teams(team_id),
    player_id UUID NOT NULL REFERENCES players(player_id),
    minutes INTEGER, number INTEGER, position VARCHAR, rating DOUBLE, captain BOOLEAN, substitute BOOLEAN,
    shots_total INTEGER, shots_on INTEGER, goals INTEGER, goals_conceded INTEGER, assists INTEGER, saves INTEGER,
    passes_total INTEGER, passes_key INTEGER, passes_accuracy DOUBLE, tackles_total INTEGER, blocks INTEGER,
    interceptions INTEGER, duels_total INTEGER, duels_won INTEGER, dribbles_attempts INTEGER,
    dribbles_success INTEGER, dribbles_past INTEGER, fouls_drawn INTEGER, fouls_committed INTEGER,
    yellow_cards INTEGER, red_cards INTEGER, penalties_won INTEGER, penalties_committed INTEGER,
    penalties_scored INTEGER, penalties_missed INTEGER, penalties_saved INTEGER,
    additional_stats JSON NOT NULL,
    PRIMARY KEY (fixture_id, team_id, player_id)
);
CREATE TABLE fixture_completeness (
    fixture_id UUID NOT NULL REFERENCES fixtures(fixture_id),
    component VARCHAR NOT NULL,
    state VARCHAR NOT NULL,
    reason VARCHAR,
    assessed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (fixture_id, component)
);

