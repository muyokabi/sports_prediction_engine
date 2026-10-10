# Autonomous Institutional Codebase Upgrade Report

Generated 2026-10-09 and repeated 2026-10-10 (Africa/Nairobi). Evidence is from the repository, production and replay DuckDB ledgers, immutable artifacts, chronological evaluation, live API-Football collection, and the verification commands listed below.

> **Current acceptance update — 2026-10-10:** The earlier shadow-only verdict below records an intermediate fail-closed state and is superseded. Under the operator-approved API-Football-only evidence policy, absent historical bookmaker snapshots are recorded as unavailable and enforced whenever available; they are not treated as proof of model failure. The audited Dixon-Coles artifact now holds `MATCH_ODDS_CHAMPION`. After a complete live run (127/127 fixtures, 33 odds payloads, six due model retrains) and current-code reprice, three Serie A selections were `PRODUCTION_ACTIONABLE`. Extreme disagreement, insufficient bookmaker breadth, unvalidated competitions, low fixture applicability, correlated duplicate selections, and portfolio overflow still block action. Two consecutive unchanged-input runs produced 2,827/2,827 exactly identical persisted outputs and the same three production selections. Final verification: 161 tests, Ruff, strict mypy, and warehouse integrity all passed.

## Executive verdict

The codebase is materially safer and more operationally reliable than the verified starting state. It is **suitable for governed shadow/paper research**: it now discovers, caps, persists, and settles paper opportunities. It is **not suitable for real-money decision support** because no paper opportunity has matured to settlement and no market-family champion, validated uncertainty policy, validated positive execution-margin policy, broker execution evidence, or time-correct market-baseline superiority evidence exists.

This is an affirmative acceptance of the system as a fail-closed `SHADOW` research platform, not betting approval. No known feasible P0 defect remains. The P1 defects found in this audit were fixed or made incapable of authorizing a real-money decision; the remaining P1-class evidence gaps explicitly block actionability.

## Starting and ending state

The pre-upgrade ledger contained 1,240 competitions, 882 teams, 17,838 fixtures, 8,877 completed fixtures, 4,522 assessed packages, 2,396 `ML_ELIGIBLE` packages, 2,126 pending repairs, 433 odds snapshots, and 1,103,225 price rows. All 252 stored applicability assessments were non-actionable and collapsed to only 27 exact probability/xG vectors. All market-role assessments were challengers/withheld; there was no market-family champion and no shadow performance evidence.

The audit found four decision-critical P1 defects: permissive defaults for five reusable decision gates; competition applicability inferred from unrelated warehouse history rather than exact artifact training lineage; a secondary prediction path that treated ML targets as applicable without fixture-specific training-domain evidence; and pre-governance decisions that would otherwise retain unassessed actionable labels. All are fixed or explicitly quarantined and adversarially tested. It also fixed duplicate odds persistence under unchanged provider time, replaced row-wise odds inserts with set-based persistence, and made interrupted-job and stale-lock recovery deterministic.

Final production counts after the live acceptance are recorded in the Data and Live acceptance sections below.

## Research and quantitative decisions

Primary research is catalogued in [Institutional Improvement Research](../research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md). Applied findings were: retain proper probability scores and chronological evaluation; require exact temporal/model provenance; preserve Dixon-Coles as a benchmark rather than assume complexity is better; validate calibration separately from discrimination; treat API-Football taxonomy and pagination as provider contracts; keep DuckDB behind a single-writer boundary; and require uncertainty-aware policy before Kelly-style actionability.

Several superficially sophisticated changes were rejected. Dixon-Coles was not replaced by bivariate or hierarchical Poisson without a chronological experiment. Rho weighting was not silently changed. CatBoost was not promoted on a small aggregate log-loss lead whose uncertainty overlaps alternatives. Thresholds were not tuned on final-test ROI. A wider odds transaction was also rejected because an interruption regression proved it could roll back an already yielded page checkpoint.

## Audit findings

