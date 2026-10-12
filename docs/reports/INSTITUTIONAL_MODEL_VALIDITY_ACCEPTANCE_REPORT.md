# Institutional Model Validity Acceptance Report

> Historical evidence only. It does not authorize any current model; see `docs/reports/CURRENT_IMPLEMENTATION_STATUS.md`.

Generated: 2026-10-08 (Africa/Nairobi)

## Acceptance decision

**BETTING ACTIONABILITY REMAINS FROZEN.** The correction is accepted as a fail-closed research pipeline, not as real-money production approval. New positive discrepancies are persisted as `RESEARCH_VALUE_SIGNAL`; rows cannot reach `SHADOW_ACTIONABLE` unless fixture applicability, competition actionability, market-family role, calibration, uncertainty, and positive-margin policies all have explicit validated evidence. Historical predictions and the accepted API-Football reference-odds semantics were not rewritten.

The final corrected 63-fixture offline replay is analysis run `6a741966-3569-4fed-b1d2-208999b43252`. It made no provider calls and its [HTML](../../artifacts/reports/analysis-2026-10-09-2026-10-09-6a741966-3569-4fed-b1d2-208999b43252.html) visibly identifies `OFFLINE_REPLAY`.

## Model applicability

### 63-fixture reproduction

| Measure | Before | Corrected replay |
|---|---:|---:|
| Fixtures | 63 | 63 |
| Identical global-prior distributions | 36 | 36, explicitly quarantined |
| `PRIOR_ONLY` fixtures | not persisted | 36 |
| `UNSEEN_HOME_TEAM` | not persisted | 7 |
| `UNSEEN_AWAY_TEAM` | not persisted | 6 |
| `PARTIALLY_POOLED` | not persisted | 14 |
| Fixtures with at least one unseen team | not persisted | 49 |
| Actionable/shadow opportunities | 153 legacy conditional candidates | 0 |

The exact cause of the 36 identical distributions was a silent fallback in `PoissonModel.expected_goals`: missing team IDs used `team_attack.get(team, 0.0)` and `team_defense.get(team, 0.0)`. When both teams were absent from `fitted_teams`, every team-specific term was zero, leaving only the global intercept and home-advantage terms. Dixon-Coles then applied the same low-score correction to every such fixture. This produced the repeated 0.399718 / 0.232376 / 0.367907 1X2 distribution and identical BTTS/totals prices.

The model still supplies that prior distribution as research information, but it is no longer silent and can never become a betting candidate. Every prediction now persists team counts, recency-weighted effective observations, venue splits, last observation, fitted-universe flags, prior-dependence proxy, attack/defence terms, parameter state, baseline, home advantage, expected goals, probabilities, applicability level, and reason codes.

The complete 63-row evidence extract is [INSTITUTIONAL_MODEL_VALIDITY_FIXTURE_AUDIT.csv](./INSTITUTIONAL_MODEL_VALIDITY_FIXTURE_AUDIT.csv).

## Competition governance

| Universe measure | Count |
|---|---:|
| Discovered competition-seasons | 1,240 |
| Observation-qualified (`OBSERVATION` + `ACTIONABLE`) | 68 |
| Collected/admitted | 50 |
| Provider-state `ACTIONABLE` | 10 |
| Model/market/calibration-qualified | 0 |
| Fully actionable | 0 |

The corrected expanded replay attempted 11,928 selection prices in observation competitions and 1,925 in provider-state actionable competitions. All remained research-only because competition state alone is insufficient. Observation competitions can be collected, priced, evaluated, and compared, but cannot produce an actionable candidate.

## Calibration

No model-market family currently has `CALIBRATION_VALIDATED`; therefore calibration-qualified selections = 0.

| Model | Market evaluated | Rows | ECE | State |
|---|---|---:|---:|---|
| Elo | 1X2 | 190 | 0.024779 | not yet persisted as validated |
| Poisson | 1X2 | 190 | 0.056462 | not yet persisted as validated |
| Dixon-Coles | 1X2 | 190 | 0.042598 | not yet persisted as validated |
| Logistic | 1X2 | 60 | 0.117984 | uncalibrated challenger |
| CatBoost | 1X2 | 60 | 0.097676 | uncalibrated challenger |
| LightGBM | 1X2 | 60 | 0.253545 | calibration/evaluation failed |

