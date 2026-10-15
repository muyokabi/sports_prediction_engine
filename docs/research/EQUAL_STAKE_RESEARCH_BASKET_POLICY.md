# Equal-Stake Exploratory Research Basket Policy

Verified design date: 2026-10-14 (Africa/Nairobi).

Policy version: `equal-stake-research-v1`.

## Purpose

The research terminal must be useful before real-money promotion is possible. It therefore separates four questions:

1. **Top Forecasts:** what outcome does the model consider most likely?
2. **Research Basket:** which price-qualified hypotheses are worth tracking with equal research units?
3. **Validated Research:** which rows also pass competition-specific probability validation?
4. **Top Opportunities:** which rows have earned shadow or production governance status?

The first two views do not change `prediction_decisions`, model roles, opportunity governance, or production actionability. They expose and organize immutable research predictions that already exist. They must never be described as safe bets.

## Economic hypothesis

No individual football prediction is deterministic. A research process can therefore study a diversified group of individual fixtures rather than depend on one supposedly certain low-price selection. Equal units make outcomes comparable and prevent subjective confidence labels from silently changing exposure.

For one unit staked at decimal odds `O`:

- gross return after a win is `O` units;
- net profit on that position is `O - 1` units;
- the win can offset `O - 1` other lost one-unit positions;
- one winner covers all stakes in an `N`-selection basket only when `O >= N`.

Consequently, a 4.0 winner covers a three-selection equal-unit basket with a one-unit profit, but it does not cover a ten-selection basket. A 1.26 winner produces only 0.26 units of profit, but a high payout alone is not evidence of value. The decision-relevant quantity remains settlement-aware expected return:

`expected return = model probability-weighted settlement return at the observed reference price`.

The policy ranks by positive expected return first and payout reach second. It does not maximize odds, hit rate, or an invented confidence grade in isolation.

## Top Forecasts contract

Top Forecasts selects at most one `MATCH_ODDS` outcome per fixture and at most ten fixtures. A row must:

- have `HIGH` or `MEDIUM` applicability;
- contain a finite probability strictly between zero and one and a valid fair price;
- not depend on a global-prior substitution, an unseen team, or an out-of-domain state.

Bookmaker odds, a champion role, competition validation, and a market baseline are not required because this view makes no value or execution claim. The table is never padded with prior-only output.

## Exploratory basket admission

The equal-stake research basket selects at most one row per fixture and at most ten rows. A row must have:

- `HIGH` or `MEDIUM` fixture applicability;
- a valid model probability, fair odds, and provisional minimum odds;
- a persisted API-Football reference with timestamp, bookmaker, and observation count;
- reference odds at or above the provisional minimum;
- positive calculable model-expected return;
- globally validated calibration for the exact market family;
- adequate reference-bookmaker breadth;
- no extreme model-market disagreement;
- no prior-only, unseen-team, or out-of-domain dependency.

Competition-level probability validation is intentionally an **unresolved warning**, not an exploratory-basket veto. This is the controlled research risk: the position is visible and measurable precisely because its competition transfer remains unproven. Competition validation remains mandatory for the stricter Validated Research view and production governance.

Rows are ordered by:

1. model-expected return at the persisted API-Football reference;
2. decimal-odds payout reach;
3. model probability;
4. deterministic fixture/market keys.

There are no `A`, `B`, “sure bet,” or other subjective setup grades. Applicability, calibration, price provenance, and unresolved evidence remain separate fields.

## Basket accounting

The report assigns one notional research unit to each selected row and displays:

- total research units at risk;
- sum of model-expected net units;
- model-expected basket ROI;
- average reference odds;
- count of selections at odds 3.0 or higher;
- count of selections whose individual payout could cover the whole displayed basket;
- per-row other-stake offset and one-hit basket coverage.

Expected values are model-dependent estimates, not guarantees. Expected returns add linearly without an independence assumption, but variance, drawdown, and simultaneous losses depend on correlation. Fixture diversification alone does not prove independence.

## Governance boundary

This policy does not:

- promote a model or market family;
- turn `RESEARCH_VALUE_SIGNAL` into `SHADOW_ACTIONABLE` or `PRODUCTION_ACTIONABLE`;
- invent unavailable operator prices, injuries, lineups, or historical odds;
- convert API-Football reference odds into executable odds;
- authorize real-money staking;
- weaken the historical point-in-time market-baseline requirement;
- overwrite immutable predictions or evidence.

The exploratory basket exists to generate visible, reproducible hypotheses for prospective settlement and later chronological evaluation. Any future change to admission or ranking requires a stated hypothesis, versioned policy, regression coverage, and evaluation on a genuinely later temporal period.
