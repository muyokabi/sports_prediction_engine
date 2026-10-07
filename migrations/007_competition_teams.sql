CREATE TABLE competition_season_teams (
    competition_season_id UUID NOT NULL REFERENCES competition_seasons(competition_season_id),
    team_id UUID NOT NULL REFERENCES teams(team_id),
    first_observed_at TIMESTAMPTZ NOT NULL,
    last_observed_at TIMESTAMPTZ NOT NULL,
    source_raw_path VARCHAR NOT NULL,
    PRIMARY KEY (competition_season_id, team_id)
);
