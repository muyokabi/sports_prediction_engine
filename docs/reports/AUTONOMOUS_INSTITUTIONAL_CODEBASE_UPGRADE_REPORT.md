# Autonomous Institutional Codebase Upgrade Report

Generated 2026-10-11 (Africa/Nairobi).

## Executive verdict

The repository is materially stronger and the two operator-visible failures are fixed: discovery now runs in principal workflows, and odds ingestion can no longer silently do nothing when its governed scope is absent. A real live acceptance run discovered 1,241 current competitions, collected odds for all six requested fixtures, generated six new fixture predictions (12 retained across runs), reconciled 6/6 terminal fixtures, and wrote a complete HTML report.

The final classification remains **`RESEARCH_ONLY / FAIL_CLOSED`**. This is intentional. The previous Dixon-Coles champion failed the evaluator's aggregate probability-forensics verdict and has been demoted. Fresh candidates were trained, but none passed every promotion gate. Seven prospective odds snapshots are operational proof, not enough market history or settled shadow evidence for real-money actionability.

## Root causes proved

### Why discovery stayed at ten leagues

The provider was not the limiting factor. The production YAML contained ten seed leagues, `football fetch-backfill` always passed that static list to the season catalog, and discovery was exposed only as a specialist command. Consequently, five seasons meant `10 leagues × 5 completed seasons = 50 replay competition-seasons`.

### Why odds were missing

Odds request scopes required a matching `competition_discoveries.universe_state='ACTIONABLE'` row. The table was empty because the principal workflow never ran discovery. `_request_scopes` therefore returned no scopes and the service returned zeroes without a reason or provider call.

### Why “having data” did not guarantee production predictions

The archive contained enough matches to train models, but production selection is evidence-gated. The incumbent's walk-forward report explicitly failed aggregate probability forensics due to material confidence-band miscalibration. Promotion logic checked selected global/fold metrics but did not enforce that explicit verdict or reassess the incumbent. The model could therefore remain champion incorrectly.

## Implemented upgrades

1. `football daily`, and therefore the principal `run`, refreshes competition discovery before current fixture and odds work.
2. Odds ingestion reports `NO_ACTIONABLE_COMPETITION_SCOPE` explicitly and exposes request-scope count.
3. `football fetch-backfill` discovers automatically, then uses a bounded 40-league universe: admitted leagues first, followed by the best observation candidates. This expands historical evidence without equating collection with production actionability.
4. Backfill exposes `--league-limit` and the recovery-only `--no-discovery`; its result states both catalog discovery and selected-universe size.
5. Promotion requires `probability_forensics.passed=true`. The selected governed incumbent is reassessed each cycle and is demoted fail-closed when evidence fails.
6. README now gives a single ordered fresh-clone workflow: migrate/verify, discovery-backed five-season backfill, historical training, then the principal live run. Specialist commands are clearly labelled optional.
7. Regression tests cover explicit empty odds scope, discovery-backed candidate selection, failed probability forensics, and incumbent demotion.

## Post-upgrade warehouse evidence

| Evidence | Value |
|---|---:|
| Discovered competitions / competition seasons | 1,241 / 1,291 |
| Discovery states | 10 actionable; 65 observation; 1,062 discovered; 104 rejected |
| Teams / fixtures / completed | 279 / 19,774 / 17,179 |
| Quality assessed / ML eligible / pending repair | 9,041 / 8,271 / 770 |
| Production fixtures / completed / ML eligible | 3,174 / 584 / 260 |
| Replay seasons / fixtures / completed / ML eligible | 50 / 16,600 / 16,595 / 8,011 |
| Odds snapshots / prices / bookmakers / provider markets | 7 / 30,258 / 10 / 182 |
| Fixtures with odds on target date | 6 of 6 |
| Feature datasets / model runs | 5 / 28 |
| Institutional predictions / opportunities | 12 / 317 |
| Validated competition probability scopes | 60 |
| Active production champions | 0 |

The 1,241 production competition-season rows are catalog knowledge, not 1,241 admitted leagues. Ten remain `ACTIONABLE`; 65 qualified leagues are observation candidates. A normal future `fetch-backfill --past-seasons 5` selects up to 40 governed leagues by default and registers their league-specific completed seasons in replay.

## Live end-to-end acceptance

Command: `sports-engine run --date tomorrow`

- `football.daily` succeeded after 12 minutes 25 seconds: 35 recorded requests, 74 eligible enrichments, 21 quarantines, and six odds snapshots.
- The final requested-date odds pass added one deduplicated snapshot; all six target fixtures have odds.
- Analysis run `853e039b-b608-4bf6-ab70-8d7a72eb651c` completed with six expected and six terminal fixtures.
- The report is `artifacts/reports/2026/10/11/analysis-2026-10-12-2026-10-12-853e039b-b608-4bf6-ab70-8d7a72eb651c.html` (451,043 bytes).
- The report generated research prices and three `SHADOW_ACTIONABLE` watch observations, but no production bet because no candidate passed every champion gate.
- Post-run warehouse integrity passed.

The report's HTML, navigation, fixture records, odds timestamp, and persisted manifest were structurally inspected. Automated visual QA could not be completed: Edge was unavailable, and both Chrome and the in-app browser enforce a policy that blocks local `file:` URLs (the correct Windows URL form `file:///C:/...` was used). No browser-policy workaround was attempted.

## Verification

| Check | Result |
|---|---|
| Full test suite | 194 passed in 63.63 seconds |
| Targeted new regressions | 17 passed |
| Ruff lint | Passed |
| Ruff formatting | Passed after formatting one new test |
| Strict mypy | Passed for 161 source files |
| CLI contract | New discovery and league-limit options rendered correctly |
| Warehouse audit | Read-only audit completed after the live run |
| Warehouse integrity | Passed |
| Pre-change backup | Schema 33; 2,865 files; nine critical table counts verified |

## Remaining limitations

- Historical match data can be backfilled; historical pre-match odds cannot be recreated. Odds and movement evidence must accumulate prospectively.
- Seven snapshots do not establish de-vigged market superiority, closing-price behavior, robust execution edge, or calibration under market regimes.
- There is no production champion because the known incumbent failed probability forensics and fresh candidates remain challengers.
- There are no settled shadow opportunities yet. The system must observe outcomes over time before any return or drawdown claim.
- The 770 repair rows remain excluded rather than imputed.
- DuckDB remains a coordinated single-writer local architecture, not a multi-writer server database.

No known feasible P0 or P1 code correctness defect remains from this audit. The unresolved P1 limitations are evidence deficits and are enforced as abstention conditions.
