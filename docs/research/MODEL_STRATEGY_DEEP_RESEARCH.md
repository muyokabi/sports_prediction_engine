# Football Model Strategy: Deep Research and Repository Diagnosis

Reviewed 2026-10-11. This is a research and diagnosis report, not authorization to promote a model or place a wager.

Implementation and post-backfill empirical results are recorded in
[`POST_BACKFILL_REFINEMENT_REPORT_2026-10-12.md`](../reports/POST_BACKFILL_REFINEMENT_REPORT_2026-10-12.md).

## Executive verdict

The system should be **refined, not replaced by a downloaded pretrained model**.

Its data lineage, point-in-time feature construction, chronological testing, probability calibration, immutable registry, applicability controls, and fail-closed promotion design are substantially stronger than most public football-prediction repositories. The quantitative layer is not yet production-ready, however. The immediate weaknesses are not simply that six model families exist. They are:

1. model roles are not cleanly separated;
2. the promotion allowlist excludes all direct 1X2 ML models even though CatBoost currently has the best aggregate walk-forward score;
3. simply adding CatBoost to that allowlist would be unsafe because the deployed warm-start artifact and the walk-forward reconstruction are not the same training regime;
4. repeated warm starts add hundreds of trees using batches of only about 50 new observations and are degrading holdout quality;
5. the usable model history is not five complete seasons and covers only ten competitions;
6. there is no historical point-in-time odds, lineup, or availability signal in the active ML feature matrix;
7. the small differences among the leading models have not been shown to be statistically significant in a paired comparison.

The recommended production architecture is deliberately small:

- one score-distribution model for scorelines, totals, BTTS, handicaps, and correct score;
- one calibrated direct 1X2 model as a challenger or eventual 1X2 specialist;
- bookmaker consensus as an external benchmark, never as an assumed truth;
- logistic regression and Elo as diagnostic baselines rather than equal production candidates.

## What the current repository actually contains

### Usable training evidence

The latest feature dataset contains 8,271 eligible matches, but the phrase “five seasons” overstates the evidence actually used by the models.

| Provider season label | Rows | Competitions | Observed date range |
|---|---:|---:|---|
| 2023 | 2,029 | 10 | 2023-11-27 to 2024-06-02 |
| 2024 | 3,059 | 10 | 2024-07-27 to 2025-06-01 |
| 2025 | 2,923 | 10 | 2025-07-25 to 2026-05-31 |
| 2026 | 260 | 10 | 2026-08-30 to 2026-10-10 |

This is approximately 35 months, with partial first and last seasons, across the Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira Liga, Belgian Pro League, Scottish Premiership, and Turkish Super Lig. Discovery has catalogued 1,241 competitions, but discovery is not the same as collected, data-qualified, model-qualified, or actionable history.

### Feature evidence

The latest CatBoost manifest has 155 numeric features. None is constant. Only the two three-match red-card averages exceed 50% missingness. That is better than a sparse or broken matrix, but most columns are overlapping transformations of the same recent form and match-statistics families over 3-, 5-, 10-match, season, and exponentially weighted windows.

The dataset also contains columns for bookmaker probabilities, odds movement, player availability, injury counts, and lineup strength, but they are null or false for historical training and are excluded from the active numeric feature list. The model is therefore not learning from historical market prices, confirmed lineups, or injuries.

CatBoost importance is diffuse. The largest features are away opponent-adjusted goal difference (7.0%), Elo difference (4.1%), home opponent-adjusted goal difference (2.7%), then many correlated rolling statistics below 2%. This supports feature ablation and compression; it does not support adding more model families.

## Current model results

The latest walk-forward reports use four folds and 3,348 out-of-time predictions.

