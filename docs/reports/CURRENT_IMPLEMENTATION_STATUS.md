# Current Implementation Status

Verified 2026-10-11 (Africa/Nairobi).

## Status

`RESEARCH_ONLY / FAIL_CLOSED`

The system now discovers the provider catalog automatically in its principal and historical workflows. The current catalog contains 1,241 competitions: 10 actionable, 65 observation candidates, 1,062 discovered, and 104 rejected. Historical backfill selects up to 40 governed leagues by default; it does not auto-promote observation leagues.

The warehouse contains 19,774 fixtures, 17,179 completed fixtures, and 8,271 ML-eligible detailed matches. The latest live run covered all six requested fixtures, stored API-Football references for all six, generated six new fixture predictions, priced 275 selections, and produced three shadow-only watch rows. Across retained runs the warehouse contains 12 institutional predictions and 317 opportunity rows.

There is no production champion. The prior incumbent was demoted after its explicit probability-forensics failure was correctly enforced. Fresh candidates remain challengers. Therefore every current price is research or shadow evidence, not a real-money recommendation.

## Normal commands

For a fresh clone, follow the ordered sequence in `README.md`: migrate and verify, run the discovery-backed five-season backfill, train historically, then use `sports-engine run --date tomorrow`. For ongoing operation, the principal `run` command handles discovery, current data, odds, due learning, governance, pricing, and reporting.

## Evidence

- Final audit: `docs/reports/AUTONOMOUS_INSTITUTIONAL_CODEBASE_UPGRADE_REPORT.md`
- Pre-upgrade snapshot: `docs/audits/CURRENT_SYSTEM_BASELINE.md`
- Open/closed findings: `docs/audits/IMPROVEMENT_REGISTER.md`
- Satisfaction boundary: `docs/reports/CODEBASE_SATISFACTION_STATEMENT.md`
