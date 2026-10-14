# Codex Prediction-Path Research Prompt

Use this prompt for recurring autonomous improvement runs focused on prediction
quality. Codex should read the repository's current evidence before acting and
continue from the highest-value unresolved hypothesis instead of restarting a
general platform audit.

---

You are taking ownership of the prediction-research path in a mature quantitative football intelligence codebase.

Your task is to perform an **autonomous, evidence-driven prediction-quality research and improvement cycle**.

The objective is not to perform another general codebase audit.

The objective is to improve the system's ability to generate the strongest, best-calibrated, most stable and most defensible football prediction candidates supported by the available evidence.

"Best prediction candidates" means:

- strong out-of-sample probability quality;
- honest calibration;
- fixture-specific applicability;
- controlled uncertainty;
- stable chronological performance;
- coherent probabilities across related markets;
- useful performance against meaningful baselines;
- transparent reasons for inclusion or rejection;
- no leakage, invented data or unjustified confidence.

It does **not** mean:

- maximizing the number of daily selections;
- maximizing historical ROI;
- selecting the largest model-market disagreements;
- weakening gates to generate candidates;
- claiming certainty;
- forcing a model promotion;
- producing bets every day.

A run with zero qualified candidates is valid when the evidence warrants abstention.

## 1. Non-negotiable repository rules

Read and follow `AGENTS.md` before making changes.

Also read the current versions of:

- `docs/audits/CURRENT_SYSTEM_BASELINE.md`
- `docs/audits/IMPROVEMENT_REGISTER.md`
- `docs/research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md`
- `docs/reports/CURRENT_IMPLEMENTATION_STATUS.md`
- `docs/operations/RUNBOOK.md`

Preserve these invariants:

1. A qualified score model must continue producing research probabilities and fair prices even when it is not approved for real-money actionability.
2. API-Football remains the sole integrated reference-odds provider.
3. Historical results and completed-match facts are `RECONSTRUCTABLE_EVENT_TIME`.
4. Odds, injuries, lineups and market movement are `OBSERVED_POINT_IN_TIME` unless actually captured before kickoff.
5. Preserve explicit `UNKNOWN`; never invent neutral values or observations.
6. Never restore an arbitrary quote-age veto.
7. Model fair odds, API-Football reference odds, minimum acceptable execution odds and unknown operator odds must remain distinct.
8. Competition admission, fixture applicability, market-family qualification, calibration, uncertainty and risk are independent gates.
9. Market-family qualification must not leak between 1X2, BTTS, totals, handicaps, team totals, correct score or secondary markets.
10. Never mutate immutable predictions, model artifacts or evaluation evidence.
11. Use chronological evaluation only.
12. Every feature dataset must retain its feature-quality sidecar.
13. Do not claim real-money readiness merely because tests pass or predictions exist.

## 2. Scope of this run

Concentrate on this path:

persisted football evidence
→ point-in-time features
→ statistical and ML models
→ score/probability distributions
→ calibration
→ fixture applicability
→ model comparison or ensemble
→ uncertainty
→ market-family prices
→ candidate filtering and ranking
→ prospective validation.

Work outside this path only when it directly blocks prediction correctness, experiment validity or candidate quality.

Do not spend the run on:

- generic HTML redesign;
- broad operational refactoring;
- speculative server architecture;
- cosmetic documentation;
- unrelated data collection;
- adding unsupported markets;
- repeating closed audits without new contradictory evidence.

Do not rewrite functioning architecture merely to create activity.

## 3. Establish the current prediction baseline

Before changing quantitative behavior, reproduce the current state from code, persisted artifacts and the production warehouse.

Identify:

- the research-usable score model;
- active champions and challengers by market family;
- training dataset and cutoff;
- feature set and feature-quality sidecar;
- calibration method and calibration sample;
- chronological fold definitions;
- evaluation metrics;
- fixture-applicability policy;
- competition-scope validation;
- uncertainty and minimum-odds policy;
- candidate-ranking logic;
- prospective market and shadow evidence.

Measure the current baseline using, where applicable:

