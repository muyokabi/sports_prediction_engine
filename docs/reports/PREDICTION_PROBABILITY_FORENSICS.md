# Prediction Probability Forensics

> Historical evidence only. See `docs/reports/CURRENT_IMPLEMENTATION_STATUS.md` for current model governance.

Date: 2026-10-10 (Africa/Nairobi)

## Verdict

The active Dixon–Coles probabilities are mathematically coherent and are not a hidden constant-prior output, but they
are **not uniformly reliable across competitions or market families**. Global 1X2 calibration is good; league-level
evidence is heterogeneous and often too small. The system now persists that distinction and requires an exact
model-version + market-family + competition validation before a row can become `PRODUCTION_ACTIONABLE`.

No current output is approved for real-money decision support. The warehouse has no settled fixture with a stored
pre-match odds snapshot, no settled shadow opportunity, and no score-model market-family champion. A large apparent
reference return is therefore a hypothesis for prospective tracking, not a reliable wager.

## Independent checks on the active output

Final analysis run `ed159426-e0c7-4ff1-9424-953946c0b447` used immutable model
`dixon-coles-20261010T104725895417Z-39eeeebc` and reconciled 125/125 fixtures.

- 1X2 probabilities summed to one with maximum error `5.55e-16`.
- The 369 stored 1X2 selection probabilities ranged from `0.1490` to `0.6326` and contained 354 distinct values at six
  decimals. The model is not emitting one generic vector for every fixture.
- BTTS probabilities ranged from `0.2981` to `0.7019`; totals ranged from `0.0025` to `0.9936` because the board includes
  alternate lines. Extreme alternate-line probability is not itself an error.
- Every displayed candidate remains `SHADOW_ACTIONABLE/WATCH`, has null execution edge, and requires a fresh manual
  operator-price check. API-Football is a reference feed, not an execution venue.

## Chronological probability evidence

The latest four-fold walk-forward evaluation contains 1,904 out-of-sample predictions:

| Metric | Dixon–Coles result |
|---|---:|
| Log loss | 1.054578 |
| 95% chronological block-bootstrap interval | 1.04178–1.06817 |
| Brier score | 0.635710 |
| Ranked probability score | 0.222855 |
| Expected calibration error | 0.011938 |
| Unique probability-vector fraction | 0.9018 |

Confidence buckets were close to empirical accuracy overall: 0.30–0.40 predictions averaged 0.383 confidence versus
0.398 accuracy; 0.40–0.50 averaged 0.443 versus 0.443. The 0.50–0.60 bucket averaged 0.536 versus 0.603, which is not
large enough under the predeclared material-gap rule to invalidate the global report but remains visible.

Global evidence masked material competition differences. With a predeclared minimum of 100 chronological predictions,
ECE at most 0.08, valid probability geometry, and log-loss/Brier upper confidence bounds inside the model evidence
policy, only these leagues currently pass:

| Competition | Rows | ECE | Log-loss upper bound | State |
|---|---:|---:|---:|---|
| Serie A | 127 | 0.0325 | 1.0935 | VALIDATED |
| Major League Soccer | 142 | 0.0675 | 1.1360 | VALIDATED |
| Liga Profesional Argentina | 109 | 0.0429 | 1.1030 | VALIDATED |

Examples that do not pass include Premier League (99 rows, ECE 0.0921), Bundesliga (64, 0.1435), Premiership (35,
0.1246), League One (57, 0.1291), and La Liga (64 rows despite ECE 0.0665). These are now blocked by persisted scope
evidence rather than hidden behind the global average.

## Defects found and fixed

1. Aggregate calibration could authorize an unproven competition. Migration 033 adds immutable
   `model_probability_scope_validations`; evaluation writes exact league evidence and analysis fails closed with
   `COMPETITION_PROBABILITY_NOT_VALIDATED`.
2. Probability geometry had no standard forensic record. Every probability evaluation now reports normalization,
   bounds, non-finite values, duplicate concentration and entropy.
3. Score-model applicability used a history threshold without model-specific chronological proof. A threshold of five
   recency-weighted team matches was selected on validation and confirmed on untouched test data before being persisted.
4. A crash inside a 20-fixture detail batch could checkpoint past unwritten fixtures. The page and its checkpoint are now
   committed atomically, so restart is lossless.
5. Aged API references were allowed, as required, but could dominate the candidate ranking and the report copy could be
   read as a betting instruction. Age remains non-vetoing, while current references rank first, aged rows carry
   `AGED_REFERENCE_RECHECK_REQUIRED`, and reports show every production-gate failure.

## Why the engine still abstains from real money

The model has no time-correct settled odds baseline against which to prove residual value. The odds ledger began on
2026-10-08 and currently covers only future/unsettled fixtures. There is also no settled prospective shadow sample,
validated score-market uncertainty/margin policy, or score-model market-family champion. Dixon–Coles now passes the
global MATCH_ODDS calibration gate and is persisted as a challenger, but is correctly withheld on the missing time-correct
market baseline and paired superiority evidence. These are statistical evidence
gaps; inventing a promotion would make the probabilities more misleading, not more executable.

The methodological basis is consistent with proper-scoring and calibration literature: probability quality must be
judged by proper scores and reliability, not hit rate or realized ROI alone. See
[Gneiting and Raftery](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf), the original
[Dixon–Coles model](https://doi.org/10.1111/1467-9876.00065), and the recent football calibration study
[Probability calibration in sports forecasting](https://journals.sagepub.com/doi/10.1177/22150218261416681).

## Operational meaning

- `PRODUCTION_ACTIONABLE / BET_IF_PRICE_AVAILABLE`: all model, fixture, league, market-family, calibration, uncertainty,
  margin and baseline gates passed; the operator must still verify an executable price.
- `SHADOW_ACTIONABLE / WATCH`: eligible only for prospective paper measurement; never a betting pick.
- `RESEARCH_VALUE_SIGNAL / NO_BET`: discrepancy worth investigation but one or more safety gates failed.
- `RESEARCH_ONLY` or `PRICE_TARGET`: a model price exists, but there is no conditional opportunity.

This makes the output honest today and creates the ledger required to become real-money decision support after enough
prospective outcomes exist.
