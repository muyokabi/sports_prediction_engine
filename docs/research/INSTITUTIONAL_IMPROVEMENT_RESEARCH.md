# Institutional Improvement Research

Research accessed 2026-10-09. Primary papers and official documentation were preferred. Findings below influenced this run only where repository evidence supported the change.

| Source | Evidence type | Relevant finding | Implementation implication |
|---|---|---|---|
| [Dixon & Coles (1997), Applied Statistics](https://www.research.lancs.ac.uk/portal/en/publications/modelling-association-football-scores-and-inefficiencies-in-the-football-betting-market%28d16276a2-d6e0-483b-a708-1d29663f1992%29.html) | Empirical/theoretical | Low-score dependence and time weighting can improve football score modelling; complexity must be tested against a Poisson baseline. | Retain Dixon-Coles as a challenger/champion candidate; do not assume superiority. Record unweighted rho fitting as an experiment, not an automatic rewrite. |
| [Gneiting & Raftery, strictly proper scoring rules](https://doi.org/10.1198/016214506000001437) | Theoretical | Proper scores reward honest full probability distributions. | Keep log loss and Brier primary; do not promote on accuracy or ROI alone. |
| [Wheatcroft, football forecast scoring](https://www.degruyterbrill.com/document/doi/10.1515/jqas-2019-0089/html) | Football-specific empirical/theoretical | RPS adds ordinal assumptions and should not be the sole model selector. | Report RPS alongside log loss/Brier, never alone. |
| [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) | Official library guidance | Ordinary random CV can train on future data; time-ordered splits preserve direction. | Preserve chronological split/walk-forward evaluation and adversarial timing tests. |
| [CatBoost classification objectives](https://catboost.ai/docs/en/concepts/loss-functions-classification) | Official library documentation | Logloss and Brier are probability-oriented metrics; classifier output still requires out-of-sample calibration assessment. | Keep CatBoost as a challenger; accept neither raw discrimination nor calibration automatically. |
| [Niculescu-Mizil & Caruana, predicting good probabilities](https://icml.cc/Conferences/2005/proceedings/papers/079_GoodProbabilities_NiculescuMizilCaruana.pdf) | Empirical | Different classifiers produce characteristic probability distortions; Platt and isotonic calibration require held-out evidence. | Fit calibration only on the validation era and assess it separately on later data. |
| [LightGBM parameters](https://lightgbm.readthedocs.io/en/latest/Parameters.html) | Official library documentation | Multiclass probability objectives are supported, but probability quality and calibration are separate concerns. | Keep LightGBM behind validation-only calibration and promotion gates. |
| [API-Football guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide) | Official provider guidance | Odds bets/bookmakers are provider taxonomies, and pagination/rate limits are integral to collection. | Preserve raw IDs, canonical mappings, complete pagination, caching, and quota reserves; do not infer unsupported semantics. |
| [API-Sports quota optimization](https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage) | Official provider guidance | Multi-fixture requests reduce endpoint calls and pagination metadata must be followed to completion. | Retain verified multi-ID batching, page checkpoints, and complete-pagination reconciliation. |
| [DuckDB concurrency](https://www.duckdb.org/docs/current/connect/concurrency) | Official database documentation | File-backed DuckDB supports one read-write process; multi-process server writes need coordination or another boundary. | Keep DuckDB locally, serialize writes, and document the server-readiness boundary. |
| [Distributionally robust Kelly](https://arxiv.org/abs/1812.10371) | Theoretical | Growth-optimal stakes are sensitive to uncertainty in the estimated distribution. | Fractional Kelly is insufficient by itself; require validated uncertainty and margin policies before actionability. |

## Hypotheses and decisions

1. Requiring explicit decision gates would eliminate a silent permissive fallback without changing qualified outputs. This was implemented and regression-tested.
2. Exact training-lineage competition membership would reclassify falsely in-domain fixtures and can only reduce actionability. This was implemented and adversarially tested.
3. Replacing Dixon-Coles, adding a bivariate/hierarchical model, or changing decay may improve score forecasts, but the current ledger does not contain an experiment proving that. These changes were rejected for this run.
4. CatBoost currently has the best aggregate walk-forward log loss among the newest evaluated candidates, but its interval overlaps statistical models and no sufficient point-in-time market baseline exists. Promotion was correctly rejected.
5. Threshold selection from realized ROI would overfit a noisy downstream outcome. No EV, uncertainty, or staking threshold was tuned on final-test ROI.

## Required future experiments

Prospectively accumulate immutable pre-match market snapshots and shadow outcomes; compare calibrated candidates with de-vigged market probabilities on paired fixtures; run blocked bootstrap comparisons; validate uncertainty and margin policies on a validation era; then freeze them for a later test era. Separately benchmark weighted-rho Dixon-Coles and competition-aware partial pooling against the current score models. No experiment may reuse final-test outcomes for threshold selection.
