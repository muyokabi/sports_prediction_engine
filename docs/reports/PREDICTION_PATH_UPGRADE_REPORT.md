# Prediction Path Upgrade Report

Verified 2026-10-14 (Africa/Nairobi).

## Outcome

This run improved the **evidence quality of the prediction path**, not the quoted probabilities or the number of candidates. The walk-forward evaluator now retains score-derived BTTS and over/under 2.5 probabilities, observed goals, fold-local empirical baselines, binary proper scores, direct-event calibration, equal-mass reliability, contiguous block-bootstrap uncertainty, and paired score-family comparisons on identical fixtures.

The new evidence rejected blanket BTTS/totals qualification. The candidate funnel therefore remains fail-closed and no historical or production-ledger decision was changed.

## Baseline and hypothesis

The research-usable score model is Dixon–Coles `dixon-coles-20261013T223455579046Z-92b51b5e`, trained on dataset hash `9c5d616d445e807c6c6ff087f0f498429cfb5fd34274c8aec6bac68c84cdb879`. The prior retained 1X2 walk-forward baseline was reproduced on 9,460 out-of-fold fixtures: log loss 1.027692, multiclass Brier 0.616561, RPS 0.213132, and top-label ECE 0.014923.

The tested hypothesis was that the same coherent score matrix could support family-specific BTTS and total-goals validation without post-hoc probability invention. Poisson was the interpretable ablation; fold-local event prevalence was the simple predictive baseline.

## Chronological result

- Dixon–Coles BTTS: log loss 0.691331, Brier 0.248950, ECE 0.035114.
- Dixon–Coles over 2.5: log loss 0.689288, Brier 0.247858, ECE 0.041127.
- All fold ECE values were below 0.08, but paired model-minus-baseline intervals crossed zero for both families.
- Only 18/28 adequately sampled competitions passed BTTS ECE <= 0.08; only 15/28 passed totals ECE <= 0.08.
- Dixon–Coles beat Poisson for BTTS by a small paired amount, but 1X2 remained `NO_SIGNIFICANT_DOMINANCE` and totals were identical.

The untouched temporal evidence therefore says `NO_CLEAR_WINNER` against the simple baseline and rejects global competition qualification.

## Calibration, applicability, and candidate funnel

Probability vectors were finite, bounded, coherent derivatives of each fold's score matrix, and evaluated without fitting a binary calibrator. This preserves cross-market distributional coherence.

Fixture applicability behavior was not weakened. `PRIOR_ONLY`, `OUT_OF_DOMAIN`, unseen-team, critical-history, calibration, competition-scope, reference, uncertainty, price, and correlation gates remain independent. No BTTS or totals calibration/scope records were inserted, so the live shortlist is unchanged. Candidate quantity did not improve; candidate defensibility improved because global family averages can no longer be mistaken for competition-specific validation.

## Verification

Focused adversarial coverage verifies invalid/non-finite/out-of-range binary probabilities fail explicitly, binary ECE uses the quoted event probability, standard binary Brier semantics are preserved, score-model artifacts retain family targets/probabilities, and paired comparisons keep market families separate.

- Full test suite: 239 passed.
- Ruff: passed.
- Mypy: passed for 163 source files.
- Warehouse integrity: passed; schema remained 34 and the production warehouse was not mutated by the experiment.
- Generated artifact integrity: evaluation reports bind the prediction parquet row count and SHA-256; paired comparison re-verifies each digest.
- Real-report reconciliation: analysis `ec603dc8-13c4-4431-aec7-eb3a4e51b017` remains `COMPLETE` with 12 expected / 12 terminal fixtures, ten predictions, 467 opportunities, 135 research-value signals, and zero shadow/production labels. Its HTML shows the same counts and an unpadded zero-row shortlist.

## Verdict

- **Prediction quality improved:** no; probabilities were not changed.
- **Candidate quality improved:** yes in governance precision—unsupported BTTS/totals qualification was rigorously rejected—but no new candidate was admitted.
- **Decision:** retain Dixon–Coles as `RESEARCH_ONLY`; do not promote BTTS or totals.
- **Still unproven:** score-distribution-preserving calibration benefit, competition transfer, market outperformance, prospective edge, and bankroll safety.
- **Next experiment:** predeclare and test one distribution-preserving score calibration challenger on validation eras, then keep a later temporal era untouched.
- **Current classification:** `RESEARCH_AND_SHADOW`.

## Follow-up cycle — global intensity calibration

PXR-002 implemented reproducible latent score-parameter lineage and tested one score-distribution-preserving calibration hypothesis. The challenger multiplied both Dixon-Coles intensities by a shared scalar, retained rho, and rebuilt every market from the same normalized score matrix.

The scalar fitted on chronological folds 1-2 was 0.979780. It failed fold-3 validation: realized-score log loss worsened by +0.003593 with 95% block-bootstrap interval [0.002368, 0.004965], BTTS by +0.001917 [0.001161, 0.002677], and totals by +0.003052 [0.001875, 0.004218]. The failure persisted on the 1,938 both-teams-seen fixtures. Fold 4 remained uninspected under the predeclared gate.

