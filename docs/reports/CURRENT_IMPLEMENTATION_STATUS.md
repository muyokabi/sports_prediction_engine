# Current Implementation Status

Verified 2026-10-14 (Africa/Nairobi).

## Status

`RESEARCH_AND_SHADOW / NOT_REAL_MONEY_APPROVED`

The engine continues to produce fixture probabilities and fair prices without an active market-family champion. Production actionability is a separate fail-closed label: the current warehouse has zero `PRODUCTION_ACTIONABLE` opportunities and zero active champions.

The live ledger is at schema 34 and contains 1,241 competitions, 1,443 competition-seasons, 1,046 teams, 69,542 fixtures, 60,815 completed fixtures (`FT`, `AET`, or `PEN`), 23,850 ML-eligible fixture-quality assessments, 106 prospective odds snapshots over 55 fixtures, 13 feature datasets, 71 model runs, 207 institutional predictions, and 8,520 opportunities. Opportunity governance is 5,894 `RESEARCH_ONLY`, 2,619 `RESEARCH_VALUE_SIGNAL`, seven historical `SHADOW_ACTIONABLE`, and zero production-actionable. All seven shadow records have now settled as paper-tracking evidence; that sample is not sufficient to demonstrate calibration, durable edge, or bankroll safety. No claim of real-money readiness is justified by these counts.

## Latest acceptance

Final offline analysis `ec603dc8-13c4-4431-aec7-eb3a4e51b017` completed all 12 requested fixtures for 2026-10-14, retained reference odds for ten fixtures, wrote ten predictions and 467 research prices/opportunities, including 135 research value signals, and emitted zero production or shadow candidates. The report is:

`artifacts/reports/2026/10/14/analysis-2026-10-14-2026-10-14-ec603dc8-13c4-4431-aec7-eb3a4e51b017.html`

The HTML now includes an independently evidence-qualified `Top Research` section with at most ten selections and one selection per fixture. Admission requires HIGH/MEDIUM applicability, valid model/reference prices, validated calibration and competition probability scope, adequate bookmaker breadth, no extreme model–market disagreement, positive calculable reference EV, and an API-Football quote at or above provisional minimum odds. A production champion or historical market baseline is not required merely to appear in this research shortlist. Ranking is lexicographic: applicability quality, fewer remaining evidence warnings, normalized price cushion above minimum odds, reference expected return, then model probability. Full pricing, provenance, EV, minimum-odds basis, the bookmaker-breadth gate, validated uncertainty state, applicability, governance, and gate reasons remain visible. A quality funnel reports the leading blockers when fewer than ten rows qualify, and the table is never padded with prior-only/out-of-domain guesses.

The earlier live analysis `e75f38b4-ecaa-4be9-9590-76a3e557d371` completed 12/12 fixtures and wrote 519 price rows. Eleven fixtures were `MEDIUM / PARTIALLY_POOLED`; one fixture was `PRIOR_ONLY`. Its report contained one genuinely evidence-qualified Top Research row for Millonarios v Once Caldas and correctly excluded the other rows, principally for missing competition probability validation or calibration. This proves the section can populate from persisted evidence without manufacturing a fixed daily quota. It does not prove predictive edge or real-money readiness.

## Forecast and exploratory-basket usability layer

The HTML report now separates four questions that were previously compressed into two often-empty top tables. `Top Forecasts` exposes up to ten strongest in-domain 1X2 views without requiring a market quote or implying value. `Research Basket` selects up to ten one-per-fixture, equal-unit learning hypotheses using positive model-expected return, a reference at or above the provisional minimum, exact-family global calibration, adequate bookmaker breadth, and no prior-only, unseen-team or extreme-disagreement state. Competition-scope validation is displayed as unresolved evidence in this exploratory view instead of hiding the hypothesis; it remains mandatory for `Validated Research` and production actionability.

The basket ranks expected return before payout reach and reports exact equal-stake arithmetic. At decimal odds `O`, one winning unit returns `O` units and offsets `O-1` other one-unit stakes; one winner covers an `N`-selection basket only when `O >= N`. High odds are therefore not treated as value by themselves, and no A/B or “sure bet” grades are invented. This is a report-only organization of already persisted immutable opportunities: no model role, prediction, governance state, stake instruction, or production gate changed. The durable policy is `docs/research/EQUAL_STAKE_RESEARCH_BASKET_POLICY.md`; prospective basket settlement evaluation remains open.

## Governance and evidence

Migration 034 makes promotion assessments and market-role changes append-only. Integrity validates a production label against the role, calibration, competition scope, and other evidence that existed at the opportunity's creation time. Three legacy production labels lacking provable historical role events were quarantined as `RESEARCH_VALUE_SIGNAL / NO_BET`; their immutable predictions and fair prices were not changed.

The prior Dixon-Coles model remains usable as a qualified research score model. It is not a champion because the policy-required historical point-in-time market baseline is absent. API-Football's short odds retention means that evidence must accumulate prospectively and cannot be reconstructed. Missing odds, injuries, lineups, and movement remain explicit unknowns.

