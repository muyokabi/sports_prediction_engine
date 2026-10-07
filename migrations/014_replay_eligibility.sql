ALTER TABLE competition_seasons ADD COLUMN replay_eligible BOOLEAN;
UPDATE competition_seasons SET replay_eligible = false WHERE replay_eligible IS NULL;
