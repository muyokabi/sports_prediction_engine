# Institutional Improvement Research

Reviewed 2026-10-11. Primary papers and official documentation were used. Sources were rechecked online during the final audit and accessed on 2026-10-11.

The focused follow-up on model count, pretrained alternatives, CPU/Colab training, current artifacts, and the recommended compact model architecture is in [MODEL_STRATEGY_DEEP_RESEARCH.md](MODEL_STRATEGY_DEEP_RESEARCH.md).

| Source | Finding | Applied conclusion |
|---|---|---|
| [Dixon & Coles (1997)](https://doi.org/10.1111/1467-9876.00065) | Low-score dependence and time weighting can improve association-football score models. Empirical football-model evidence. | Retain Dixon-Coles as a challenger and compare chronologically; do not assume it beats Poisson. Weighted-rho fitting remains an experiment. |
| [Gneiting & Raftery (2007)](https://doi.org/10.1198/016214506000001437) | Strictly proper scores reward honest full probability distributions. Theoretical and empirical forecasting evidence. | Promotion must enforce the evaluator's complete probability-forensics verdict, not merely selected headline metrics. |
| [scikit-learn `TimeSeriesSplit`](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) | Time-ordered splitting prevents training on future observations. Official implementation guidance. | Candidate-specific walk-forward reports reproduce that candidate's features, hyperparameters, and calibration inside each fold. |
| [CatBoost classification objectives](https://catboost.ai/docs/en/concepts/loss-functions-classification) | Probabilistic objectives do not by themselves establish out-of-sample calibration. | CatBoost remains a challenger behind later-period calibration and exact-candidate gates. |
| [API-Football guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide) and [quota guidance](https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage) | Pagination and quota accounting are part of data correctness. | Durable request telemetry and resumable checkpoints are first-class evidence; completed replay seasons are not refetched on resume. |
| [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency) | A local file database should use a coordinated writer. Official database guidance. | Preserve exclusive job locks and serialized writes; the README explicitly warns against concurrent write commands. |
| [Baker & McHale, modified Kelly](https://www.sfu.ca/~tswartz/papers/kelly.pdf) | Estimation uncertainty should reduce exposure. | Fractional Kelly cannot substitute for validated uncertainty and return-margin policies; missing policy fails closed. |

## Decisions from this audit

1. Exact model lineage and exact evaluation-candidate identity are decision-critical. Family- or dataset-level similarity is insufficient.
2. Probability vectors and all policy values must be finite, bounded, and correctly normalized before any market decision.
3. A failed provider run must report requests from durable evidence, not only in-memory counters.
4. Historical bootstrap is idempotent only if completion is bound to the exact season universe and corroborated by local rows.
5. Additional model complexity was not justified by the available evidence. No new model family or optimistic threshold was introduced.
6. A failed aggregate probability-forensics verdict invalidates a champion even when global averages look acceptable; incumbents are now reassessed and demoted fail-closed.
7. Discovery can safely broaden historical evidence collection without equating collection admission with production actionability.
8. Historical odds remain unreconstructable; live prospective collection is required even after match-history backfill.

## Required future evidence

Continue prospective pre-match odds and shadow-outcome accumulation. Compare models against de-vigged references on identical timestamp-correct fixtures, use blocked uncertainty intervals, freeze uncertainty/margin policies before a later test era, and only then consider promotion. Never reconstruct unavailable historical odds or select thresholds on final-test ROI.