- multiclass log loss;
- Brier score;
- ranked probability score;
- calibration error and reliability tables;
- score-distribution diagnostics;
- goal-total calibration;
- performance by probability bucket;
- performance by competition;
- performance by applicability state;
- performance by team-history depth;
- performance across chronological periods;
- market-family performance;
- paired loss against the incumbent;
- de-vigged market baseline on identical point-in-time fixtures;
- bootstrap or block-bootstrap uncertainty;
- number and rate of prior-only or out-of-domain predictions.

Do not rely only on aggregate averages. Search for unstable subgroups and failure clusters.

## 4. Select the highest-value prediction hypothesis

Use current evidence to select the smallest number of high-value hypotheses that can be tested rigorously in this run.

Prioritize hypotheses likely to improve:

1. probability calibration;
2. chronological generalization;
3. score-distribution quality;
4. difficult-fixture handling;
5. unseen or low-history team treatment;
6. competition transfer and partial pooling;
7. model stability;
8. market-family-specific prediction quality;
9. uncertainty discrimination;
10. candidate precision.

Examples include:

- improved time decay;
- dynamic home advantage;
- regularized team-strength estimation;
- hierarchical or partial-pooling competition effects;
- bivariate or overdispersed score models;
- better promoted/unseen-team initialization;
- opponent-adjusted form;
- feature-family ablations;
- better calibration;
- score-distribution-preserving calibration;
- constrained statistical/ML ensembles;
- applicability-aware model selection;
- disagreement-aware candidate filtering;
- competition-specific reliability policies.

Do not implement several fashionable models without a clear hypothesis.

If the evidence shows that data quality, leakage, calibration or applicability is the dominant limitation, fix that before adding model complexity.

## 5. Research before quantitative changes

For every substantial modelling change, consult authoritative evidence where internet access is available.

Prefer:

- peer-reviewed football forecasting research;
- primary statistical literature;
- official scikit-learn documentation;
- official CatBoost and LightGBM documentation;
- primary calibration and time-series-validation literature;
- primary literature on model comparison and uncertainty;
- official API-Football documentation for provider constraints.

Record:

- source;
- access date;
- relevant finding;
- evidence type;
- applicability to this ledger;
- proposed hypothesis;
- reasons to apply or reject it.

Do not implement complexity merely because it is academically interesting.

## 6. Experimental contract

For each hypothesis, follow:

RESEARCH
→ PREDECLARE HYPOTHESIS
→ FREEZE BASELINE
→ DEFINE TRAIN/VALIDATION/TEST ERAS
→ IMPLEMENT CHALLENGER
→ RUN CHRONOLOGICAL EVALUATION
→ COMPARE ON IDENTICAL FIXTURES
→ QUANTIFY UNCERTAINTY
→ RUN ABLATIONS/SENSITIVITY
→ PROMOTE, RETAIN AS CHALLENGER OR REJECT
→ REGRESSION TEST
→ DOCUMENT.

The final temporal test must remain untouched until the specification, features, calibration method and thresholds have been selected using earlier data.

Never tune on the final test period.

Never select a model because it has the best realized betting ROI alone.

## 7. Required model comparison

Compare every serious challenger against:

- the current incumbent;
- a simple interpretable baseline;
- other relevant model families;
- the de-vigged API-Football market baseline where genuine point-in-time observations exist.

Use identical fixture sets and prediction cutoffs.

Compare:

- mean loss;
- paired fixture-level loss differences;
- chronological block-bootstrap confidence intervals;
- calibration;
- worst-period behavior;
- competition-level stability;
- low-history/unseen-team performance;
- score-distribution behavior;
- model-market residual stability.

Allow the conclusion `NO_CLEAR_WINNER`.

Do not promote a challenger based on a tiny, statistically ambiguous metric difference.

A simpler model should win when added complexity does not provide defensible incremental information.

## 8. Feature research

Audit active features for:

- temporal availability;
- coverage;
- null and NaN rates;
- variance;
- unique values;
- stability;
- drift;
- leakage;
- target contamination;
- model importance;
- incremental chronological value.

Run feature-family ablations where practical.

Candidate feature families include:

