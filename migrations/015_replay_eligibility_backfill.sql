-- Reuse already-persisted coverage facts from audits performed before the
-- replay_eligible column existed; no provider requests are needed.
UPDATE competition_seasons
SET replay_eligible = true
WHERE ledger_mode = 'replay'
  AND json_extract_string(coverage, '$.fixtures.events') = 'true'
  AND json_extract_string(coverage, '$.fixtures.lineups') = 'true'
  AND json_extract_string(coverage, '$.fixtures.statistics_fixtures') = 'true'
  AND json_extract_string(coverage, '$.fixtures.statistics_players') = 'true';