The schema-33 warehouse was backed up and verified before migration at:

`artifacts/backups/2026-10-14-pre-append-only-governance/backup_manifest.json`

## Verification

| Check | Result |
|---|---|
| Full test suite | 233 passed |
| Focused report/discovery regressions | 22 passed |
| Ruff | Passed |
| Strict mypy | Passed for 163 source files |
| Migrations | Schema 34/current |
| Warehouse integrity | Passed after migration and final acceptance |
| Pre-change backup | Verified schema 33; 14,648 files; nine critical tables |
| Pre-final-acceptance backup | Verified schema 34; 14,719 files; nine critical tables |
| Offline principal acceptance | 12/12 terminal; 11 fixtures with references; zero production/shadow labels |
| Final offline principal acceptance | 12/12 terminal; ten predictions; 467 prices; 135 research value signals; zero production/shadow labels |
| Historical offline report acceptance | 29 headers/cells reconciled; shortlist correctly empty because no row satisfied the independent evidence policy |
| Latest shortlist regression contract | 32 truthful columns plus quality funnel; one persisted live row independently reconciled |

## Remaining limitations

- Only 55 fixtures have prospective reference odds and seven shadow records have settled; this is not a sufficient prospective sample to demonstrate durable edge.
- There is no active market-family champion.
- Calibration and competition-scope validation currently cover `MATCH_ODDS` only. BTTS and totals remain research-priced but cannot enter the evidence-qualified shortlist until dedicated chronological validation exists.
- Historical pre-match odds, injuries, expected/confirmed lineups, and movement cannot be invented where they were not captured.
- Injury/lineup features have no useful historical training coverage; provider-dependent all-null or constant columns remain explicit but are excluded from fitted information.
- Competition admission, applicability, family qualification, calibration, uncertainty, and risk gates remain independent.
- DuckDB remains a coordinated single-writer local store, not a multi-process service database.

The correct next step is continued prospective collection and settlement, followed by predeclared chronological evaluation—not weaker gates or reinterpretation of research rankings as bets.

## Prediction-family experiment — 2026-10-14

PXR-001 extended new score-model evaluation artifacts with coherent BTTS and over/under 2.5 probabilities, observed goals, family-specific proper scores, direct-event calibration, fold-local empirical baselines, and paired chronological block-bootstrap comparison. On 9,460 identical out-of-fold fixtures, Dixon–Coles BTTS recorded log loss 0.691331 / Brier 0.248950 / ECE 0.035114; over 2.5 recorded 0.689288 / 0.247858 / 0.041127. Neither family clearly outperformed the simple fold-local event-rate baseline. Only 18/28 adequately sampled competitions passed the BTTS ECE bound and 15/28 passed the totals bound.

The hypothesis that global score-family evidence was sufficient for blanket validation was rejected. No live calibration, probability-scope, role, prediction, price, or opportunity row was changed. BTTS and totals remain research-priced but fail closed for the evidence-qualified shortlist. The durable record is `docs/research/PREDICTION_EXPERIMENT_REGISTER.md`; the implementation/result summary is `docs/reports/PREDICTION_PATH_UPGRADE_REPORT.md`.

Post-change verification: 239 tests passed, Ruff passed, mypy passed for 163 source files, and warehouse integrity passed. The final offline acceptance report was re-reconciled to the ledger: 12 expected / 12 terminal fixtures, ten predictions, 467 opportunities, 135 research-value signals, and zero shadow/production labels.

## Score-calibration experiment — 2026-10-14

PXR-002 tested one coherent global goal-intensity scale without changing production predictions. The exact four-fold Dixon-Coles baseline was reproduced on 9,460 out-of-fold fixtures (log loss 1.027692, Brier 0.616561, RPS 0.213132, ECE 0.014923). Evaluation artifacts now retain fold-local expected goals, rho, and home/away training representation so coherent calibration can be reproduced rather than inferred.

The scale fitted on folds 1-2 was 0.979780 and failed the 2,217-row fold-3 validation gate. It significantly worsened scoreline, BTTS and total-goals proper losses; the last fold remained uninspected. No model role, family validation, historical prediction, production opportunity, or shortlist rule changed. Prediction and candidate probabilities therefore did not improve; evidence quality improved by closing an unjustified calibration path. Classification remains `RESEARCH_AND_SHADOW`.

Post-change verification: 242 tests passed, Ruff passed, mypy passed for 164 source files, warehouse integrity passed, and the current persisted report was re-reconciled to 12/12 terminal fixtures, ten predictions, 467 opportunities, 135 research value signals, and zero shadow/production labels.

## Competition-intensity experiment — 2026-10-14

PXR-003 added a research-only evaluator for a shrunk competition scoring-rate correction. It binds the exact source prediction artifact and read-only fixture-to-competition mapping, selects shrinkage chronologically, preserves one normalized Dixon-Coles score matrix, and assigns scale 1.0 to sparse or unseen competitions rather than borrowing another competition's rate.

