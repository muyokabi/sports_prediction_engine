# Autonomous Institutional Codebase Upgrade Report

Generated 2026-10-12 and independently re-audited through 2026-10-14 (Africa/Nairobi).

Latest independent re-audit: 2026-10-14 (Africa/Nairobi). See the addendum at the end of this report for schema 34, append-only governance, end-to-end runtime repairs, and the Top Research report view.

## Executive verdict

The platform is materially stronger and still performs its primary job: it produces fixture probabilities and fair prices. The final live acceptance analyzed all 19 requested fixtures and persisted 19 predictions and 837 prices. The audit removed the real-money label from the current model because its promotion record required significant market outperformance while containing zero historical point-in-time market-baseline rows.

Final classification: **`RESEARCH_AND_SHADOW / NOT_REAL_MONEY_APPROVED`**.

- Suitable for probability research: **yes**.
- Suitable for prospective shadow observation: **yes**.
- Suitable for real-money decision support: **no**. The final provider ledger has only 55 fixtures with odds, seven settled shadow observations, no active champion, and no candidate has the 200 point-in-time market rows required by policy.

Prediction availability is not the same as evidence of a tradable edge. Withholding a market role does not suppress probabilities or fair odds.

## Starting state and principal correction

At the pre-upgrade snapshot the warehouse held 58,650 fixtures, 18,767 eligible assessments, 33 odds snapshots over 22 fixtures, 56 institutional predictions, and one `MATCH_ODDS` champion. Three persisted opportunities were labeled `PRODUCTION_ACTIONABLE`.

The champion's promotion evidence showed `market_baseline.available=false`, `rows=0`, and `passed=true`, even though `require_significant_market_outperformance=true`. The permissive `when_available` mode had silently bypassed a policy that could not logically be evaluated. This was a feasible P1 defect.

The correction makes a missing point-in-time market baseline fail closed whenever significant market outperformance is required. Production configuration now uses `market_baseline_mode: required`. A production reassessment withheld all 39 candidates and demoted the incumbent with `INSUFFICIENT_POINT_IN_TIME_MARKET_BASELINE`. Historical prediction records were not rewritten.

## Research applied

The detailed research log is in `docs/research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md`. Material sources included:

- API-Football's official getting-started, full-fixture collection, quota optimization, and multi-ID documentation. Provider odds are commonly available shortly before matches, retained for a short window, and historical lineups/injuries are not universally reconstructable. This justified prospective accumulation and explicit unknowns rather than synthetic backfill.
- Dixon and Coles (1997) for low-score football dependence and time weighting.
- Gneiting and Raftery (2007) for proper scoring rules.
- Karlis and Ntzoufras (2003) for bivariate-Poisson challenger context.
- Official scikit-learn calibration guidance, CatBoost and LightGBM objectives, and DuckDB concurrency documentation.
- Primary work on blocked time-series validation, betting-market efficiency, and Kelly sizing under estimation uncertainty.

No more complex score model was promoted merely because it is theoretically richer. Available chronological evidence supports retaining Dixon-Coles as the research pricing core while collecting the missing prospective market evidence.

## Audit findings

The authoritative finding-by-finding record is `docs/audits/IMPROVEMENT_REGISTER.md`.

Confirmed and fixed:

- P1 market-baseline bypass in automated promotion.
- P1 feature-evidence error where IEEE `NaN` was counted as observed rather than missing.
- P1 multiclass-calibration fallback that silently replaced zero calibrated mass with a uniform one-third probability vector.
- Incomplete feature-quality evidence: every newly built dataset now receives a sidecar covering all candidate features, and model manifests record included/excluded columns and reasons.
- P2 provider-access diagnostic error: Doctor and capability reporting now select an exact competition/season mapping instead of pairing league 39 with the catalog-wide maximum season. The corrected live probe used league 39 / season 2026, returned 20 teams, and passed. Daily collection, bootstrap, odds, analysis, and rollover were audited and already preserve exact provider pairs.

Confirmed safe through forensics:

