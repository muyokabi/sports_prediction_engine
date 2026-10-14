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

## Re-audit implementation research — 2026-10-13

| Source / evidence | Finding | Evidence type | Implementation implication |
|---|---|---|---|
| [API-Football documentation](https://api-sports.io/documentation/football/v3), plus immutable raw odds payloads captured 2026-10-13 | API-Football's Asian Handicap values repeat the home-team line on both selections (`Home -1` and `Away -1`); the away selection therefore uses the inverse selected-team handicap. Double Chance is returned as overlapping `Home/Draw`, `Home/Away`, and `Draw/Away` selections, and some bookmaker books omit one selection. | Provider-specific and directly observed | Preserve the home-perspective handicap inversion. De-vig a complete three-selection double-chance book to total mass two; never manufacture the missing leg of an incomplete book. Canonicalize only observed deterministic aliases. |
| [API-Football official getting-started guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide), accessed 2026-10-13 | Odds history is short-lived and lineups commonly arrive shortly before kickoff, with later availability in some competitions. | Provider-specific | Keep odds, injuries, and lineups observation-time restricted. A later complete injury snapshot supersedes an earlier snapshot; lineup membership must come from the exact stored observation, never a mutable current table. |
| [scikit-learn time-series cross-validation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) and [probability calibration](https://scikit-learn.org/stable/modules/calibration.html), accessed 2026-10-13 | Evaluation must preserve temporal order; calibration must be learned from predictions not used to fit the corresponding base estimator. | Official implementation guidance | Retain chronological validation/test evidence and its calibrator, freeze the selected specification, then refit only the deployable base model on all observations. Do not recompute or optimize holdout scores after deployment refit. |
| [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency) and [database copy](https://duckdb.org/docs/stable/sql/statements/copy), accessed 2026-10-13 | DuckDB coordinates writes within one process; multiple processes require application coordination. Native database export/copy is schema-sensitive. | Official database guidance plus repository experiment | Continue single-writer operation. Backup creation now rejects a filesystem copy unless source-before, target, and source-after SHA-256 digests are identical; this proves byte stability without claiming unsupported concurrent snapshot semantics. |

No new model family or actionability threshold was introduced from this research. The changes repair timing, market mathematics, artifact lineage, and operational fail-closed behavior; quantitative promotion still requires new chronological and prospective market evidence.

## API-Football data-availability research — 2026-10-12

This follow-up was performed before applying the new market-evidence policy to the production registry. It distinguishes provider limitations from defects in the engine. API-Football remains the sole integrated reference provider.

| Source / evidence | Finding | Evidence type | Implementation implication |
|---|---|---|---|
| [Official API-Football beginner guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide), accessed 2026-10-12 | Pre-match odds are typically published before a fixture, update periodically, are paginated, and only seven days of history are retrievable. A query for an eight-day-old fixture returns no odds by design. | Provider-specific | Historical odds must never be reconstructed or treated as a recoverable backfill gap. Capture prospectively and keep immutable snapshots. Lack of historical odds must not suppress football probabilities; it blocks only claims requiring market evidence. |
| [Official full-fixture collection tutorial](https://www.api-football.com/news/post/how-to-get-all-fixtures-data-from-one-league), accessed 2026-10-12 | `fixtures?ids=` accepts at most 20 fixture IDs and can return events, lineups, team statistics, and player statistics for those fixtures in one response. Completed/in-progress status filtering avoids waste. | Provider-specific | Retain verified 20-ID batching and quota-aware fallback. Do not plan three detail calls per fixture when the batched fixture response supplies the components. |
| [Official quota optimization guidance](https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage), accessed 2026-10-12 | League/season coverage flags should be checked, but enabled coverage is not a guarantee that every match has the data immediately. Future/new competitions may change coverage and lineups can arrive during or after a match. | Provider-specific | Coverage is a planning signal, never proof of per-fixture completeness. Optional detail remains explicit missingness; actionability uses fixture-level evidence. |
| [Official API-Football beginner guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide), lineup section, accessed 2026-10-12 | Lineups commonly appear 20–40 minutes before kickoff, but can appear later and for some competitions only 24–72 hours after the match. | Provider-specific | A backfilled lineup is a completed-match fact but is not evidence that the lineup was known pre-match. Only a stored observation timestamp at or before the prediction cutoff may enter a pre-match availability/lineup feature. |
| Production `provider_capabilities`, observed 2026-10-12 16:43 Africa/Nairobi | The active plan was `Pro`, active, with a 7,500 daily and 300 per-minute allowance; 4,796 daily calls remained after the latest run. | Persisted live evidence | There is enough capacity for disciplined daily prospective odds capture and high-value batched match detail, but the protected reserve and priority order remain necessary. |
| Production odds ledger, queried 2026-10-12 | 33 snapshots covered 22 fixtures, 10 bookmakers, 182 provider market IDs, and 108,309 prices. Match Winner, Asian Handicap, Goals O/U, BTTS, Exact Score, Double Chance, and home/away team totals had deterministic supported mappings; most other observed markets remained explicitly unsupported or research-only. | Persisted live evidence | Keep the raw taxonomy broad while pricing only mappings with deterministic semantics and tested settlement. Provider breadth is not model qualification. |
| Production detail ledger, queried 2026-10-12 | 18,767 completed packages had core event/score/lineup evidence; team statistics were present for 16,886 and player statistics for 15,212. A further 36,965 completed replay fixtures were score-only/unassessed. | Persisted live evidence | Score-distribution models may use reconstructable scores from the larger ledger. ML feature audits must disclose optional-stat coverage and missingness; no detail field may be invented to make a row look complete. |
| Production injury collections, queried 2026-10-12 | Seven complete date-level collections preserved 601 known-team observations across 13 fixtures. Recent responses also contained 155 rows for teams outside the local governed universe, which were ignored while raw payloads were retained. | Persisted live evidence | Global date queries naturally include out-of-scope teams. Ignoring them is not missing data for governed fixtures, but the warning and raw provenance must remain visible. Injury features are observation-time facts and cannot be reconstructed historically. |

### Provider-constrained policy decision

The provider limitation changes what can be proven, not whether the system should issue predictions:

1. **Prediction availability:** a chronologically qualified score model may continue to publish research probabilities, expected goals, coherent score-derived prices, and fair odds from reconstructable event-time facts even when no historical odds baseline exists.
2. **Reference comparison:** any currently available API-Football observation may be displayed with age, bookmaker, movement, dispersion, and manual-execution caveats. Quote age is not an arbitrary veto.
3. **Production betting label:** when policy explicitly requires statistically significant market outperformance, zero baseline rows cannot count as a passed gate. The system remains research/shadow until prospective capture supplies the predeclared sample.
4. **Unavailable data:** missing historical odds, pre-match injuries, and pre-match lineups are `UNKNOWN`, not zero, negative evidence, or permission to use post-match retrievals.
5. **Data expansion:** prioritize daily odds capture and 20-ID fixture batching. Do not spend quota attempting to repair provider data that official coverage and actual payloads show is optional or unavailable.

### Provider season identity finding — 2026-10-12

The local provider catalog legitimately contains future-dated seasons for individual competitions: a 2028 tournament row and multiple 2027 rows existed while the current Premier League mapping was season 2026. Therefore, the catalog-wide maximum `provider_season` is not a valid definition of the current season for an unrelated competition.

Provider access checks and capability metadata must preserve the exact `(provider league ID, provider season)` pair from one admitted competition-season mapping. They must never combine a globally selected season with a hard-coded league. The faulty diagnostic queried `/teams?league=39&season=2028` and received zero results; the corrected exact pair `/teams?league=39&season=2026` returned 20 teams on 2026-10-12. This defect affected Doctor and capability reporting, not daily collection, bootstrap, odds collection, analysis, or season rollover: those operational paths were audited and already derive exact league/season pairs from their target competition-season or fixture.

## Independent source recheck — 2026-10-13

The final adversarial pass rechecked the implementation decisions against current primary/official sources rather than relying only on the prior audit narrative.

| Source | Rechecked finding | Evidence type | Audit implication |
|---|---|---|---|
| [Dixon & Coles (1997)](https://doi.org/10.1111/1467-9876.00065), accessed 2026-10-13 | The football-score model is a dynamic Poisson-regression extension motivated by low-score dependence; complexity is not itself evidence of superiority. | Empirical / peer reviewed | Retain Dixon-Coles as a chronologically tested research core/challenger; do not introduce a more complex model without an untouched temporal comparison. |
| [scikit-learn `TimeSeriesSplit`](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html), accessed 2026-10-13 | Time-ordered splits prevent training on future observations and testing on the past. | Official implementation guidance | Preserve expanding chronological evaluation and candidate-bound fold evidence; random evaluation remains prohibited. |
| [scikit-learn calibration API](https://scikit-learn.org/stable/api/sklearn.calibration.html), accessed 2026-10-13 | Calibration methods produce probability estimates that must remain valid probabilities. | Official implementation guidance | A zero-mass or non-finite calibrator result is now an explicit failure. The former uniform one-third fallback was removed because it manufactured a decision-critical distribution. |
| [API-Football beginner guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide), accessed 2026-10-13 | Pre-match odds retain only seven days of history. | Provider-specific | The missing historical market baseline remains an evidence deficit, not a backfill defect; it blocks promotion but not research pricing. |
| [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency), accessed 2026-10-13 | Stable read-write operation is coordinated within one process; multi-process access requires an explicit boundary/design. | Official database guidance | Keep the current single-writer lock and document the server boundary rather than migrating speculatively. |
| [Python `pickle` documentation](https://docs.python.org/3/library/pickle.html), accessed 2026-10-13 | Pickle is unsafe for untrusted or potentially tampered data; integrity protection is required before deserialization. | Official security guidance | Retain immutable legacy artifacts for research-only compatibility, but require a matching recorded SHA-256 digest for the model and calibrator before any production market-role promotion. A digest detects replacement but does not establish external provenance, so artifacts must still originate from the trusted local training pipeline. |

## Transactional governance recheck — 2026-10-14

The append-only promotion repair was checked against current DuckDB primary documentation before implementation.

| Source | Rechecked finding | Evidence type | Audit implication |
|---|---|---|---|
| [DuckDB transactions](https://duckdb.org/docs/current/sql/statements/transactions), accessed 2026-10-14 | DuckDB transactions provide ACID behavior and multi-statement rollback. | Official database guidance | Migration 034 rebuilds the assessment table and creates/seeds role events as one migration transaction; a partial governance history must not become the accepted state. |
| [DuckDB constraints](https://duckdb.org/docs/preview/sql/constraints), accessed 2026-10-14 | Primary/unique constraints create ART indexes and enforce row uniqueness. | Official database guidance | Event identifiers remain unique, while the former `(model, family, role)` uniqueness that forced reassessment overwrite was removed from the assessment history. |
| [DuckDB indexes](https://duckdb.org/docs/lts/sql/indexes), accessed 2026-10-14 | ART indexes improve highly selective access but have update and memory tradeoffs. | Official database guidance | The role-event ledger uses a compact ordered lookup and current-role projection; no speculative broad indexing or database migration was introduced. |

This is an evidence-model correction, not evidence of predictive edge. Append-only role history enables point-in-time governance checks; it does not satisfy the missing prospective market baseline, settled-shadow sample, or competition qualification required for real-money actionability.

## Operational performance source recheck — 2026-10-14

The persistence optimization was checked against current provider and database guidance before replacing row-at-a-time hot paths.

| Source | Rechecked finding | Evidence type | Audit implication |
|---|---|---|---|
| [API-Football quota optimization guidance](https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage), accessed 2026-10-14 | Reference and semi-dynamic endpoints should be cached/refreshed according to how often their content can change; coverage is still not a per-fixture guarantee. | Provider-specific | Content-checkpoint an unchanged `/leagues` catalog, while still fetching and raw-preserving the provider response and reprocessing any changed content. Do not use the checkpoint to invent missing downstream coverage. |
| [API-Football beginner guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide), accessed 2026-10-14 | `/odds` is paginated, retains only seven days, and cannot be reconstructed retroactively. | Provider-specific | Keep complete prospective pagination and immutable odds snapshots. Optimize local taxonomy persistence, not the required provider collection or point-in-time evidence. |
| [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency), accessed 2026-10-14 | In-process writes use MVCC/optimistic concurrency. Multi-process native-file writing now has a Quack remote option, but the documented implementation is beta in DuckDB 1.5.2. | Official database guidance | Continue the proven coordinated single-writer boundary for this repository. Do not introduce a beta remote protocol or speculative storage migration during a local persistence optimization. |
| [DuckDB transactions](https://duckdb.org/docs/current/sql/statements/transactions), accessed 2026-10-14 | Multi-statement transactions roll back as a unit. | Official database guidance | Preserve the provider page as the recovery unit: bulk component writes and checkpoint advancement remain inside one transaction. |

The hypothesis was that observed 40–65 second provider-call gaps were dominated by local small-statement overhead, not network latency. Real-ledger measurements supported it: set-based typed relations materially reduced competition, taxonomy, and 20-fixture detail persistence time without changing the statistical model, provider data requirements, or actionability gates.

## Final primary-source recheck — 2026-10-14

| Source | Rechecked finding | Evidence type | Final implication |
|---|---|---|---|
| [API-Football official beginner guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide), accessed 2026-10-14 | The current v3 guide states that pre-match odds retain only seven days, full date/league surfaces are paginated, lineups usually appear shortly before kickoff and may arrive only after the match for some competitions, and optional fixture/player fields can be null. | Provider-specific official guidance | Preserve prospective capture, complete pagination, observation-time restrictions, and explicit `UNKNOWN`; do not attempt to reconstruct absent historical market or lineup state. |
| [API-Sports quota optimization](https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage), accessed 2026-10-14 | Cache duration should follow endpoint volatility, pagination is part of completeness, current response headers expose daily/minute budget, and retries can themselves waste quota. | Provider-specific official guidance | The catalog content checkpoint, durable pagination, header-driven quota accounting, protected reserve, and per-retry reauthorization remain justified. |
| [scikit-learn time-series validation](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-of-time-series-data) and [probability calibration](https://scikit-learn.org/stable/modules/calibration.html), accessed 2026-10-14 | Random IID splitting is inappropriate for temporally correlated observations; a calibrator should be fitted on predictions independent of base-model training, and multiclass per-class calibration requires normalization and complete class representation. | Official implementation guidance | Retain chronological folds, disjoint calibration evidence, complete-class gates, and explicit rejection of invalid/non-finite/zero-mass calibrated output. |
| [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency), [transactions](https://duckdb.org/docs/current/sql/statements/transactions), and [bulk insert guidance](https://duckdb.org/docs/current/data/insert), accessed 2026-10-14 | Native read-write remains a coordinated single-process boundary; transactions provide rollback/snapshot isolation; row-at-a-time insert loops carry material overhead and bulk statements are preferred. Quack multi-process writing is still documented as beta. | Official database guidance | Keep the proven single-writer lock and atomic page transactions. The set-based persistence change is supported; a speculative server-storage migration is not. |

This recheck did not justify a new model family, a weaker promotion gate, an odds-age veto, or a real-money label. It supports the implemented operational improvements and the existing fail-closed evidence boundary.

## Score-family validation research — 2026-10-14

| Source | Relevant finding | Evidence type | Experiment implication |
|---|---|---|---|
| [Dixon & Coles (1997)](https://doi.org/10.1111/1467-9876.00065), accessed 2026-10-14 | The model is a dynamic Poisson-regression score model with a low-score dependence correction; family behavior must be derived from the score distribution rather than inferred from 1X2 quality. | Peer-reviewed football-model evidence | Retain coherent score-derived BTTS and totals probabilities and compare the low-score correction with the Poisson ablation on identical fixtures. |
| [Gneiting & Raftery (2007)](https://doi.org/10.1198/016214506000001437), accessed 2026-10-14 | Strictly proper logarithmic and quadratic/Brier scores encourage honest probability forecasts; calibration and sharpness are distinct. | Primary statistical literature | Use binary log loss and standard binary Brier loss as primary family metrics. ECE is a diagnostic, not a standalone promotion rule. |
| [scikit-learn probability calibration](https://scikit-learn.org/stable/modules/calibration.html) and [Brier loss](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html), accessed 2026-10-14 | Binary reliability compares observed event frequency with the quoted positive-class probability; Brier loss is the mean squared probability error. | Official implementation guidance | Evaluate BTTS yes and over 2.5 directly. Do not reuse multiclass top-label confidence ECE or the multiclass Brier scaling. |

PXR-001 rejected blanket family validation. Global Dixon–Coles ECE was 0.0351 for BTTS and 0.0411 for totals, but proper-score differences versus fold-local empirical baselines were unresolved and competition calibration was unstable. The result supports future score-distribution-preserving calibration research, not independent binary recalibration, gate weakening, or market-family promotion.
