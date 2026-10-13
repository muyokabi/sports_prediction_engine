-- Promotion reassessment used to overwrite the only persisted assessment and
-- role timestamp.  Preserve future assessment evidence as append-only rows and
-- retain the mutable role table solely as the current-role projection.
CREATE TABLE model_promotion_assessments_v2 (
    assessment_id UUID PRIMARY KEY,
    model_version VARCHAR NOT NULL,
    model_type VARCHAR NOT NULL,
    market_family VARCHAR NOT NULL,
    policy_version VARCHAR NOT NULL,
    state VARCHAR NOT NULL,
    reason_codes JSON NOT NULL,
    gate_results JSON NOT NULL,
    evaluation_path VARCHAR,
    assessed_at TIMESTAMPTZ NOT NULL,
    CHECK (state IN ('PROMOTED','WITHHELD','REJECTED'))
);

INSERT INTO model_promotion_assessments_v2
SELECT * FROM model_promotion_assessments;

DROP TABLE model_promotion_assessments;
ALTER TABLE model_promotion_assessments_v2 RENAME TO model_promotion_assessments;

CREATE TABLE model_market_role_events (
    event_id UUID PRIMARY KEY,
    market_family VARCHAR NOT NULL,
    role_name VARCHAR NOT NULL,
    model_version VARCHAR NOT NULL,
    model_type VARCHAR NOT NULL,
    state VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    assessment_id UUID,
    occurred_at TIMESTAMPTZ NOT NULL,
    evidence JSON NOT NULL DEFAULT '{}',
    CHECK (state IN ('CHAMPION','CHALLENGER','RESEARCH_ONLY','REJECTED')),
    CHECK (event_type IN ('PROMOTED','WITHHELD','SUPERSEDED','MIGRATED_CURRENT_STATE'))
);

-- The current projection is known, but its overwritten predecessor is not.
-- Seed only what can still be proven and label that provenance explicitly.
INSERT INTO model_market_role_events
SELECT uuid(), market_family, role_name, model_version, model_type, state,
       'MIGRATED_CURRENT_STATE', NULL, selected_at,
       json_object('source', 'model_market_roles', 'history_complete', false)
FROM model_market_roles;

-- Three legacy production labels survived a later champion demotion, but the
-- overwritten role record cannot prove their decision-time role.  Preserve the
-- immutable prediction/price evidence and fail the unverifiable action label
-- closed with an explicit reason.
UPDATE institutional_opportunities AS opportunity
SET governance_state = 'RESEARCH_VALUE_SIGNAL',
    decision = 'NO_BET',
    reason_codes = to_json(list_append(
        json_transform(reason_codes, '["VARCHAR"]'),
        'LEGACY_GOVERNANCE_EVENT_HISTORY_UNAVAILABLE'
    ))
WHERE governance_state = 'PRODUCTION_ACTIONABLE'
  AND NOT EXISTS (
      SELECT 1
      FROM model_market_role_events event
      JOIN institutional_predictions prediction
        ON prediction.prediction_id = opportunity.prediction_id
      WHERE event.model_version = prediction.fundamental_model_version
        AND event.market_family = opportunity.canonical_market
        AND event.role_name = opportunity.canonical_market || '_CHAMPION'
        AND event.state = 'CHAMPION'
        AND event.occurred_at <= opportunity.created_at
  );
