# Repository guardrails for future AI and engineering work

Read these files before changing data, model-promotion, pricing, or decision logic:

- `docs/audits/CURRENT_SYSTEM_BASELINE.md`
- `docs/audits/IMPROVEMENT_REGISTER.md`
- `docs/research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md`
- `docs/reports/CURRENT_IMPLEMENTATION_STATUS.md`
- `docs/operations/RUNBOOK.md`

Non-negotiable invariants:

1. The engine must keep producing fixture probabilities and fair prices when a qualified score model exists. `PRODUCTION_ACTIONABLE` is a separate real-money governance label; withholding that label must not suppress research predictions.
2. API-Football is the sole integrated reference-odds provider. Research its documented coverage and retention limits before changing data requirements. Do not invent unavailable historical odds, injuries, or lineups.
3. Treat results and prior completed-match facts as `RECONSTRUCTABLE_EVENT_TIME`. Treat pre-match odds, injuries, expected/confirmed lineups, and movement as `OBSERVED_POINT_IN_TIME` unless the ledger actually captured them before kickoff.
4. Preserve explicit `UNKNOWN` values. Never replace missing provider data with neutral probabilities, fabricated observations, or silently fitted priors in a decision-critical path.
5. Never restore an arbitrary quote-age veto. Expose reference age and provenance; keep model fair odds, API-Football reference odds, minimum acceptable execution odds, and unknown operator odds distinct.
6. A model that lacks the historical point-in-time market baseline required by policy may still issue research prices, but it must not receive a real-money champion/actionability label. Do not weaken this fail-closed gate to manufacture predictions or bets.
7. Competition collection state, model applicability, market-family qualification, calibration, uncertainty, and risk gates are independent. Collection admission alone never implies actionability.
8. Market-family roles are explicit. Qualification for `MATCH_ODDS` must not leak into BTTS, totals, handicaps, team totals, correct score, corners, cards, or player markets.
9. Do not mutate immutable historical predictions, model artifacts, or evaluation evidence. Use migrations for schema changes and create/verify a backup before production-ledger mutation.
10. Run chronological—not random—evaluation. Substantial quantitative changes require research, a stated hypothesis, an untouched temporal test, regression coverage, and a documented result.
11. Every newly built feature dataset must retain its feature-quality sidecar. All-null/constant provider-dependent columns may remain explicit in the dataset, but must not be represented as informative fitted features.
12. Keep the improvement register current. Record material discoveries, evidence, fixes, tests, unresolved limitations, and whether each limitation blocks real-money actionability.
13. Provider access probes must use a season belonging to the same competition being queried. Never pair a global maximum catalog season with a hard-coded league; future-dated tournament rows make that inference invalid.

Do not claim the platform is safe for real-money decision support merely because tests pass or predictions exist. Reconcile claims against the production warehouse and current persisted artifacts.