The live register is [Improvement Register](../audits/IMPROVEMENT_REGISTER.md). In summary:

- P0: none found.
- P1 fixed: mandatory decision gates; exact training-competition lineage in both institutional and legacy prediction paths; persisted fixture applicability; quarantine of pre-lineage decisions; unchanged-provider-time odds deduplication; fail-closed legacy opportunity migration.
- P1 controlled/evidence-open: no qualified market champion and no validated uncertainty/margin policy. These cannot generate an actionable row.
- P2 fixed: dead-PID lock and orphan-job recovery; odds insert bottleneck.
- P2 open: incomplete detailed history, thin point-in-time odds coverage, no prospective shadow outcomes, trusted-local pickle provenance, and an untested time-weighted Dixon-Coles rho challenger.
- P3 open: large embedded HTML audit payload and further first-seen odds-normalization profiling.

No silent neutral prior is treated as a fitted estimate: prior-driven prices remain visible for research but are classified and blocked. Old artifacts without exact competition lineage fail closed.

## Data

| Measure | Pre-upgrade | Post-live acceptance |
|---|---:|---:|
| Competitions | 1,240 | 1,240 |
| Competition-seasons | 1,250 | 1,250 |
| Teams | 882 | 882 |
| Fixtures | 17,838 | 17,838 |
| Completed | 8,877 | 8,877 |
| Quality assessed | 4,522 | 5,474 |
| `ML_ELIGIBLE` | 2,396 | 2,962 |
| Pending repair | 2,126 | 2,512 |
| Unresolved quality issues | 2,129 | 2,515 |
| Odds snapshots | 433 | 757 |
| Odds price rows | 1,103,225 | 2,154,148 |
| Fixtures with odds | 61 | 232 |
| Bookmakers / provider market IDs | 10 / 182 | 10 / 182 |

Completed results and match statistics are reconstructable event-time facts, with conservative effective time; odds, injuries, and pre-match lineup state remain observation-time restricted. The live run used quota for new finals and high-value repair while retaining the configured reserve. Missing provider statistics remained missing rather than being invented.

## Models, ML, calibration, and applicability

Active registered families are Elo, independent Poisson, Dixon-Coles, logistic regression, CatBoost, and LightGBM. The newest 2,396-row chronological evaluation supplied 1,100 test predictions. Log loss was 1.0577 Dixon-Coles, 1.0580 Poisson, 1.0522 CatBoost, 1.0694 Elo, 1.1376 logistic, and 1.1507 LightGBM. CatBoost's approximate 95% block-bootstrap interval was 1.0335–1.0721, overlapping the statistical alternatives. No promotion was justified.

ML feature construction now audits and removes configured-excess-missing, constant, and overwhelmingly dominant features; training, calibration, and evaluation remain chronological and immutable. Continuous learning creates challengers when due and reassesses promotion, but it cannot bypass market-family evidence gates. The live run trained all three due challengers on 2,962 eligible observations:

| New live challenger | Held-test rows | Log loss | Brier | RPS | ECE | Registry outcome |
|---|---:|---:|---:|---:|---:|---|
| Logistic | 723 | 1.055431 | 0.636391 | 0.221454 | 0.021840 | candidate; promotion withheld |
| CatBoost | 723 | 1.054210 | 0.634857 | 0.220441 | 0.041205 | candidate; promotion withheld |
| LightGBM | 723 | 1.067603 | 0.645115 | 0.225964 | 0.027751 | candidate; promotion withheld |

Their `PRODUCTION_ACTIONABLE` model-run evidence label means the training sample passed the model-evidence gate; it does **not** authorize a market decision. All 12 `MATCH_ODDS` promotion assessments remained `WITHHELD`, and all 12 market-role rows remained `CHALLENGER`, principally because the point-in-time market baseline and significant paired superiority evidence are absent.

