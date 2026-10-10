-- Migration 027 predates explicit state writes and gave pre-governance rows a
-- permissive label through the column default. Existing rows have no evidence
-- of passing the new gates, so quarantine only those that lack applicability.
UPDATE institutional_opportunities AS opportunity
SET governance_state = 'RESEARCH_ONLY'
WHERE NOT EXISTS (
    SELECT 1
    FROM prediction_applicability AS applicability
    WHERE applicability.prediction_id = opportunity.prediction_id
);

ALTER TABLE institutional_opportunities
ALTER COLUMN governance_state SET DEFAULT 'RESEARCH_ONLY';