- Duplicate xG/probability clusters are explicit `PRIOR_ONLY` outputs for unseen teams, with `GLOBAL_PRIOR_SUBSTITUTION` and `actionability_qualified=false`; they are not hidden actionable estimates.
- BTTS and total-goals probabilities do not inherit the `MATCH_ODDS` role. After demotion every family was research-only or a research value signal.
- Unknown-team injury rows come from the provider's global date response; they are raw-preserved and ignored outside the local fixture universe rather than converted to false absences.
- The observed 182-market taxonomy remains explicitly mapped. Only deterministic, score-derived families are priced; unsupported corner/card/player semantics are not guessed.

The calibration fallback now rejects non-finite, negative, or zero-mass output and verifies the normalized simplex instead of inventing neutral probabilities. No known feasible P0 or P1 correctness defect remains after re-audit. Evidence deficits remain and block real-money approval.

## Data and provider reality

| Measure | Final value |
|---|---:|
| Competitions / competition seasons | 1,241 / 1,443 |
| Competition states | 10 actionable; 68 observation; 1,061 discovered; 104 rejected |
| Teams | 1,046 |
| Fixtures / completed | 69,542 / 60,815 |
| Production fixtures / completed | 14,086 / 5,667 |
| Replay fixtures / completed | 55,456 / 55,148 |
| Quality-assessed `ML_ELIGIBLE` fixtures | 23,850 |
| Odds snapshots / fixtures / prices | 106 / 55 / 315,960 |
| Bookmakers / observed provider markets | 10 / 182 |
| Feature datasets / model runs | 13 / 71 |
| Institutional predictions / opportunities | 207 / 8,520 |
| Shadow observations / settled | 34 / 7 |

API-Football is the sole integrated reference provider. Official documentation and the ledger show why historical match facts are far more complete than point-in-time odds, injuries, and lineups. The system now treats unavailable time-sensitive inputs as `UNKNOWN`; it does not manufacture them or spend quota attempting impossible reconstruction.

## Models, evaluation, calibration and applicability

The research score core used by the final re-audit is `dixon-coles-20261012T184807737791Z-8711396c`, trained on 17,179 observations through 2026-10-09. Its untouched test metrics were log loss 1.00665, Brier 0.60221, RPS 0.20515, and ECE 0.02332. Four walk-forward folds covered 6,776 test rows; upper uncertainty bounds remained within the configured probability-quality limits.

Those scores justify research pricing, not market superiority. Market-baseline rows were zero. The model now has no champion role, and there is no active production market champion. Fixture applicability remains persisted with exact training lineage, effective team history, prior fractions, competition representation, cutoff, and explicit states such as `PARTIALLY_POOLED` or `PRIOR_ONLY`.

The previously stored production labels are immutable historical evidence generated under the superseded promotion policy. They do not represent current approval.

## ML and feature quality

The champion-lineage dataset has 17,179 rows and 168 numeric/boolean candidate columns. Model-specific selection retained 155 and excluded 13 all-null or constant columns. Nineteen candidates were at least 50% missing and nine were at least 90% missing.

The all-null fields were the three bookmaker fair probabilities, four injury/availability measures, and two lineup-strength measures. Their known-state flags were constant false. These fields remain in the dataset so `UNKNOWN` is auditable, but they are not represented as fitted information. `NaN` and `null` are now treated consistently by feature selection, quality manifests, and model-evidence missingness gates.

Logistic, CatBoost, and LightGBM artifacts remain immutable challengers with full-refit and lineage metadata. No ML model is assigned a production market role. More ablation work is appropriate only after prospective time-sensitive features acquire non-zero coverage.

## Markets and opportunity funnel

The live acceptance run `137f30a3-8c64-48f5-ba24-ebf4f2db319d` used current API-Football data for 2026-10-13:

| Funnel stage | Count |
|---|---:|
| Requested fixtures | 19 |
| Terminal analyzed fixtures | 19 |
| Fixtures with reference odds | 19 |
| Persisted predictions | 19 |
| Match-odds prices | 57 |
| BTTS prices | 38 |
| Total-goals prices | 742 |
| All prices/opportunities | 837 |
| Research value signals | 324 |
| Research-only prices | 513 |
| Shadow actionable | 0 |
| Production actionable | 0 |

The report preserves model fair odds, API-Football reference odds, minimum acceptable execution odds, reference age/provenance, and unknown actual operator price. No arbitrary quote-age veto was introduced. A large discrepancy is not automatically an executable edge.

## Risk and actionability