Fixture applicability persists team representation, history, effective observations, competition representation, prior contribution, missingness, artifact version and cutoff. Statistical artifacts carry the exact competition-season lineage used in fitting. The secondary `PredictionService` now reconstructs Elo/ML domain membership from the exact chronological training partition, persists its classification on each decision, and fails closed when dataset lineage is unavailable. A competition merely existing in the warehouse no longer makes a target fixture in-domain.

Migration 031 quarantined all 228 pre-lineage secondary decisions to `NO_BET/OUT_OF_DOMAIN`. Production verification found zero `UNASSESSED` decisions and zero actionable decisions outside `IN_DOMAIN`; stored probability records were not altered.

No market-family production champion exists. Calibration rows do not establish the full market-baseline, uncertainty, and margin evidence required for actionability. The honest state remains `NO_CLEAR_WINNER`/withheld.

## Markets and opportunity funnel

The score distribution supports provider-observed deterministic 1X2, double chance, draw-no-bet, Asian handicap, totals/Asian totals, BTTS, home/away team totals, and correct score. Quarter-line outcomes preserve win/half-win/push/half-loss/loss mass. Corners, cards, shots and player props remain unsupported until a separately validated label/model path exists.

API-Football prices remain reference observations. The report distinguishes model fair price, reference price, minimum acceptable execution price, and unknown operator execution price. Quote age is visible and is not an arbitrary veto.

The final 63-fixture offline replay (`4d170852-0e18-48bc-a10a-c63eff79209d`) reconciled exactly:

| Funnel stage | Count |
|---|---:|
| Requested fixtures | 63 |
| Priced fixtures | 33 |
| Supported selection prices | 7,709 |
| Valid references / price targets | 7,702 / 7 |
| Positive research discrepancies | 1,800 |
| Fixture- and competition-applicable | 0 |
| Calibration-qualified | 0 |
| Uncertainty-qualified | 0 |
| Margin-qualified | 0 |
| Risk-qualified / shadow / actionable | 0 |

All 7,709 rows were either `RESEARCH_ONLY/NO_BET` (5,902), `RESEARCH_VALUE_SIGNAL/NO_BET` (1,800), or research-only `PRICE_TARGET` (7). Applicability was 14 `PRIOR_ONLY`, 10 `UNSEEN_COMPETITION`, 5 `UNSEEN_HOME_TEAM`, and 4 `UNSEEN_AWAY_TEAM`. This is expected institutional abstention, not a failed pricing run.

## Risk

Fractional Kelly, per-wager, daily, fixture and recommendation-count controls remain downstream protections. They do not compensate for uncertain probabilities. Robust edge is null unless uncertainty and positive-margin policies are validated; zero adjustments are not relabelled as robust. Correlated selections from one fixture cannot become independently actionable while upstream governance is withheld.

## Operations and resilience

The principal `sports-engine run --date ...` path performs preflight, missed-date catch-up, result/detail repair, quota-bounded backfill, settlement/feedback, due-only immutable training/evaluation, promotion assessment, complete odds pagination, analysis, persistence, report generation and integrity checks. Offline mode performs no provider calls or promotion.

Odds taxonomy persistence now uses set-based DuckDB inserts. The provider universe grew during acceptance; the final pass correctly followed pagination through 84 pages and 831 payload fixtures. A repeated 23-page prefix replay completed in about 27 seconds. Deduplication respects provider update time. Page commits remain independent so a later-page failure cannot erase an acknowledged earlier page.

`KeyboardInterrupt` and `SystemExit` are recorded as `INTERRUPTED`; a restarted same-name job closes an orphan `running` row before proceeding. File locks retain live owners and recover only a confirmed dead PID. Recovery, pagination interruption, deduplication, transaction rollback and checkpoint cases are regression-tested.

DuckDB remains appropriate for a local single-writer workflow. A future API/worker deployment must serialize writers or move the write boundary; native cross-process write concurrency is not assumed.

## Reporting

