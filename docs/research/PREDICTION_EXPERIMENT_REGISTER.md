# Prediction Experiment Register

This append-only register records predeclared chronological prediction experiments. A negative result is retained as evidence; it must not be rewritten into a promotion later.

## PXR-001 — Score-derived BTTS and total-goals family validation

**Opened / completed:** 2026-10-14 (Africa/Nairobi)  
**Decision:** `NO_CLEAR_WINNER / RETAIN RESEARCH_ONLY`  
**Production ledger mutation:** none. Evaluation used a byte-stable isolated warehouse copy whose source-before, copy, and source-after SHA-256 were all `6CDCB68388A7997BAD0C5C6ED8FE80668C5B50DA7D5AA5FBAC58828C313D0338`.

### Hypothesis and frozen contract

The exact current Dixon–Coles score model may already supply sufficiently calibrated BTTS and over/under 2.5 probabilities to justify market-family calibration and competition-scope validation. The hypothesis is accepted only if the untouched chronological evidence is finite and coherent, stable across folds and competitions, and useful against a fold-local empirical-rate baseline. No market-family calibration, scope row, shortlist gate, or role is written merely because global ECE passes.

Primary metrics are binary log loss and standard binary Brier loss. Diagnostics are direct-event ECE, equal-mass reliability with Wilson intervals, fold stability, competition stability, and contiguous chronological block-bootstrap intervals. Comparisons use identical fixture/cutoff rows. A family cannot borrow `MATCH_ODDS` evidence.

### Dataset and lineage

| Item | Evidence |
|---|---|
| Dataset | `automatic-models-20261013T220836790988Z` |
| Dataset hash | `9c5d616d445e807c6c6ff087f0f498429cfb5fd34274c8aec6bac68c84cdb879` |
| Schema hash | `36e70cd2185d9906be9f8ff357f9e861b45a25ca0cbd092e5bb3a6fc393ef853` |
| Rows / competitions / teams | 22,262 / 100 / 900 |
| Feature cutoff | 2021-07-22 through 2026-10-12 |
| Feature-quality sidecar | `data/parquet/features/automatic-models-20261013T220836790988Z-9c5d616d445e.parquet.feature-quality.json` |
| Sidecar exclusions | Four all-null lineup/player-availability columns and constant `lineup_strength_known` remain explicit and are not fitted information |
| Incumbent | `dixon-coles-20261013T223455579046Z-92b51b5e`, full refit, regularization 3.0, half-life 730 days, rho -0.0486195 |
| Simple comparator | `poisson-20261013T222434970208Z-9b5e4de3`, identical fitted rates/time weighting without the low-score rho correction |
| Calibration method | None; probabilities remain direct functions of the score matrix |
| Market baseline | Unavailable historically by provider retention policy; no market claim is made |

### Chronological folds

The established split contract was retained: `minimum_train_periods=7,099`, `test_periods=1,183`, four expanding folds, 9,460 total out-of-fold fixtures. Test eras were:

1. 2025-04-12 through 2026-01-06 — 2,163 fixtures.
2. 2026-01-07 through 2026-04-16 — 2,004 fixtures.
3. 2026-04-16 through 2026-08-13 — 2,217 fixtures.
4. 2026-08-13 through 2026-10-12 — 3,076 fixtures.

The fourth era remained untouched until the family definitions, losses, ECE bound, minimum competition sample, and comparison rule were frozen.

### Results

| Model / family | Log loss | Brier | ECE | Mean p / event rate | Worst fold ECE | Paired vs fold empirical baseline, log loss (95% block CI) | Paired vs baseline, Brier (95% block CI) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dixon–Coles BTTS | 0.691331 | 0.248950 | 0.035114 | 0.52537 / 0.54852 | 0.062313 | +0.002741 [-0.000364, +0.005676] | +0.001226 [-0.000273, +0.002646] |
| Poisson BTTS | 0.691948 | 0.249254 | 0.038796 | 0.52032 / 0.54852 | 0.064311 | +0.003358 [+0.000192, +0.006367] | +0.001529 [-0.000008, +0.002990] |
| Dixon–Coles totals 2.5 | 0.689288 | 0.247858 | 0.041127 | 0.50861 / 0.53626 | 0.067989 | -0.001346 [-0.006147, +0.003318] | -0.000886 [-0.003131, +0.001409] |
| Poisson totals 2.5 | 0.689288 | 0.247858 | 0.041127 | 0.50861 / 0.53626 | 0.067989 | -0.001346 [-0.006147, +0.003318] | -0.000886 [-0.003131, +0.001409] |