- goals and result strength;
- opponent-adjusted form;
- shots and shots on target;
- possession and passing;
- set pieces;
- discipline;
- rest and congestion;
- home/away effects;
- ratings;
- player-strength aggregates;
- lineup continuity;
- point-in-time availability;
- competition and season effects.

Provider-dependent all-null or constant fields may remain explicit in the dataset but must not be represented as fitted information.

Do not keep a feature merely because it sounds football-relevant.

## 9. Calibration and distributional coherence

Treat calibration as a primary objective.

Evaluate calibration:

- globally;
- by chronological block;
- by competition;
- by market family;
- by probability bucket;
- by applicability tier;
- by odds band where point-in-time references exist.

Calibration must use validation-only or otherwise out-of-sample predictions.

Reject non-finite, negative, zero-mass or non-normalized outputs.

Do not casually calibrate 1X2 probabilities in a way that destroys consistency with the underlying score distribution.

For score-derived markets, investigate distribution-preserving calibration where justified.

Discrimination without calibration is insufficient for candidate qualification.

## 10. Fixture-specific applicability

Every prediction must carry fixture-specific applicability evidence:

- home-team training representation;
- away-team training representation;
- effective recency-weighted matches;
- competition representation;
- fitted-versus-prior contribution;
- critical missing inputs;
- model version;
- training cutoff;
- domain similarity;
- applicability classification.

Prior-like output may remain visible for research pricing, but it must not be ranked as a top candidate.

Candidate selection must fail closed for:

- `PRIOR_ONLY`;
- `OUT_OF_DOMAIN`;
- unsupported unseen-team states;
- insufficient critical history;
- unvalidated model-specific applicability.

## 11. Uncertainty and candidate quality

Improve candidate selection, not merely raw prediction generation.

Use evidence such as:

- parameter or bootstrap variation;
- fold variance;
- model disagreement;
- calibration uncertainty;
- effective sample size;
- prior dependence;
- feature missingness;
- competition reliability;
- out-of-domain distance;
- unexplained model-market disagreement.

Do not call a heuristic a confidence interval.

Do not call unadjusted expected value "robust EV."

Extreme model-market disagreement is an investigation trigger, not automatically a top opportunity.

The strongest candidate should be the strongest after applicability, calibration, uncertainty, price, competition and correlation checks—not simply the largest raw edge.

## 12. Market-family research

Evaluate market families separately.

At minimum distinguish:

- `MATCH_ODDS`;
- `SCORE_DISTRIBUTION`;
- `BTTS`;
- `TOTAL_GOALS`;
- `ASIAN_HANDICAP`;
- `TEAM_TOTALS`;
- `CORRECT_SCORE`.

A good 1X2 model is not automatically calibrated for BTTS or totals.

Only add or promote a market-family model when:

- settlement semantics are deterministic;
- historical labels are trustworthy;
- chronological evaluation exists;
- calibration is measured;
- applicability is defined;
- uncertainty is governed.

Keep unsupported families research-only.

## 13. Candidate-ranking objective

Design the research-candidate funnel around precision and defensibility.

The funnel should be:

requested fixtures
→ valid prediction
→ fixture-applicable
→ supported market
→ calibrated for exact family
→ competition-scope validated
→ usable API-Football reference
→ positive reference discrepancy
→ uncertainty-qualified
→ minimum-price-qualified
→ risk/correlation-qualified
→ final candidate.

Rank qualified research candidates using transparent evidence such as:

1. applicability quality;
2. calibration quality;
3. competition reliability;
4. uncertainty;
5. normalized cushion above minimum acceptable odds;
6. expected return at the API-Football reference;
7. model agreement or validated ensemble strength;
8. model probability.

Do not invent an arbitrary weighted "confidence score" unless its weights are learned and validated chronologically.

Keep at most one primary candidate per fixture unless correlated exposure is explicitly modelled.

Never pad the candidate list.

## 14. Promotion rule

A challenger may be promoted only when:

- exact artifact and dataset lineage are verified;
- chronological evaluation is reproducible;
- calibration requirements pass;
- applicability policy is validated;
- paired comparison supports improvement or a clearly justified complementary role;
- market-family evidence exists;
- the untouched temporal test supports the decision;
- regression tests pass.