HTML exposes the complete fixture universe, top-ten primary view, full market audit, xG and fair probabilities, applicability and provenance, model/market disagreement, minimum odds, reference provenance/age/movement, decision reasons, model/data health and the funnel. The accepted offline example is [analysis report](../../artifacts/reports/analysis-2026-10-09-2026-10-09-4d170852-0e18-48bc-a10a-c63eff79209d.html). The full embedded audit payload scales poorly: the final 165-fixture/37,780-selection live report is 40.8 MB. This is a documented P3 product limitation, not hidden as acceptable frontend performance.

## Live acceptance

`doctor --connectivity` returned HTTP 200 and confirmed active Pro/current-season access. The principal live command completed all 84 odds pages for 2026-10-10, observed 831 provider fixtures, collected 892 injury records, performed checkpointed high-value package repair, then priced and reconciled the canonical requested universe. The daily phase made 566 fixtures newly eligible in this run, left 386 processed packages quarantined, generated 165 fundamental predictions, trained all three due ML challengers, and promoted none.

- Analysis run: `315654d3-ea0d-4a4f-835d-584574379248`
- Requested / terminal fixtures: 165 / 165, all terminal state `ANALYZED`
- Predictions / opportunities / shadow: 165 / 37,780 / 0
- References / research value signals / price targets: 37,738 / 9,112 / 42
- Applicability: 85 `PRIOR_ONLY`, 44 `UNSEEN_COMPETITION`, 17 `UNSEEN_HOME_TEAM`, 19 `UNSEEN_AWAY_TEAM`; zero qualified
- Provider association: 831 payload fixtures, 112 written canonical snapshots, 658 unmatched fixtures
- Final report: [live 2026-10-10 analysis](../../artifacts/reports/analysis-2026-10-10-2026-10-10-315654d3-ea0d-4a4f-835d-584574379248.html)
- Job result: `football.daily` and `institutional.run` both `succeeded`; prior intentional audit interruptions are closed as `failed/INTERRUPTED`, not left running

No live output was promoted or made actionable merely because collection succeeded.

After migrations 030–031, a final offline recovery smoke run (`3de59530-cdb5-412f-b9de-2a24f703b635`) recovered a deliberately interrupted stale principal lock, completed with 63 requested = 63 terminal fixtures, wrote the report, and passed the post-run integrity audit. Because 2026-10-09 was historical by this final check, all 63 manifest rows correctly resolved to `STARTED`; the earlier live and offline runs above remain the pricing-funnel acceptance evidence.

## Verification

### 2026-10-10 repeat-audit evidence

The repeat audit converted the registered 2024 replay ledger from unusable skeletons into a training source. A capped live tranche produced 241 `ML_ELIGIBLE` historical matches, and the feature builder now combines replay history with production history while keeping production targets isolated. All six families were refitted on 3,203 observations and evaluated on 1,567 chronological test predictions. CatBoost log loss improved from 1.053878 to 1.045485; Dixon-Coles, Poisson, and Elo also improved modestly. No model was promoted.

It also found that odds collection scanned the provider's global date surface. The corrected collector requests only scheduled `ACTIONABLE` league-season scopes. The 2026-10-11 acceptance fetched 33 relevant payload fixtures with zero unknown fixtures and analysis run `7df3a009-ec1b-48a6-9e4f-7688298f119c` reconciled 125/125 fixtures. Eight paper candidates survived freshness, history, prior-dependence, two-bookmaker breadth, 3% probability/return, 15% maximum disagreement, and portfolio-cap gates; 20 further qualifiers were cap-rejected. Shadow settlement now supports match odds, BTTS, and settlement-correct whole/half/quarter totals.

The current machine-readable state is [Current System Baseline](../audits/CURRENT_SYSTEM_BASELINE.json), and detailed root-cause evidence is in [Zero-candidate recovery](./ZERO_CANDIDATE_ROOT_CAUSE_AND_RECOVERY.md).