Minimum acceptable odds remain model-bound and include the configured 2% base required return plus validated uncertainty adjustment when a role exists. Missing role, calibration, applicability, market-family, competition, uncertainty, margin, or risk evidence prevents production actionability. Fractional Kelly and exposure caps therefore cannot turn an unqualified signal into a recommendation.

Seven settled shadow observations is still an explicit empirical limitation, not a credible validation sample. No durable ROI, drawdown, bankroll-survival, or closing-line advantage claim is made.

## Operations, recovery and performance

The normal command remains `sports-engine run --date today|tomorrow`. It performs preflight, discovery/catch-up, enrichment, prospective odds and injuries, due learning, promotion assessment, pricing, persistence, report generation, and integrity checks.

The final live run used the Pro account with thousands of daily calls still available, consumed only the calls required for current discovery/fixtures/scoped odds/injuries, associated all target odds, and completed. A preceding restricted-network DNS failure was persisted as `PROVIDER_UNAVAILABLE`; retry with network access completed normally, demonstrating explicit failure classification rather than partial silent success.

The 2026-10-13 re-audit repeated live connectivity and current collection. Doctor passed on the Pro plan, scoped odds were fetched for five admitted league-season pairs, the injury feed returned 286 rows, and the prospective ledger advanced to 57 snapshots across 38 fixtures. The desktop execution wrapper twice lost its elevated child after provider writes; the application recovered both abandoned `football.daily` rows as `INTERRUPTED`. A deliberate restricted-network retry was recorded as `PROVIDER_UNAVAILABLE`, and a repository-local offline analysis against the freshly collected ledger then completed normally. This is execution-environment evidence, not a fabricated fully live completion claim.

DuckDB remains appropriate for coordinated local operation and a single writer. It is not a multi-writer service database; a future API must enforce a writer boundary or migrate deliberately.

## Reporting

The final live acceptance HTML is:

`artifacts/reports/2026/10/12/analysis-2026-10-13-2026-10-13-137f30a3-8c64-48f5-ba24-ebf4f2db319d.html`

The premium template was then regenerated from the same persisted target-date evidence without additional provider calls:

`artifacts/reports/2026/10/12/analysis-2026-10-13-2026-10-13-9362dc41-e9ab-441f-9c5f-76820e492f91.html`

The final 2026-10-13 re-audit report is:

`artifacts/reports/2026/10/13/analysis-2026-10-13-2026-10-13-ff874af0-50c5-45ec-b64b-c8d18a72f206.html`

It reconciles 19 processed manifests: 18 `ANALYZED` fixtures and one explicit `STARTED` exclusion because kickoff had passed while the provider status still read `NS`. The run persisted 18 predictions, 791 prices/opportunities, reference odds for all 18 predicted fixtures, and zero production or shadow candidates.

It adds animated ambient depth, decision and market-family visualizations, probability micro-bars, sticky navigation, searchable/filterable market rows, keyboard navigation, responsive layouts, accessible focus states, and reduced-motion support. CLI, report manifest, and warehouse reconcile at 19 expected, 19 terminal, 19 predictions, and zero production candidates. Automated structure tests pass. The browser connector blocked local-file/localhost inspection under its URL policy, so manual visual sign-off remains explicitly recommended rather than falsely claimed.

## Verification

| Check | Result |
|---|---|
| Focused report/pricing tests | 14 passed after the premium template change |
| Full test suite | 210 passed using a repository-local pytest temp directory after the hashless-artifact and tampered-calibrator promotion regressions |
| Ruff | Passed |
| Strict mypy | Passed for 162 source files |
| Migrations | Schema 33/current; idempotent rerun applied none |
| Warehouse integrity | Passed after final live acceptance and report regeneration |
| Pre-change backup | Verified: schema 33, 13,847 files, nine critical table counts |
| Offline acceptance | 19/19 fixtures; 19 predictions; 707 prices; zero production labels |
| Live acceptance | 19/19 fixtures; 19 references; 19 predictions; 837 prices; zero production labels |
| 2026-10-13 re-audit acceptance | Live provider collection succeeded; fresh-ledger analysis processed 19/19 manifests, wrote 18 predictions and 791 prices, and emitted zero production labels |
| Final offline acceptance after artifact gate | Analysis `a8735c81-39c6-4612-9e33-1122ee291f30` processed 12/12 fixtures, priced 519 selections across three families, retained references for 11 fixtures, and emitted zero production or shadow labels |
| Artifact-integrity governance | Inventory: 65 manifests, 10 legacy model manifests without hashes, 32 calibrators, four without calibrator hashes. A verified schema-33 backup containing 13,930 files preceded production reassessment; all 49 candidates were withheld and eight legacy assessed artifacts received `ARTIFACT_INTEGRITY_NOT_VERIFIED`. |

