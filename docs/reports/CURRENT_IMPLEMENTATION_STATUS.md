# Current Implementation Status

Verified 2026-10-13 (Africa/Nairobi).

## Status

`RESEARCH_AND_SHADOW / NOT_REAL_MONEY_APPROVED`

The engine produces probabilities and fair prices. The final live acceptance analyzed 19/19 fixtures, associated API-Football references to all 19, and persisted 837 prices across match odds, BTTS, and total goals. There were 324 research value signals and 513 research-only prices; none was labeled production-actionable.

There is no active market-family champion. The prior Dixon-Coles champion was demoted because the configured significant market-outperformance requirement had zero point-in-time baseline rows. It remains available as a qualified research score model, so absence of a real-money role does not suppress fixture predictions.

The warehouse contains 1,241 competitions, 876 teams, 58,670 fixtures, 55,732 completed fixtures, 18,767 eligible quality assessments, 76 prospective odds snapshots over 38 fixtures, 161 institutional predictions, and 34 unsettled shadow observations.

## Normal command

Use `sports-engine run --date today` or `sports-engine run --date tomorrow`. The principal workflow handles preflight, catch-up, discovery, current data, scoped odds, due learning, governance, prediction, reporting, and integrity.

Unavailable historical odds, injuries, and lineups remain explicit unknowns. Do not weaken gates to create betting recommendations. Continue prospective collection until market-baseline and settled-shadow evidence reach the configured requirements.

Production promotion now also requires digest-backed integrity evidence for the model artifact and any calibrator. Legacy hashless pickle artifacts remain available only as trusted-local research history. The 2026-10-13 reassessment withheld all 49 candidates; no market-family champion was created.

## Durable evidence

- Future-agent guardrails: `AGENTS.md`
- Pre-upgrade snapshot: `docs/audits/CURRENT_SYSTEM_BASELINE.md`
- Open/closed findings: `docs/audits/IMPROVEMENT_REGISTER.md`
- Research record: `docs/research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md`
- Final audit: `docs/reports/AUTONOMOUS_INSTITUTIONAL_CODEBASE_UPGRADE_REPORT.md`
- Satisfaction boundary: `docs/reports/CODEBASE_SATISFACTION_STATEMENT.md`