Lower loss is better; paired differences are model minus baseline. Intervals crossing zero are inconclusive. Poisson BTTS log loss is significantly worse than its simple baseline. Dixon–Coles BTTS is not resolved against that baseline. Totals are not resolved against baseline.

Dixon–Coles versus Poisson on identical fixtures:

- `MATCH_ODDS`: no significant dominance; log-loss difference -0.000355, 95% CI [-0.000842, +0.000124].
- `BTTS`: Dixon–Coles dominates Poisson statistically but trivially in magnitude; log-loss difference -0.000616 [-0.000837, -0.000397], Brier difference -0.000304 [-0.000412, -0.000196].
- `TOTAL_GOALS_2_5`: identical within numerical precision because the Dixon–Coles correction only redistributes 0-0, 0-1, 1-0, and 1-1 mass, all below 2.5 goals.

Competition diagnostics with at least 100 out-of-fold fixtures found 28 competitions. Only 18/28 passed ECE <= 0.08 for Dixon–Coles BTTS and 15/28 for totals. Worst ECE was 0.139854 for BTTS and 0.169635 for totals in Eerste Divisie. This is fixture-family evidence that global averages cannot safely be copied to every competition.

### Ablation / sensitivity interpretation

Removing the Dixon–Coles low-score dependence is the Poisson ablation. It weakens BTTS slightly and has no effect on over/under 2.5. The comparison therefore supports retaining Dixon–Coles as the research score model, but not family qualification. No arbitrary recalibration was fitted because a scalar binary calibrator would sever BTTS/totals from the common score distribution unless a score-distribution-preserving method were validated.

### Decision and artifacts

The hypothesis that current evidence supports blanket BTTS/totals validation is **rejected**. No `calibration_validations`, `model_probability_scope_validations`, role, threshold, historical prediction, or shortlist rule was changed. This prevents 483/519 previously uncalibrated live rows from being admitted on a misleading global average.

Artifacts:

- `artifacts/evaluation/2026/10/14/dixon-coles-9c5d616d445e-63f622e66a59.json`
- `artifacts/evaluation/2026/10/14/dixon-coles-9c5d616d445e-63f622e66a59.predictions.parquet`
- `artifacts/evaluation/2026/10/14/poisson-9c5d616d445e-f8e5a7f8df43.json`
- `artifacts/evaluation/2026/10/14/poisson-9c5d616d445e-f8e5a7f8df43.predictions.parquet`
- `artifacts/evaluation/2026/10/14/comparisons/model-comparison-9c5d616d445e-a07b827fc670.json`

### Unresolved limitations and next experiment

Historical point-in-time API-Football market probabilities remain unavailable, so no market-baseline or execution claim is possible. Competition samples are uneven; applicability tiers are not yet stratified inside the family report; and this experiment evaluates only BTTS yes/no and the 2.5 total line. The next highest-value experiment is a predeclared score-distribution-preserving calibration challenger (for example, validation-era scaling of goal intensities or a constrained mixture with league priors), selected before a new untouched temporal era and evaluated only in competitions with adequate samples. Continued prospective reference capture remains mandatory.

## PXR-002 — Global score-intensity calibration

**Opened / completed:** 2026-10-14 (Africa/Nairobi)

**Decision:** `REJECTED_ON_VALIDATION / RETAIN RESEARCH_ONLY`

**Production ledger mutation:** none. The source warehouse was opened read-only and probability-scope persistence was disabled. Only new immutable evaluation artifacts were written.

### Hypothesis and frozen contract

A single positive multiplier on both Dixon-Coles goal intensities may repair score-distribution calibration while preserving one coherent matrix for MATCH_ODDS, BTTS and TOTAL_GOALS_2_5. Folds 1-2 fit the scalar inside the predeclared range [0.5, 1.5]. Fold 3 is the validation gate. Fold 4 may be inspected only if validation scoreline log loss improves and no family log loss degrades by more than 0.001. The primary loss is negative log probability of the realized score; family proper losses and ECE are diagnostics. The fitted fold rho is retained.

### Dataset and baseline lineage

