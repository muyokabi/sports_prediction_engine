ALTER TABLE prediction_decisions ADD COLUMN applicability_state VARCHAR DEFAULT 'UNASSESSED';
ALTER TABLE prediction_decisions ADD COLUMN applicability_reason_codes JSON DEFAULT '[]';

