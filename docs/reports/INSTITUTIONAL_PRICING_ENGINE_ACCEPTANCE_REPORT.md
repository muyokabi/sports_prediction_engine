# Institutional Pricing Engine Acceptance Report

> Historical evidence only. See `docs/reports/CURRENT_IMPLEMENTATION_STATUS.md` for the current classification.

Report date: 2026-10-08 (Africa/Nairobi)

Overall state: **IN PROGRESS — CORE PRICING VERIFIED OFFLINE; MODEL EVIDENCE ACCUMULATING**

## Implemented and verified offline

- Dynamic-tail independent-Poisson score distribution with normalized mass and reported omitted probability.
- Existing Poisson and Dixon-Coles models now use the dynamic grid without replacing their fitted parameters.
- Coherent 1X2, double chance, DNB, BTTS, totals, team totals, correct-score, and Asian-handicap pricing primitives.
- Full-win, half-win, push, half-loss, and full-loss settlement for whole, half, and quarter lines.
- Fair odds, target-EV minimum odds, and expected-return calculations over complete settlement distributions.
- Proportional, power, and Shin-style de-vig methods.
- Exact-ID/name API-Football market taxonomy with unknown and mismatched markets explicitly disabled/unsupported.
- Intervening-fixture dependency assessment and distinct model-state versus market-price staleness states.
- Timezone-aware today, tomorrow, ISO-date, and bounded-range parsing.
- Migration 022 for governed taxonomy, analysis manifests, immutable institutional prediction metadata, source snapshots,
  engine independence, settlement distributions, and per-engine price storage.
- `sports-engine run --date ... --days ...` full-universe reconciliation and standalone HTML audit reporting.
- HTML escaping and explicit terminal state for every fixture.

## Production evidence retained

- Odds source: API-Football only.
- Provider: production-qualified Pro subscription based on persisted controlled qualification evidence.
- Admitted competitions: 10.
- Production schedule fixtures: 3,174 at the prior qualification checkpoint.
- Eligible detailed fixtures: 276; configured training minimum: 500.
- Canonical odds: 13 append-only snapshots for eight admitted fixtures at the prior qualification checkpoint.
- Current model actionability: no qualified institutional dual-engine/fused price; wagering remains disabled by evidence gates.

## Verification results

- Focused institutional pricing tests: 12 passed.
- Full offline suite after implementation: 112 passed in 36.72 seconds on the final working tree.
- Ruff lint and format: passed.
- Strict mypy: passed across 148 source files.
- Migration clean-from-zero/idempotency: passed through migration 022; production ledger migrated to schema 22.
- Production warehouse integrity audit: passed after migration and acceptance runs.
- Live API calls used for this stage: one successful `/status` refresh. No odds or fixture calls were repeated.
- Refreshed provider status: Pro, active, production/replay access available, 7,275/7,500 daily requests remaining and
  299/300 minute requests remaining at observation time.
- Two initial sandboxed `/status` attempts failed locally at DNS resolution and were recorded with no HTTP status; the single
  approved network attempt then returned HTTP 200. The failed attempts did not reach API-Football or consume provider quota.
- Today run (2026-10-08): complete, 0 expected fixtures and 0 terminal fixtures.
- Tomorrow run (2026-10-09): complete, 8 expected and 8 explicitly `NO_QUALIFIED_MODEL`.
- Seven-day run (2026-10-09 through 2026-10-15): complete, 90 expected and 90 explicitly `NO_QUALIFIED_MODEL`.
- Future dependency run (2026-10-16): complete, 6 expected and all 6 `BLOCKED_BY_INTERVENING_FIXTURE`.
- Observed provider taxonomy persisted: 174 market IDs (9 supported core score markets, 4 research-only secondary
  markets, and 161 explicitly unsupported rather than guessed).
- Representative HTML report:
  `artifacts/reports/analysis-2026-10-09-2026-10-09-9c9e8391-bcc5-498f-b82a-4c1160a92ff0.html`.

## Not yet complete

- A production-qualified independently versioned fundamental model fit and evaluation run.
- ML challenger retraining after the 500-row evidence gate is reached.
- Chronologically learned and versioned fusion weights.
- Historical de-vig method selection by market.
- Persisted best/worst quote, dispersion, and line-movement services across all governed markets.
- Correlation-aware portfolio construction beyond existing exposure/count caps.
- Outcome attachment and rolling institutional engine/market/ROI monitoring tables.
- Drift-trigger workflows and league-expansion scoring reports.
- Fresh live odds pagination/coverage collection inside the new orchestration command; existing canonical odds evidence was
  retained and no quota-heavy collection was repeated in this pass.
- Full fixture-detail and top-opportunities report sections; these must remain empty rather than fabricated until prices qualify.

No edge, profitability, or readiness to recommend wagers is claimed.