## Remaining limitations

- Historical pre-match odds, injuries, expected lineups, and movement cannot be reconstructed when the provider did not retain or deliver them. Market evidence must accumulate prospectively.
- Only 55 fixtures currently have odds and seven shadow observations are settled. This remains far too thin for real-money approval.
- There is no active market-family champion. The qualified score model remains a research pricing core.
- Injury/lineup features have no historical training coverage; match/player statistics are only partially covered.
- Thirty-six thousand-plus completed replay fixtures are score-only/unassessed for detailed packages. Score models can use the results; ML detail coverage remains explicit.
- The present report prices score-derived BTTS and totals, but they have no independently promoted family champion.
- DuckDB requires coordinated single-writer operation.
- Legacy local pickle artifacts without hashes remain available only for trusted-local research compatibility. The production promotion gate now requires verified model and calibrator digests, and no pickle may be accepted from an untrusted source.

The correct next step is continued daily prospective collection and settlement, not lowering gates to manufacture bets.

## Independent re-audit addendum — 2026-10-14

### Outcome

The platform remains **`RESEARCH_AND_SHADOW / NOT_REAL_MONEY_APPROVED`**. It produces research probabilities and fair prices, now with a concise Top Research view, while retaining zero active champions and zero production-actionable labels. No unresolved feasible P0/P1 defect was found after the repairs and final verification below.

### Starting evidence and backup

This pass began against the schema-33 production warehouse with 69,542 fixtures, 23,850 ML-eligible quality assessments, 161 institutional predictions, and 6,496 opportunities. Integrity failed because three completed historical opportunities were still labelled `PRODUCTION_ACTIONABLE`, while reassessment had overwritten the role projection and promotion assessment needed to prove their champion status at creation time.

Before mutation, the warehouse and associated project evidence were copied to `artifacts/backups/2026-10-14-pre-append-only-governance/`. The manifest verified schema 33, 14,648 files, byte hashes, the applied migration prefix, nine critical table counts, and the exact pre-existing integrity findings.

### Repairs

1. Migration 034 replaces mutable promotion-assessment history with append-only assessments, adds append-only `model_market_role_events`, and seeds the current projection with an explicit incomplete-history marker. New reassessments append rather than overwrite.
2. Integrity validates production governance point in time: the latest role event, calibration, and competition scope must all have existed at or before the opportunity was created. Three legacy labels without provable history were changed to `RESEARCH_VALUE_SIGNAL / NO_BET` with reason `LEGACY_GOVERNANCE_EVENT_HISTORY_UNAVAILABLE`; their underlying immutable predictions and prices were preserved.
3. Shadow settlement now selects the latest quote whose collection time and effective provider timestamp are both pre-kickoff. This removed a crash caused by querying a nonexistent column.
4. Performance rollups use an explicit named-column upsert, removing a 22-value/21-column runtime mismatch discovered only in end-to-end execution.
5. Machine-readable football quality output is ASCII-safe and unstyled, avoiding a Windows legacy-code-page Unicode failure without altering the data.
6. Backup verification can now attest a faithful pre-migration, known-bad source state rather than incorrectly requiring the state already to match the newest schema and pass integrity.

### Research ranking requested by the operator

The generated HTML contains a separate `Top Research` tab and section governed independently from production promotion. Admission requires HIGH/MEDIUM applicability, validated calibration and competition probability scope, adequate bookmaker breadth, no extreme model–market disagreement, positive calculable reference EV, and a persisted API-Football quote at or above provisional minimum odds. Missing champion or historical market-baseline approval remains visible but does not alone suppress an otherwise qualified research row. The section selects at most one market per fixture and is never padded. Ranking is lexicographic: applicability, fewer remaining warnings, normalized price cushion above the settlement-aware minimum odds, reference EV, then model probability. It displays fair/minimum/reference odds, quote provenance, valid-observation count, the bookmaker-breadth gate, EV, robust/execution edge, minimum-odds basis, validated uncertainty state, applicability, governance, and gate reasons. A quality funnel exposes the leading blockers instead of silently returning an empty or padded table. The initial probability-minus-policy-adjustment “confidence index” was removed because the adjustment is not a probability interval and can be zero when unvalidated.