A model may remain:

- `RESEARCH_ONLY`;
- `CHALLENGER`;
- `NO_CLEAR_WINNER`;
- `REJECTED`;
- `CHAMPION`.

Do not manufacture a champion.

Lack of the historical point-in-time market baseline may block real-money promotion without suppressing research prediction.

## 15. Testing

Add meaningful tests for every material prediction-path change.

Prioritize adversarial tests for:

- temporal leakage;
- cutoff equality and timezone boundaries;
- target-derived features;
- unseen teams and competitions;
- prior substitution;
- all-null or constant features;
- invalid calibration output;
- probability-simplex violations;
- score-distribution coherence;
- model and artifact lineage;
- market-family role leakage;
- fixture applicability;
- candidate-ranking exclusions;
- extreme disagreement;
- reproducible chronological splits;
- immutable historical predictions.

Ask of each test:

"Would this fail if the quantitative implementation were subtly wrong?"

## 16. Iterative run behavior

This prompt will be used repeatedly.

Therefore:

- do not repeat a closed platform-wide audit without new evidence;
- do not recreate baseline documents unnecessarily;
- read the prior experiment history first;
- continue from the strongest unresolved prediction hypothesis;
- treat rejected hypotheses as useful evidence;
- avoid rerunning expensive experiments when the dataset and specification are unchanged;
- distinguish new evidence from previously established facts;
- append experiment results rather than rewriting history;
- prioritize marginal prediction improvement over general codebase activity.

If no responsible model improvement is supported, do not force a code change. A rigorous negative result is preferable to an unjustified model.

## 17. Required outputs

Maintain or create a durable prediction-research ledger containing:

- hypothesis;
- baseline;
- dataset hash;
- training, validation and test eras;
- feature set;
- model specification;
- calibration method;
- applicability policy;
- metrics;
- paired comparison;
- uncertainty interval;
- ablations;
- result;
- promotion decision;
- artifact paths;
- unresolved limitations.

Update:

- `docs/audits/IMPROVEMENT_REGISTER.md`
- `docs/research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md`
- `docs/reports/CURRENT_IMPLEMENTATION_STATUS.md`

Create or maintain:

- `docs/research/PREDICTION_EXPERIMENT_REGISTER.md`
- `docs/reports/PREDICTION_PATH_UPGRADE_REPORT.md`

Do not overwrite historical experiment conclusions.

## 18. Completion standard for this run

This run is complete only when it produces at least one defensible result:

- a verified prediction-path correctness defect is fixed;
- a challenger is chronologically proven superior and safely integrated;
- a useful ensemble is validated;
- calibration is materially improved;
- applicability or uncertainty becomes more discriminating;
- candidate precision is materially improved;
- a plausible hypothesis is rigorously rejected, preventing unjustified complexity;
- an evidence deficit is precisely measured and the next experiment is clearly defined.

Before finishing:

- rerun the relevant chronological evaluation;
- rerun adversarial tests;
- run the full test suite when production code changed;
- run Ruff and mypy;
- verify migrations and warehouse integrity when relevant;
- reconcile at least one real generated prediction report with persisted rows;
- state whether prediction quality actually improved;
- state whether candidate quality actually improved;
- state what remains unproven.

## 19. Final verdict

End with a concise evidence-based verdict covering:

- baseline model and metrics;
- hypothesis tested;
- implementation made;
- chronological result;
- calibration result;
- paired uncertainty result;
- applicability result;
- candidate-funnel result;
- promoted, retained or rejected decision;
- tests and integrity checks;
- remaining limitations;
- next highest-value prediction experiment;
- current classification: `RESEARCH_ONLY`, `RESEARCH_AND_SHADOW` or `REAL_MONEY_DECISION_SUPPORT`.

Do not claim "absolute best" in a literal or guaranteed sense.

The target is the strongest defensible prediction system supported by the current data, not certainty.

Begin by reading the existing experiment and implementation evidence, reproducing the current prediction baseline, and selecting the single highest-value unresolved prediction hypothesis.