The registry now supports explicit `CALIBRATION_VALIDATED` and `CALIBRATION_FAILED` by model and market family. Absence is fail-closed. Score-distribution models are not independently recalibrated per derived selection; future validation must preserve distribution coherence.

## Champion selection and uncertainty

Corrected four-fold chronological evaluation used 190 held-out fixture predictions and 2,000-sample chronological block-bootstrap intervals (block size 13).

Machine-readable evidence: [Elo](../../artifacts/evaluation/elo-2678725e3b88-0519e9fdb64d.json), [Poisson](../../artifacts/evaluation/poisson-2678725e3b88-1a52af2bc9ee.json), and [Dixon-Coles](../../artifacts/evaluation/dixon-coles-2678725e3b88-17866ca51cea.json).

| Model | Log loss (95% interval) | Brier (95% interval) | RPS (95% interval) |
|---|---|---|---|
| Elo | 1.059118 (1.023559, 1.081892) | 0.639715 (0.615600, 0.655346) | 0.229397 (0.221133, 0.236935) |
| Poisson | 1.061520 (1.028327, 1.084126) | 0.641056 (0.618772, 0.656020) | 0.229934 (0.223058, 0.236152) |
| Dixon-Coles | 1.063239 (1.029553, 1.086020) | 0.641983 (0.619681, 0.656831) | 0.230089 (0.223223, 0.236261) |

Paired Elo-minus-Dixon-Coles log-loss difference was -0.004120 with 95% interval (-0.015940, 0.007065). Elo-minus-Poisson was -0.002402 (-0.014526, 0.008732). Both intervals cross zero: the correct 1X2 decision is `NO_CLEAR_WINNER`, not forced promotion. Poisson was slightly better than Dixon-Coles on paired log loss (-0.001719; interval -0.003317 to -0.000017), but its Brier and RPS differences still crossed zero.

The `model_market_roles` registry separates `MATCH_ODDS`, score distribution, totals, BTTS, Asian handicap, corners, and cards roles. No role is currently a production champion because calibration and market-baseline evidence are incomplete.

No historically valid pre-match market baseline existed in the corrected feature evaluation window; late-downloaded odds were correctly excluded rather than backfilled as point-in-time observations. The evaluator supports de-vigged chronological market comparison and paired bootstrap when valid timestamps exist.

## Candidate funnel

| Gate | Selections remaining |
|---|---:|
| Score-distribution selections priced | 13,853 |
| Valid API-Football reference present | 13,818 |
| Positive raw probability discrepancy | 3,343 |
| Research value signals | 3,349 |
| Both teams in fitted universe | measured and persisted; only 14/63 fixtures |
| Competition provider-state actionable | 1,925 |
| Calibration validated | 0 |
| Uncertainty policy validated | 0 |
| Evidence-qualified positive-margin threshold | 0 |
| Robust-EV qualified | 0 |
| `SHADOW_ACTIONABLE` | 0 |
| Production actionable | 0 |

The six additional research signals have positive reference expected return but do not meet the raw probability-advantage diagnostic. `robust_estimated_edge` is `NULL` unless both margin and uncertainty policies are validated. Zero adjustment is never presented as robust expected return.

When all gates eventually pass, the opportunity is written to the separate `shadow_opportunities` ledger with the complete qualification evidence. That ledger does not confer production approval; it exists for prospective scoring, threshold survival, market-movement, return, and drawdown evaluation.

Extreme discrepancies are quarantined by the same fail-closed gates. A historical residual threshold is required before an explicit `MODEL_MARKET_CONFLICT` can be cleared; absence of that evidence cannot authorize a bet.

## Data completion and effective time

At audit start the warehouse contained 8,870 completed skeletons, 463 `ML_ELIGIBLE`, 442 `PENDING_REPAIR`, and 8,407 not yet eligible. The lower-bound batching plan was 421 `/fixtures?ids=` calls, but live execution demonstrated that completed skeletons normally also require a fixture-scoped statistics call. The evidence-based request estimate is therefore `ceil(N/20) + N` before any event/lineup/player repairs: 8,828 calls for the initial gap. The planner now budgets this observed cost instead of assuming one request fully enriches twenty fixtures, retains the daily reserve, and checkpoints capped runs.

Post-backfill warehouse state:

| Completion state | Fixtures |
|---|---:|
| Completed skeletons | 8,877 |
| Assessed/enriched | 3,267 |
| `ML_ELIGIBLE` | 1,759 |
| Assessed but `PENDING_REPAIR` / quarantined | 1,508 |
| Not yet assessed | 5,610 |