### Final acceptance evidence

Offline analysis `8116e66f-d46c-47b0-ad9a-8abb1103de88` processed 12/12 fixtures for 2026-10-14, wrote 24 predictions and 1,038 prices/opportunities across score-derived families, retained reference odds for 11 fixtures, and emitted zero production or shadow labels. Its regenerated report has a 29-column Top Research contract but correctly emits no shortlisted row: every available candidate is `PRIOR_ONLY` or `OUT_OF_DOMAIN`, so displaying ten as highly reliable would fabricate evidence. It is stored at:

`artifacts/reports/2026/10/14/analysis-2026-10-14-2026-10-14-8116e66f-d46c-47b0-ad9a-8abb1103de88.html`

The resulting schema-34 ledger contains 185 predictions and 7,534 opportunities: 5,181 research-only, 2,346 research-value signals, seven historical shadow-actionable observations, and zero production-actionable records. Warehouse integrity passes.

Latest verification completed with 233 passing tests, 22 focused report/discovery regressions, clean Ruff, and strict mypy across 163 source files. The failed intermediate jobs that exposed the settlement and rollup defects remain in the operational ledger as immutable evidence; the successful final run follows them rather than erasing them.

### Remaining boundary

Append-only governance repairs auditability, not market evidence. The latest ledger has prospective reference odds for 55 fixtures and seven settled shadow records, but there is no active champion and that sample is insufficient for a real-money claim. Current API-Football retention cannot supply the missing historical point-in-time baseline. Daily prospective capture, settlement, and untouched chronological evaluation remain the correct path.

### Performance and operational re-audit — 2026-10-14

Provider-call telemetry showed that the slowest intervals were local row-at-a-time DuckDB persistence rather than API-Football latency. The audited implementation now checkpoints an unchanged competition catalog by content hash, writes match components and the observed market taxonomy through typed set-based relations, and emits explicit continuous-learning train/evaluate timings. It also distinguishes candidates withheld in the current learning run from the complete historical promotion pool and reports research-price/value-signal counts plus odds snapshots outside the analysis scope.

Measured on real persisted evidence, a repeated unchanged 1,241-row catalog write fell from 33.62 seconds to 0.0128 seconds after the checkpoint was seeded; 13 observed-market refreshes fell from 11.16 seconds to 0.96 seconds; and a 20-fixture detail page persisted 1,988 component rows in 2.92 seconds. Page-level transactions still bind persistence and checkpoint advancement atomically. The full suite, lint, typing, migrations, and warehouse integrity were rerun after these changes.

The pre-final-acceptance read-only warehouse audit reported 1,443 competition-seasons, 60,815 completed fixtures, 106 odds snapshots over 55 fixtures, 197 institutional predictions, 8,053 opportunities, seven settled shadow records, and zero production-actionable rows. The later artifact-reconciliation run below appended analysis evidence but did not change the research-and-shadow classification.

### Final artifact reconciliation — 2026-10-14

Before the final offline principal acceptance appended new analysis evidence, a schema-34 backup was created and independently verified at `artifacts/backups/2026-10-14-pre-final-offline-acceptance/backup_manifest.json` (14,719 files and nine critical table counts). Offline analysis `ec603dc8-13c4-4431-aec7-eb3a4e51b017` then completed 12/12 requested fixtures without provider calls, persisted ten predictions and 467 prices/opportunities (135 research value signals), and emitted zero shadow or production candidates. The fresh 934,172-character HTML contains the evidence-qualified Top Research contract, quality funnel, full Market Board, no-padding statement, and manual-price caveat. Direct SQL reconciled the exact analysis row and opportunity states, and post-run warehouse integrity passed.

The resulting live ledger contains 207 institutional predictions and 8,520 opportunities: 5,894 research-only, 2,619 research-value signals, seven historical shadow-actionable records, and zero production-actionable records. This final artifact regeneration fixed a documentation/artifact drift where earlier HTML files predated the quality-funnel template; it did not alter model, pricing, or actionability policy.
