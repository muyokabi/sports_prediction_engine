# Autonomous Institutional Codebase Upgrade Report

Generated 2026-10-12 and independently re-audited 2026-10-13 (Africa/Nairobi).

## Executive verdict

The platform is materially stronger and still performs its primary job: it produces fixture probabilities and fair prices. The final live acceptance analyzed all 19 requested fixtures and persisted 19 predictions and 837 prices. The audit removed the real-money label from the current model because its promotion record required significant market outperformance while containing zero historical point-in-time market-baseline rows.

Final classification: **`RESEARCH_AND_SHADOW / NOT_REAL_MONEY_APPROVED`**.

- Suitable for probability research: **yes**.
- Suitable for prospective shadow observation: **yes**.
- Suitable for real-money decision support: **no**. The provider ledger has only 25 fixtures with odds, zero settled shadow observations, and no candidate has the 200 point-in-time market rows required by policy.

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
| Teams | 876 |
| Fixtures / completed | 58,670 / 55,732 |
| Production fixtures / completed | 3,214 / 584 |
| Replay fixtures / completed | 55,456 / 55,148 |
| Quality-assessed `ML_ELIGIBLE` fixtures | 18,767 |
| Odds snapshots / fixtures / prices | 76 / 38 / 222,275 |
| Bookmakers / observed provider markets | 10 / 182 |
| Feature datasets / model runs | 10 / 59 |
| Institutional predictions / opportunities | 161 / 6,496 |
| Shadow observations / settled | 34 / 0 |

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

Zero settled shadow observations is an explicit empirical limitation. No ROI, drawdown, bankroll-survival, or closing-line advantage claim is made.

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
- Only 38 fixtures currently have odds and no shadow observation is settled. This blocks real-money approval.
- There is no active market-family champion. The qualified score model remains a research pricing core.
- Injury/lineup features have no historical training coverage; match/player statistics are only partially covered.
- Thirty-six thousand-plus completed replay fixtures are score-only/unassessed for detailed packages. Score models can use the results; ML detail coverage remains explicit.
- The present report prices score-derived BTTS and totals, but they have no independently promoted family champion.
- DuckDB requires coordinated single-writer operation.
- Legacy local pickle artifacts without hashes remain available only for trusted-local research compatibility. The production promotion gate now requires verified model and calibrator digests, and no pickle may be accepted from an untrusted source.

The correct next step is continued daily prospective collection and settlement, not lowering gates to manufacture bets.