| Item | Evidence |
|---|---|
| Dataset / hash | `automatic-models-20261013T220836790988Z` / `9c5d616d445e807c6c6ff087f0f498429cfb5fd34274c8aec6bac68c84cdb879` |
| Sidecar | `data/parquet/features/automatic-models-20261013T220836790988Z-9c5d616d445e.parquet.feature-quality.json` |
| Model | `dixon-coles-20261013T223455579046Z-92b51b5e` |
| Four-fold baseline | 9,460 rows; log loss 1.027692; Brier 0.616561; RPS 0.213132; ECE 0.014923 |
| Development folds | 1-2 |
| Validation fold | 3: 2026-04-16 through 2026-08-13, 2,217 rows |
| Untouched experiment fold | 4; not inspected because validation failed |
| Market baseline | unavailable historically; no market or execution claim |

The regenerated artifact reproduced every stored baseline MATCH_ODDS, BTTS and totals probability from latent expected goals and rho with maximum absolute error 0.0.

### Validation results

The development scale was `0.9797795579802315`.

| Target | Baseline | Challenger | Paired challenger-minus-baseline loss (95% chronological block CI) |
|---|---:|---:|---:|
| Realized score log loss | 3.007913 | 3.011506 | +0.003593 [0.002368, 0.004965] |
| MATCH_ODDS log loss | 1.060802 | 1.060883 | +0.000081 [-0.000230, 0.000449] |
| BTTS log loss | 0.690809 | 0.692726 | +0.001917 [0.001161, 0.002677] |
| BTTS Brier | 0.248582 | 0.249521 | +0.000939 [0.000576, 0.001318] |
| TOTAL_GOALS_2_5 log loss | 0.695792 | 0.698844 | +0.003052 [0.001875, 0.004218] |
| TOTAL_GOALS_2_5 Brier | 0.250623 | 0.252068 | +0.001445 [0.000895, 0.002001] |

BTTS ECE worsened from 0.050671 to 0.059131 and totals ECE from 0.062508 to 0.073888. MATCH_ODDS ECE improved slightly from 0.033246 to 0.030069, but its proper loss did not improve and the shared distribution worsened materially elsewhere.

### Applicability and failure clusters

Fold-local representation was 1,938 both-teams-seen fixtures, 33 one-team-unseen, and 246 both-teams-unseen; 798 fixtures had either team below five training matches. Scoreline loss worsened for both-teams-seen rows by +0.003395 [0.001901, 0.004776], for both-unseen rows by +0.006091 [0.001866, 0.010908], and for the low-history group by +0.004101 [0.001962, 0.006932]. The small one-team-unseen subgroup was unresolved. A global scale therefore did not become useful after isolating fitted-team fixtures and supplies no new applicability discrimination.

### Decision and artifacts

The challenger failed the frozen validation gate and was rejected without opening fold 4. No calibrator, model artifact, role, family qualification, threshold, historical prediction, opportunity, or candidate-ranking rule was changed. Candidate quality and quantity are unchanged.

Verification after the evaluation-lineage change: 242 tests passed, Ruff passed, mypy passed for 164 source files, `git diff --check` passed, and production warehouse integrity passed. Analysis `ec603dc8-13c4-4431-aec7-eb3a4e51b017` was re-reconciled read-only to 12/12 terminal fixtures, ten predictions, 467 opportunities, 135 research value signals, and zero shadow/production labels.

Artifacts:

- `artifacts/evaluation/2026/10/14/dixon-coles-9c5d616d445e-7a42be875b91.json`
- `artifacts/evaluation/2026/10/14/dixon-coles-9c5d616d445e-7a42be875b91.predictions.parquet`
- `artifacts/evaluation/2026/10/14/score-intensity-calibration-9c5d616d445e-edb829e594c1.json`
- `artifacts/evaluation/2026/10/14/score-intensity-calibration-9c5d616d445e-edb829e594c1.predictions.parquet`

### Unresolved limitations and next experiment

The result rejects only one global total-intensity degree of freedom; it does not reject partially pooled competition effects, dynamic home advantage, or a constrained competition-prior mixture. Historical point-in-time market evidence remains unavailable, and the experiment did not create new candidate evidence. The next highest-value quantitative experiment is a predeclared partially pooled competition scoring-effect challenger with sparse-competition shrinkage, evaluated on sufficiently represented competitions and a genuinely later untouched era. Prospective API-Football reference accumulation remains mandatory.