The final completed checkpointed run assessed 952 fixtures: 527 became eligible and 425 were quarantined. Earlier checkpointed work in this audit also persisted, so eligibility increased by 1,296 from the 463-fixture starting point. The remaining 5,610 fixtures require future quota windows; the report does not represent the current season as complete.

Completed results and match statistics now use `RECONSTRUCTED_EVENT_TIME` with a conservative effective time of scheduled kickoff plus four hours. Odds, injuries, and lineups remain `OBSERVED_POINT_IN_TIME`. A late database download can no longer erase earlier completed-match facts, while time-sensitive data is never reconstructed.

A live-run failure exposed mixed timezone metadata when Polars combined fixtures with reconstructed history (`Africa/Nairobi`) and fixtures falling back to the live decision timestamp (`UTC`). All event and observation datetimes are now normalized to UTC before prediction-frame construction. A regression test reproduces the mixed history/no-history case.

## ML matrix and challengers

Dataset `f95bb24f-51bb-5a4a-a9a7-7a2520bc82e4` (`institutional-validity-20261008`) contains 463 rows and 177 columns. Before the effective-time fix, Elo, history, congestion, and essentially every non-target numeric feature were constant or empty. After correction:

- no numeric feature is constant or near-constant;
- home Elo spans 1479.31–1531.38 and away Elo 1472.76–1538.19;
- home/away history spans 0–4 matches;
- goals, shots on target, corners, passing/possession, discipline, rest, congestion, and completed-player aggregates vary where available;
- feature selection removes configured-excess-missing, constant, and >=99.5% dominant features before ML fitting.

| Challenger | Log loss | Brier | RPS | ECE | Decision |
|---|---:|---:|---:|---:|---|
| Logistic | 1.111947 | 0.674884 | 0.251836 | 0.117984 | `VALIDATION_ELIGIBLE`; no promotion |
| CatBoost | 1.102676 | 0.662810 | 0.257452 | 0.097676 | `VALIDATION_ELIGIBLE`; no promotion |
| LightGBM | 1.268376 | 0.741003 | 0.288216 | 0.253545 | failed evaluation; no promotion |

All three are immutable full-refit challengers. None is calibrated or production actionable.

## Continuous learning

The principal live workflow now evaluates due-only policies for logistic, CatBoost, and LightGBM before market analysis. When any model is due it materializes one immutable point-in-time dataset, attempts an incremental challenger where supported, falls back to an immutable full refit when incremental chronology or schema is unsuitable, calibrates from the validation holdout, evaluates chronologically, and retains lineage. Fresh model runs record the complete dataset observation count, so validation/test partitions cannot make a just-trained model immediately appear due again.

The corrected automatic run used dataset `ca0d7a84-c79c-5bd8-b411-4c4394a61c09` (`automatic-ml-20261008T141249489941Z`), containing 1,759 rows with hash prefix `586869675b47`. All three models were due and produced calibrated full-refit challengers:

| Challenger | Log loss | Brier | RPS | ECE | Workflow decision |
|---|---:|---:|---:|---:|---|
| Logistic `f4e0a99b` | 1.056874 | 0.638132 | 0.225109 | 0.051406 | retained, promotion withheld |
| CatBoost `09008ad9` | 1.034751 | 0.621620 | 0.220029 | 0.084328 | retained, promotion withheld |
| LightGBM `1113f476` | 1.055067 | 0.635759 | 0.227059 | 0.049870 | retained, promotion withheld |

Machine-readable walk-forward reports: [Logistic](../../artifacts/evaluation/logistic-586869675b47-d948cf5e5b75.json), [CatBoost](../../artifacts/evaluation/catboost-586869675b47-900b7bb64421.json), and [LightGBM](../../artifacts/evaluation/lightgbm-586869675b47-c1505aca57f4.json).

An immediate second scheduler pass returned no due models and trained nothing. Existing champions were not mutated. Promotion remained withheld because a lower scalar loss alone does not establish a market-family champion, validated uncertainty policy, or evidence-qualified execution margin.

### Automated production promotion extension

