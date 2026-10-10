UPDATE shadow_opportunities
SET state = 'SHADOW_REJECTED'
WHERE state = 'SHADOW_ACTIONABLE'
  AND opportunity_id IN (
      SELECT opportunity_id
      FROM institutional_opportunities
      WHERE canonical_market = 'ASIAN_HANDICAP'
  );

UPDATE institutional_opportunities
SET governance_state = 'RESEARCH_VALUE_SIGNAL', decision = 'NO_BET'
WHERE governance_state = 'SHADOW_ACTIONABLE'
  AND canonical_market = 'ASIAN_HANDICAP';