| Model family | Log loss | Brier | RPS | ECE | Probability forensics |
|---|---:|---:|---:|---:|---|
| CatBoost | **0.996288** | **0.594425** | **0.202204** | **0.011894** | Pass |
| Dixon-Coles | 0.998412 | 0.595419 | 0.203332 | 0.036498 | Fail |
| Poisson | 0.999406 | 0.595753 | 0.203388 | 0.030051 | Fail |
| Elo | 1.009713 | 0.603259 | 0.206386 | 0.046410 | Fail |
| Logistic | 1.009233 | 0.602326 | 0.204720 | 0.017489 | Pass |
| LightGBM | 1.012189 | 0.605357 | 0.206797 | 0.013260 | Pass |

CatBoost's advantage over Dixon-Coles is only 0.002125 log-loss units (about 0.21%), 0.000994 Brier units (about 0.17%), and 0.001128 RPS units (about 0.55%). Their bootstrap intervals overlap substantially. Because the repository does not retain paired per-fixture forecasts from every candidate in the report, this evidence does **not** establish that CatBoost is genuinely superior.

The score models fail the current forensic rule because their 70-80% confidence bands are materially underconfident: Dixon-Coles predicted 74.0% on 110 rows whose observed top-choice accuracy was 85.5%; Poisson predicted 74.0% on 116 rows whose observed accuracy was 84.5%. This is a real diagnostic, but a hard failure based on one equal-width bin and a ten-percentage-point boundary is statistically brittle. Research on calibration metrics shows that binning trades resolution against sampling variance and that equal-width ECE can be biased. The gate should remain fail-closed, but its replacement should use classwise reliability, equal-mass or cumulative diagnostics, and uncertainty intervals rather than merely relaxing the threshold.

### The warm-start defect in model strategy

The latest CatBoost artifact has 700 trees. It began with a tuned 100-tree full refit, then two automatic updates each appended 300 trees using only 49 and 51 new training observations respectively. There is no evaluation set or early stopping in those incremental fits.

| CatBoost candidate | Training mode | Incremental rows | Trees | Holdout log loss | Holdout Brier |
|---|---|---:|---:|---:|---:|
| Initial large-data candidate | Full refit | n/a | 100 | **0.997594** | **0.595967** |
| First update | Warm start | 49 | 400 | 1.016256 | 0.608860 |
| Latest update | Warm start | 51 | 700 | 1.020765 | 0.611056 |

The walk-forward evaluator uses the latest candidate's hyperparameters but trains a fresh model in each fold. It therefore reports the behavior of a fresh 300-tree CatBoost, not the exact 700-tree warm-start artifact that promotion would serve. Candidate holdout metrics partly constrain this mismatch, but the uncertainty and forensic gates come from the reconstructed model family. Promotion must be bound to the exact training protocol and artifact behavior.

The same pattern is worse in LightGBM: its full-refit holdout log loss of 0.998741 deteriorated to 1.032506 and then 1.064786 after small-batch warm starts. Logistic warm starts also deteriorated from 1.008677 to 1.058977 and 1.068038. At this scale, full refits are inexpensive and should be the default. Warm start should remain disabled until a replay experiment demonstrates benefit under the exact deployed update policy.

CatBoost's official documentation describes `init_model` as continuing learning from an existing model and provides validation-set overfitting detection and `use_best_model`. The current implementation uses continuation but neither control. See [CatBoost fit](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_fit) and [overfitting detector](https://catboost.ai/docs/en/concepts/overfitting-detector).

## What research says about model complexity

The literature does not support building a large “model zoo” and assuming diversity creates edge.