The principal live workflow now runs an audited promotion state machine after new results are settled and due-only training completes, but before prediction generation; it also reassesses candidates when no retraining is due. For each ML candidate it requires `PRODUCTION_ACTIONABLE` training evidence, a validation-holdout Platt or isotonic calibrator, sufficient calibration and walk-forward rows, bounded log-loss/Brier/RPS uncertainty intervals, stable fold calibration, a time-correct bookmaker baseline, statistically significant paired log-loss and Brier advantage over that baseline, and improvement over the incumbent. Missing evidence is a deterministic `WITHHELD`, never an implicit pass.

Successful assessment writes `CALIBRATION_VALIDATED`, assigns the market-specific `MATCH_ODDS_CHAMPION` role, persists validated uncertainty and minimum-odds policies, and promotes the ML artifact without retiring the separate deterministic score-distribution champion. Failed assessments remain challengers with complete reason codes in `model_promotion_assessments`. The same policy is used by the principal command, `models assess-promotions`, and the guarded `models promote` command; the latter can no longer bypass governance. Migration 029 adds the immutable assessment ledger.

Migration 029 was applied to the production warehouse and the service assessed all six existing ML candidates. The result was 0 promoted and 6 withheld/challenger. Two candidates passed the isolated calibration gate and four failed it; no candidate passed the complete promotion state machine. All recent candidates lacked sufficient point-in-time bookmaker-baseline evidence and statistically significant paired market advantage. Logistic and LightGBM also exceeded one or more configured uncertainty bounds, while CatBoost exceeded the calibrated-ECE/regression limits. These are persisted production decisions, not report-only conclusions.

## Markets

The principal analysis now enumerates provider-observed, explicitly governed score-distribution-compatible selections rather than seven fixed selections.

| Market | Offered line/selection variants | Prices |
|---|---:|---:|
| Match odds | 3 selections | 189 |
| BTTS | 2 selections | 126 |
| Double chance | 3 selections | 174 |
| Asian handicap | 41 lines | 2,201 |
| Total goals | 30 lines | 2,413 |
| Home team total | 14 lines | 937 |
| Away team total | 11 lines | 789 |
| Correct score | provider-observed score selections | 7,024 |
| **Total** | **8 market families** | **13,853 selections** |

API-Football `Home/Away` is disabled because draw settlement is ambiguous. Corners, cards, shots, and player markets remain research/no-model until a separately validated engine exists.

HTML now reports market families, lines, and selections separately, shows only the top ten final shadow-qualified opportunities by default, separates research signals, exposes actual xG/probabilities/parameters/evidence, and displays live versus offline provenance.

## Operator workflow

`sports-engine run --date today|tomorrow` now performs local preflight, missed-run catch-up, detailed enrichment, bounded repair, surplus backfill, settlement/feedback, due-only ML dataset/training/calibration/evaluation, automated promotion assessment, odds collection, full-universe pricing, HTML generation, and post-run integrity checks. Specialist commands remain available. Offline replay skips provider calls, maintenance, training, and promotion, and is visibly labelled.

The live orchestration attempt exposed and led to fixes for unknown-team player foreign keys, unsupported injury pagination, duplicate injury observations, transient HTTP protocol disconnects, and mixed prediction-frame timezones. The final specialist backfill and integrity pass completed successfully. A fresh end-to-end live principal run was not repeated after the last fix because it would immediately start another quota-consuming surplus-backfill cycle; this report does not claim that final live rerun occurred.

## Verification

| Check | Result |
|---|---|
| Migrations 027–029 | applied; 028 fail-closes legacy governance defaults and 029 adds promotion audit state |
| 63-fixture offline replay | complete |
| Targeted validity/pricing tests | passed within full suite |
| Effective-time/backfill tests | passed within full suite |
| Ruff | passed |
| mypy | passed; 159 source files |
| Full pytest | 145 passed |
| Branch coverage | 73% overall on the full pre-final suite; governance-critical modules ranged from 70% to 100% |
| Warehouse integrity | passed; no stale `RUNNING` job or analysis rows |
| Backup verification | passed after production promotion assessment; schema 29, 5,566 files, 9 row-counted tables; [manifest](../../artifacts/backups/institutional-validity-20261008-promotion/backup_manifest.json) |

## Final principle

A large model-market discrepancy is now evidence to investigate, not authority to bet. The corrected pipeline must prove both teams are learned, the competition and market family are qualified, calibration is validated, uncertainty is understood, the reference comparison is legitimate, and a positive evidence-derived margin survives. Until then, the platform deliberately produces fewer false edges by producing **zero actionable bets**.