The selected 400-goal prior exposure estimated 20 competition scales from folds 1-2. On fold 3, 1,603/2,217 fixtures received an estimated scale and 614 retained the explicit fallback. The challenger worsened realized-score log loss from 3.007913 to 3.009708; the paired difference was +0.001795 with 95% block-bootstrap interval [-0.000809, +0.004035]. MATCH_ODDS and totals log losses worsened significantly, while BTTS was unresolved. The predeclared gate rejected the challenger and fold 4 remained unscored.

No production ledger, served probability, candidate, or governance state changed. Prediction quality and candidate quality did not improve; research quality improved by ruling out another plausible but unstable calibration shortcut. Dixon-Coles remains `RESEARCH_ONLY`, and system classification remains `RESEARCH_AND_SHADOW`.

Post-change verification: 246 tests passed, Ruff passed, mypy passed for 165 source files, warehouse integrity passed, the evaluation artifact digest matched, and the persisted 12-fixture report reconciled to ten predictions, 467 opportunities, 135 research value signals, and zero shadow/production labels.

## Applicability-discrimination audit — 2026-10-14

PXR-004 added exact fold-local effective team-history evidence to score-model evaluation artifacts and a read-only retrospective risk-coverage audit. The current five-effective-match floor retained 5,939/9,460 out-of-fold fixtures and showed a favourable aggregate log-loss difference of -0.062155 (95% moving-block interval [-0.076487, -0.044868]) versus rejected fixtures. It did not pass the temporal stability rule: fold 3 log-loss and Brier intervals both crossed zero, and accepted ECE was worse than rejected ECE.

No production applicability state, probability, price, opportunity, calibration, role, or shortlist rule changed. The existing floor remains a conservative fail-closed gate, not a newly proven confidence interval or stable uncertainty discriminator. Prediction quality and candidate quality did not improve; the evidence deficit is now precisely measured. A genuinely later prospective era is required for confirmation. Classification remains `RESEARCH_AND_SHADOW / NOT_REAL_MONEY_APPROVED`.

Post-change verification: 249 tests passed, Ruff passed, mypy passed for 167 source files, warehouse integrity passed, source/evaluation artifact hashes passed, and the persisted acceptance report remained reconciled to 12/12 terminal fixtures, ten predictions, 467 opportunities, 135 research value signals, and zero shadow/production labels.

## ML score-fusion experiment — 2026-10-14

PXR-005 adds a research-only bridge between the stronger 1X2 ML classifiers and the coherent Dixon-Coles pricing distribution. Outcome-marginal projection preserves a single normalized score matrix and therefore prevents separate ML probabilities from leaking incoherently into BTTS, totals, or correct score.

The selected 70% CatBoost blend improved final-fold 1X2 and over-2.5 proper loss, but BTTS degradation narrowly exceeded the predeclared uncertainty-aware family tolerance. The research gate failed. ML is therefore not being discarded, but this implementation is not served live and cannot receive a champion/actionability label from these retrospective artifacts. The command and hash-bound output make the hypothesis repeatable on a genuinely later temporal era.

Post-change verification: 253 tests passed, Ruff passed, mypy passed for 168 source files, and the PXR-005 prediction artifact hash verified. No warehouse, model-role, prediction, price, opportunity, or production-governance row was mutated.

## Direct ML family-specialist experiment — 2026-10-14

PXR-006 implements independent direct binary research challengers for BTTS and over 2.5. It uses each ML candidate's exact feature manifest, chronological fold protocol, and fold-local calibration; writes hash-bound predictions; and confines every metric and future role to its exact market family.

CatBoost significantly outperformed Dixon-Coles in both BTTS and totals on 9,469 aligned out-of-fold fixtures. LightGBM also improved BTTS, but CatBoost versus LightGBM BTTS was statistically unresolved; CatBoost clearly dominated LightGBM for totals and logistic for both families. This supports independent family ownership but does not support assigning different algorithms simply to create variety.

The evaluator and paired comparator are implemented, but no live model role or probability path changed. These are retrospective development results on an already inspected era. Direct family specialists still require later-era confirmation, exact-family calibration/scope evidence, and the configured market-baseline policy before live use.

Post-change verification: 255 tests passed, Ruff passed, mypy passed for 170 source files, all three family-specialist prediction hashes verified, and the paired comparison artifact was reproduced. No warehouse or production-governance row was mutated.

## Durable evidence

- Documentation map: `docs/README.md`
- Future-agent guardrails: `AGENTS.md`
- Pre-change baseline: `docs/audits/CURRENT_SYSTEM_BASELINE.md`
- Findings register: `docs/audits/IMPROVEMENT_REGISTER.md`
- Research record: `docs/research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md`
- Full audit report: `docs/reports/AUTONOMOUS_INSTITUTIONAL_CODEBASE_UPGRADE_REPORT.md`
- Satisfaction boundary: `docs/reports/CODEBASE_SATISFACTION_STATEMENT.md`