- A large experimental review of forty years of score-based football models found the leading methods produced very similar forecasts, suggesting a practical ceiling for generic result-only approaches. See [Hubáček, Šourek, and Železný (2022)](https://doi.org/10.1093/imaman/dpab029).
- Direct result models and hierarchical Poisson score models showed similar predictive behavior under purpose-built temporal validation. See [Tsokos et al. (2019)](https://discovery.ucl.ac.uk/id/eprint/10056079/).
- Recent 14-season English Premier League evidence found Bayesian dynamic state-space models strongest among the compared statistical methods, but no tested model beat bookmaker-average probabilities; differences among weighted Poisson, negative-binomial, Dixon-Coles, and bivariate-Poisson variants were barely distinguishable. See [Bayesian state-space models, JRSS C (2025)](https://academic.oup.com/jrsssc/article/74/3/717/7929974).
- A 2026 dynamic Bayesian study across the Bundesliga, EPL, and La Liga found adaptive time-varying attack and defence strengths improved over several dynamic comparators, while the market generally remained stronger. It also released reproducible code and the open-source `footBayes` package. See [Macrì-Demartino, Egidi, and Torelli (2026)](https://doi.org/10.1093/jrsssc/qlag032).
- The original Dixon-Coles approach remains relevant because it addresses low-score dependence and time decay, but it is not automatically superior in every league or test period. See [Dixon and Coles (1997)](https://doi.org/10.1111/1467-9876.00065).
- Proper scoring rules, not accuracy or realized betting return alone, are the correct primary way to compare probability forecasts. See [Gneiting and Raftery (2007)](https://doi.org/10.1198/016214506000001437).

This evidence argues for a small number of role-specific models, strong baselines, and rigorous paired evaluation. It does not justify six continually promoted peers, nor does it justify jumping directly to deep learning.

## Should an open-source pretrained model replace the current models?

No defensible drop-in pretrained match-pricing model was found.

Football match models are unusually dependent on their data contract: team identity resolution, competition strength, cutoff time, promoted-team treatment, season transitions, odds timestamp, and feature definitions. A serialized estimator trained on somebody else's feature schema and historical universe is not portable in the way an image or language foundation model can be. Even a good public artifact would require local chronological validation and recalibration; at that point, retraining its architecture locally is safer than trusting its weights.

One visible Hugging Face candidate, [`ruslanmv/sports-trends-models`](https://huggingface.co/ruslanmv/sports-trends-models), publishes a calibrated `HistGradientBoostingClassifier` and self-reports 0.980 log loss and 55% accuracy. It is useful as a reproducibility reference, not as this system's champion: the model card says its headline index metrics are indicative, its production metrics are version-specific, lower-tier coverage is uncertain, and it deliberately falls back to Elo or offline mock data. Its schema, league mix, calibration era, and prediction-time evidence are not equivalent to this repository's. Loading its pickle would also introduce untrusted deserialization and lineage risk.

Open-source **implementations** are useful:

- [`penaltyblog`](https://penaltyblog.readthedocs.io/en/latest/models/overview.html) offers CPU-friendly, Cython-optimized Poisson, Dixon-Coles, bivariate Poisson, zero-inflated Poisson, negative-binomial, Weibull-copula, Bayesian, and hierarchical models behind a common interface. It is suitable for reproducible challenger experiments, not a source of universal pretrained weights.
- [`footBayes`](https://cran.r-project.org/package=footBayes) implements static and dynamic double-Poisson, bivariate-Poisson, Dixon-Coles, negative-binomial, Skellam, and related Bayesian models. It is the strongest research candidate for testing dynamic partial pooling, though full MCMC may be slower than the present CPU workflow.

The correct reuse unit is therefore code and methodology, not foreign trained parameters.

## CPU and Colab recommendation

The current 8,271-row dataset is small by tabular-ML standards. CatBoost, LightGBM, logistic regression, Poisson, and Dixon-Coles all fit on CPU; a GPU is not needed. CatBoost's official API supports both CPU and GPU, and CPU is the natural reproducible default for this workload.

Colab is useful for isolated experiments with `footBayes`, PyMC/Stan, broader hyperparameter searches, or repeated bootstrap comparisons. It should not become a second unofficial production pipeline. A safe notebook workflow would:

1. export one immutable parquet dataset plus dataset hash, schema, cutoff, and split manifest;
2. reproduce the exact chronological folds;
3. write per-fixture probabilities for every challenger;
4. compare paired log loss, Brier, RPS, classwise calibration, and competition stability;
5. export parameters and a human-readable manifest, not an unreviewed pickle;
6. re-run the winning specification in the repository before registry admission.

For the existing tree models, local full refitting is simpler and safer than Colab.

## Recommended target architecture

### 1. Score-distribution role

Keep one deployable score model. Dixon-Coles is the incumbent research baseline. Benchmark it against, in order:

1. dynamic or time-weighted hierarchical Poisson with league and team partial pooling;
2. bivariate Poisson where empirical goal correlation warrants it;
3. negative-binomial or another overdispersed marginal only where dispersion tests justify it.

This role must output a coherent score matrix and serve totals, BTTS, Asian handicap, team totals, and correct score. A direct 1X2 classifier cannot replace it.

### 2. Direct 1X2 role

Retain calibrated CatBoost as the principal challenger, logistic regression as the transparent baseline, and remove LightGBM from automatic retraining unless an ablation shows incremental value. CatBoost should not be eligible for promotion until full-refit evaluation, artifact-bound evaluation, and prospective market comparison pass.

### 3. Rating role

Use Elo as an input, cold-start prior, and diagnostic baseline. It does not need to compete as a full production champion when richer models already consume its signal.

### 4. Market role

Use de-vigged multi-bookmaker consensus as the strongest available external benchmark and, later, as an explicitly market-informed model branch. Preserve a separate market-independent probability so apparent value is not created by circularly predicting the same odds being compared.

## Ordered experiments before any model promotion

1. **Disable incremental promotion evidence.** Reproduce every ML candidate by full refit and bind the walk-forward report to the exact training mode and hyperparameters. Compare full refit against the current update replay.
2. **Retain per-fixture fold predictions.** Run paired chronological block bootstrap differences between CatBoost, Dixon-Coles, Poisson, logistic, and bookmaker consensus. Overlapping standalone intervals are not enough.
3. **Run feature ablations.** Test Elo only; goals/form only; match statistics; discipline; player rating; congestion; opponent adjustment; and all features. Prefer the smallest stable feature set.
4. **Repair calibration assessment.** Add classwise reliability, equal-mass or cumulative calibration diagnostics, confidence intervals, and rolling-period stability. Evaluate multiclass temperature scaling alongside the current one-vs-rest Platt approach; scikit-learn notes that temperature scaling directly supports multiclass probabilities with one parameter. See [scikit-learn probability calibration](https://scikit-learn.org/stable/modules/calibration.html) and [Arrieta-Ibarra et al. (2022)](https://www.jmlr.org/papers/v23/22-0658.html).
5. **Benchmark one dynamic score challenger.** Start with hierarchical/dynamic Poisson, not several variants at once. Pre-register the metric and folds, then retain it only if it improves paired proper scores or materially improves score-distribution calibration.
6. **Expand data before expanding model complexity.** Collect and qualify additional leagues progressively. Evaluate league transfer and leave-one-league/time-block behavior; do not train all 1,241 discovered competitions indiscriminately.
7. **Accumulate prospective odds.** Seven current odds snapshots cannot support a credible market-baseline or value claim. Historical odds cannot be reconstructed from present observations.
8. **Shadow only.** Require a frozen prospective window before real-money eligibility. Track probabilities, reference odds, minimum acceptable odds, settlement, calibration, and closing movement.

## Decision

The repository is suitable for **research and shadow forecasting**, not real-money decision support. Its engineering and governance foundation is good; its model evidence is narrower than the operator believed, and its current continuous-learning policy is actively degrading the ML artifacts.

The best next model is not a downloaded black box. It is a correctly evaluated, full-refit CatBoost challenger for 1X2 plus one dynamic hierarchical score-model challenger, both judged against the existing Dixon-Coles model and prospective bookmaker consensus on identical point-in-time fixtures.

No model should be promoted merely because CatBoost currently tops the table. First fix the training/evaluation identity problem, prove the difference with paired out-of-time predictions, and gather enough market history to know whether any statistical improvement translates into a usable pricing advantage.