This is a useful negative result: no production or candidate logic was changed, no unsupported calibration was promoted, and future evaluation can now reconstruct coherent fold score distributions from expected goals and rho. Prediction quality and candidate quality did not improve. Dixon-Coles remains `RESEARCH_ONLY`; system classification remains `RESEARCH_AND_SHADOW`.

Verification: 242 tests, repository-wide Ruff, mypy across 164 source files, warehouse integrity, artifact digest checks, and read-only reconciliation of the latest persisted 12-fixture report all passed.

## Follow-up cycle — partially pooled competition intensity

PXR-003 tested whether competition scoring regimes could repair the global-scale failure without breaking score-distribution coherence. Fold 1 fitted competition scales, fold 2 selected a shrinkage exposure from the frozen grid, fold 3 served as the validation gate, and fold 4 was sealed unless validation passed. Sparse or unseen competitions retained scale 1.0.

The selected 400-goal exposure produced 20 estimated competition scales and adjusted 1,603/2,217 validation fixtures. It worsened scoreline log loss by +0.001795 (95% block-bootstrap interval [-0.000809, +0.004035]), MATCH_ODDS by +0.001249 [+0.000513, +0.002031], and totals by +0.003002 [+0.000894, +0.004778]. BTTS was unresolved. MATCH_ODDS ECE improved slightly, but proper loss degraded, so the calibration diagnostic did not justify the challenger. Fold 4 was not scored.

This is a rigorous negative result. Prediction quality did not improve, candidate quality did not improve, and no live logic or ledger row changed. The partially pooled intensity correction is rejected; Dixon-Coles remains `RESEARCH_ONLY`; classification remains `RESEARCH_AND_SHADOW`. The next model experiment should wait for a genuinely later untouched era and test a distinct mechanism such as dynamic home advantage or a fully refitted hierarchical score model rather than another post-hoc total-intensity rescaling.

Verification: 246 tests, repository-wide Ruff, mypy across 165 source files, warehouse integrity, evaluation artifact digest verification, `git diff --check`, and read-only reconciliation of the persisted 12-fixture report all passed.

## Follow-up cycle — fixture-applicability discrimination

PXR-004 audited the existing five-effective-match applicability floor rather than inventing a new confidence score. Walk-forward artifacts now retain exact fold-local recency-weighted home/away representation, and a reusable research-only command reports risk, calibration, coverage, and chronological moving-block uncertainty for accepted versus rejected fixtures.

On 9,460 out-of-fold fixtures, the floor retained 62.78% and aggregate accepted log loss was 1.004557 versus 1.066713 for rejected fixtures, a difference of -0.062155 (95% CI [-0.076487, -0.044868]). The result was not stable across time. Fold 3 was unresolved for both log loss (-0.003984 [-0.036378, +0.028932]) and Brier (-0.003662 [-0.026200, +0.019297]); accepted ECE was also worse (0.039226 versus 0.028537).

The current conservative gate remains in place, but it is no longer defensible to treat its prior absolute-ceiling check as proof of stable risk discrimination. No served probability or candidate rule changed. Prediction quality and candidate quality did not improve; applicability evidence became more honest and more reproducible. A genuinely later prospective era is required before changing the threshold or its validation status. Classification remains `RESEARCH_AND_SHADOW`.

Verification: 249 tests passed, Ruff passed, mypy passed for 167 source files, warehouse integrity passed, artifact digests passed, and the persisted acceptance report remains reconciled at 12/12 terminal fixtures, ten predictions, 467 opportunities, 135 research value signals, and zero shadow/production labels.

## Follow-up cycle — temporal confirmation readiness

PXR-007 added a fail-closed, hash-bound audit that must pass before retrospective PXR-006 family-specialist evidence can be called a later temporal confirmation. It compares dataset fixture/timestamp keys, detects removed rows and changed historical targets, and counts only additions strictly after the prior dataset cutoff.

The latest registered candidate dataset contained 22,282 rows versus 22,277 in the PXR-006 baseline. It added five clean fixtures on one date, removed none, changed no overlapping targets, and added nothing inside the already-inspected era. Five rows are below the frozen 100-row readiness floor, so no specialist was fitted or scored and no final-fold evidence was recycled as confirmation.

Prediction quality did not improve and candidate quality did not change. Experiment validity improved because an apparently new dataset can no longer trigger a misleading confirmation rerun merely because its hash changed. PXR-006 remains research-only; no role, calibration, probability scope, prediction, price, opportunity, shortlist rule, or warehouse row changed. Classification remains `RESEARCH_AND_SHADOW`.

The latest report's auxiliary research pipeline was also reconciled. It renders eight finite one-per-fixture Top Forecasts, two finite one-per-fixture Research Basket hypotheses, zero strict Validated Research rows, and zero shadow/production opportunities. The basket's +0.73-unit model expectation is a tracked hypothesis with unresolved competition, margin, uncertainty, and champion evidence—not an execution claim. Both concise selectors now reject non-finite decision values explicitly.

Verification: 260 tests passed, Ruff passed, mypy passed for 171 source files, warehouse integrity passed, the readiness artifact digests reproduced, and the latest persisted report reconciled to 25 expected/terminal fixtures, eight predictions, 330 opportunities, 145 research value signals, and zero shadow/production labels.
