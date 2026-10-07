ALTER TABLE competitions ADD COLUMN source_raw_path VARCHAR;
ALTER TABLE competitions ADD COLUMN retrieved_at TIMESTAMPTZ;
ALTER TABLE competition_seasons ADD COLUMN source_raw_path VARCHAR;
ALTER TABLE competition_seasons ADD COLUMN retrieved_at TIMESTAMPTZ;
ALTER TABLE teams ADD COLUMN code VARCHAR;
-- DuckDB cannot add a column-level foreign key through ALTER TABLE. Venue identity
-- is still canonical and repository writes validate it before assigning this UUID.
ALTER TABLE teams ADD COLUMN home_venue_id UUID;
ALTER TABLE teams ADD COLUMN source_raw_path VARCHAR;
ALTER TABLE teams ADD COLUMN retrieved_at TIMESTAMPTZ;
ALTER TABLE players ADD COLUMN source_raw_path VARCHAR;
ALTER TABLE players ADD COLUMN retrieved_at TIMESTAMPTZ;

CREATE TABLE squad_snapshots (
    snapshot_id UUID PRIMARY KEY,
    competition_season_id UUID NOT NULL REFERENCES competition_seasons(competition_season_id),
    team_id UUID NOT NULL REFERENCES teams(team_id),
    observed_at TIMESTAMPTZ NOT NULL,
    source_raw_path VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    UNIQUE (competition_season_id, team_id, observed_at, content_hash)
);

CREATE TABLE squad_players (
    snapshot_id UUID NOT NULL REFERENCES squad_snapshots(snapshot_id),
    player_id UUID NOT NULL REFERENCES players(player_id),
    squad_number INTEGER,
    position VARCHAR,
    PRIMARY KEY (snapshot_id, player_id)
);
