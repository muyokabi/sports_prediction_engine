ALTER TABLE competition_seasons ADD COLUMN provider_accessible BOOLEAN;
ALTER TABLE competition_seasons ADD COLUMN access_reason VARCHAR;
UPDATE competition_seasons SET provider_accessible = true WHERE provider_accessible IS NULL;
