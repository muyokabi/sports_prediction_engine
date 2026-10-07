ALTER TABLE provider_capabilities ADD COLUMN subscription_end VARCHAR;
ALTER TABLE provider_capabilities ADD COLUMN daily_remaining INTEGER;
ALTER TABLE provider_capabilities ADD COLUMN minute_limit INTEGER;
ALTER TABLE provider_capabilities ADD COLUMN minute_remaining INTEGER;
