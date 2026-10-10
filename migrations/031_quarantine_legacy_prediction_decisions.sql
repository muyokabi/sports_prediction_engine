-- Decisions created before migration 030 have no reconstructable persisted
-- fixture-applicability assessment. Preserve their probability records but
-- quarantine the decision label rather than inheriting historical optimism.
UPDATE prediction_decisions
SET state = 'NO_BET',
    applicability_state = 'OUT_OF_DOMAIN',
    applicability_reason_codes = '["PRE_GOVERNANCE_LINEAGE_UNAVAILABLE"]'
WHERE applicability_state = 'UNASSESSED';

ALTER TABLE prediction_decisions
ALTER COLUMN applicability_state SET DEFAULT 'OUT_OF_DOMAIN';

ALTER TABLE prediction_decisions
ALTER COLUMN applicability_reason_codes SET DEFAULT '["TRAINING_LINEAGE_UNAVAILABLE"]';