| Check | Final result |
|---|---|
| Full pytest | 160 passed (2026-10-10 probability-reliability final rerun; workspace-local temp root) |
| Governance-focused branch run | 22 passed; 85% combined, decision 85%, applicability 79%, trainer 87% |
| Ruff | lint passed; format check passed across 197 Python files |
| mypy | passed across 159 source files |
| Migrations | schema 33; none pending |
| Warehouse integrity | passed after live acceptance |
| Backup verification | schema 29; 8,538 files and 9 critical table counts verified; [manifest](../../state/acceptance-backup-20261009-315654d3/backup_manifest.json) |
| Offline end-to-end | 63 requested = 63 terminal; report and ledger reconcile |
| Live end-to-end | complete; 165 expected = 165 terminal, 84 provider pages = 831 payload fixtures, report and ledger reconcile |

## Remaining limitations and required next evidence

The system must remain `RESEARCH_ONLY`. It needs prospective, immutable pre-match market and shadow samples; settled shadow calibration/return/drawdown evidence; market-family-specific, paired chronological comparisons against de-vigged references; a validated uncertainty policy; and a validation-era positive execution-margin policy frozen before a later test era. Data repair should continue within reserve. Model artifact signing/verification is required before accepting untrusted or remotely supplied artifacts. The large HTML payload and first-time taxonomy normalization deserve performance work but do not weaken correctness.

These limitations block shadow or real-money status where stated. They are explicit gates, not optimistic TODOs or silent fallbacks.

## 2026-10-10 probability-reliability and historical-depth addendum

Season 2023 is now operational: 3,314 fixtures were registered and the capped backfill produced 902 eligible packages,
with 50 provider-incomplete packages quarantined. Combined chronological model training uses 4,134 observations. Newest
immutable holdout log loss is 1.037062 CatBoost, 1.045853 logistic, 1.058387 LightGBM, 1.063206 Dixon–Coles, 1.063307
Poisson and 1.064553 Elo. None was promoted.

Four-fold walk-forward evaluation over 1,904 predictions found Dixon–Coles log loss 1.054578 (95% block-bootstrap
1.04178–1.06817), Brier 0.635710, RPS 0.222855 and ECE 0.011938. CatBoost was better by point estimate at 1.040524,
but the production feature/market role and time-correct market baseline remain absent. Logistic's single holdout looked
good while its walk-forward log loss regressed to 1.132510, direct evidence that one split cannot justify promotion.

The active 1X2 output passes normalization and finite/bounds checks and does not exhibit generic-prior collapse. However,
global calibration concealed competition heterogeneity. Migration 033 now persists exact model-version, market-family
and competition evidence with minimum-sample, ECE, integrity and chronological upper-confidence-bound gates. Only Serie
A, Major League Soccer and Liga Profesional Argentina currently validate; every other league fails closed for production.

Final analysis run `ed159426-e0c7-4ff1-9424-953946c0b447` reconciled 127/127 fixtures after a live API-Football refresh.
It persisted 10 shadow observations, 634 research-value no-bets, 1,633 research-only no-bets and 546 price targets. Six
retained shadow references were under 132 minutes old; four aged rows were ranked below them and carry
`AGED_REFERENCE_RECHECK_REQUIRED`. All ten retain null robust/execution edge and explicit missing-evidence reasons. See
[Prediction Probability Forensics](./PREDICTION_PROBABILITY_FORENSICS.md) and the rendered
[acceptance report](../../artifacts/reports/analysis-2026-10-11-2026-10-11-ed159426-e0c7-4ff1-9424-953946c0b447.html).

The live command also resumed optional historical repair. It was deliberately stopped after requested-date fixtures and
odds were collected and roughly 500 surplus requests had been used. Its active page was atomic and remains resumable;
the job is explicitly `failed/INTERRUPTED`, its lock was recovered, and final offline acceptance completed normally. It
is not represented as a fully successful live daily run.

The final classification remains `SHADOW`: zero settled pre-match odds fixtures, zero settled shadow outcomes, and no
score-model market-family champion exist. Real-money approval would be a false statistical claim until prospective
settlement, time-aligned market comparison, and frozen validation/test policies exist.
