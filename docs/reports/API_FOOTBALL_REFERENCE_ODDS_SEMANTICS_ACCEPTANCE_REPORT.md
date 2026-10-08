# API-Football Reference-Odds Semantics Acceptance Report

**Acceptance date:** 2026-10-08  
**Production ledger:** DuckDB schema 26  
**Principal live analysis:** `138c0458-db2a-42b3-8912-e1e21380a77c`  
**Historical re-analysis:** `20a0ebaa-7389-458f-957f-3649df507fcd`  
**Result:** **ACCEPTED**

## Executive conclusion

The fixed-time odds invalidation has been removed from production decision semantics. API-Football prices are now modeled as reference-market observations, not guaranteed operator execution prices. Quote age remains persisted and visible, but age alone cannot produce `NO_BET` or suppress a comparison.

For every qualified supported selection, the system now separates:

1. model fair odds;
2. the latest valid API-Football reference per bookmaker and its market summary;
3. the unknown operator execution price.

The system persists a settlement-aware minimum acceptable price and requires manual broker confirmation. A positive discrepancy is labeled `BET_IF_PRICE_AVAILABLE`, never as a guaranteed executable bet. `execution_edge` remains `NULL` until a future operator-supplied price exists.

The historical 63-fixture universe was repriced without rewriting its source snapshots. All 406 available selection comparisons were restored even though every reference was older than the former 180-minute cutoff. A subsequent genuine live run analyzed all 63 fixtures, consumed all 20 odds pages, wrote 61 new deduplicated snapshots, and produced a current-reference report.

## 1. Pre-change audit

The audit found the same universal time gate in three paths:

- `markets.decision.decide_wager` compared the newest observation with `decision_time - maximum_age` and added `NO_ACTION_STALE_ODDS`; any such reason forced `NO_BET`.
- `analysis.service._odds_status` reduced the fixture market state to `FRESH` or `STALE` using `maximum_odds_age_minutes=180`; the HTML surfaced a global stale-odds health warning.
- `sports.football.prediction.service` passed the configured maximum age into the decision engine, preserving the same veto in the compatibility prediction workflow.

The configuration key was `odds.maximum_age_minutes: 180`. The prior analysis run `28909885-ac38-4789-9437-31bac1223677` completed all 63 fixtures and persisted 441 fundamental prices, but it persisted no reference comparisons or opportunities. This was a market-semantics failure, not an absence of predictions.

## 2. Corrected semantic model

### Three distinct prices

| Field | Meaning | Execution claim |
|---|---|---|
| Model fair odds | Settlement-aware price implied by the football model | Valuation only |
| API-Football reference odds | Latest valid provider observation for a bookmaker/market/selection | Historical/reference observation |
| Operator execution odds | Price actually obtainable from an external broker | Unknown to this system |

The report's operational rule is now:

```text
Place only if the operator's actual broker price >= minimum acceptable odds,
and only if every non-price risk gate remains satisfied.
```

### Reference states

The new state model supports:

- `CURRENT_REFERENCE`
- `LATEST_PROVIDER_REFERENCE`
- `AGED_REFERENCE`
- `HISTORICAL_REFERENCE`
- `NO_REFERENCE_ODDS`
- `INVALID_REFERENCE`
- `POST_KICKOFF_INVALID`

`AGED_REFERENCE` is explicitly usable reference evidence. It says only that the newest known provider observation is older than the configured display band. The former configuration was renamed to `odds.aged_reference_minutes` to make that non-veto role explicit.

### Decision states

- `BET_IF_PRICE_AVAILABLE`: qualified positive reference discrepancy; manual price check required.
- `WATCH`: positive reference economics exist but the configured probability-advantage requirement is not met.
- `NO_BET`: reference economics or another strict gate does not qualify.
- `PRICE_TARGET`: football fair/minimum price exists without a valid API-Football market reference.

The compatibility prediction path also preserves evidence, calibration, history, exposure, malformed-price, post-kickoff, and started-fixture blocks. Quote age does not weaken these controls.

## 3. Reference selection and normalization

The analysis loads every observation available by the analysis timestamp and partitions no-vig normalization by snapshot, bookmaker, canonical market, and line. This fixes the prior risk of de-vigging different total/handicap lines as one outcome set.

For each bookmaker/market/selection/line, the newest semantically valid observation is selected first. Cross-bookmaker summaries are computed only after that step:

- best latest reference;
- worst latest reference;
- median consensus probability;
- bookmaker dispersion;
- total snapshot count;
- first-to-latest movement for the selected bookmaker.

An old high observation from a bookmaker can appear in movement history but cannot replace that bookmaker's newer lower observation.

Every selected reference persists provider update time, local collection time, prediction time, kickoff time, calculated age, bookmaker, market, selection, odds, snapshot provenance, first observed price, movement, and snapshot count.

## 4. Minimum acceptable odds

The implementation uses `SettlementDistribution.minimum_odds(required_expected_return)`:

```text
minimum decimal odds = 1 + (loss exposure + required expected return) / win exposure
```

Here:

- win exposure = full-win probability + 0.5 × half-win probability;
- loss exposure = full-loss probability + 0.5 × half-loss probability;
- pushes contribute neither profit nor loss.

This solves the complete outcome distribution and is valid for ordinary win/loss, pushes, half wins, half losses, and Asian quarter lines. The persisted method version is `settlement-distribution-v1`, together with probability source, uncertainty adjustment, and required robust-EV threshold.

For the current fundamental board, configured required robust EV and uncertainty adjustment are both zero, so minimum acceptable odds equal model fair odds. The schema and calculation support positive thresholds without changing settlement logic.

## 5. Persistence and migration

Migration `026_reference_odds_semantics.sql` applied successfully and advanced the production warehouse to schema 26. It adds:

### `market_reference_quotes`

Audited latest-per-bookmaker references with all required timestamps, age, provenance, price, movement, snapshot count, and semantic state.

### `institutional_opportunities`

Model probability, fair odds, settlement-aware minimum odds, method/version, uncertainty, required return, reference summary, reference/robust economics, decision, reasons, manual-confirmation flag, and constrained-null execution edge.

### `odds_age_research_results`

Research-only global/competition/bookmaker evidence by market family. `production_penalty_qualified` defaults to `false`; the workflow never activates an age penalty.

### `prediction_decisions` v2

Reference terminology, minimum acceptable odds, reference state, manual confirmation, conditional decision states, and a constrained-null execution edge. Existing decisions were copied forward.

## 6. Historical 63-fixture re-analysis

The persisted source ledger was repriced as-of its existing evidence. No raw payload, odds snapshot, fixture history, or earlier analysis was rewritten.

| Measure | Result |
|---|---:|
| Analysis run | `20a0ebaa-7389-458f-957f-3649df507fcd` |
| Fixtures expected / terminal | 63 / 63 |
| Fixtures analyzed | 63 |
| Institutional predictions | 63 |
| Fundamental prices | 441 |
| Fixtures with reference odds | 58 |
| Fixtures without reference odds | 5 |
| Selections compared | 406 |
| Latest-per-bookmaker reference rows | 2,914 |
| Distinct bookmakers | 10 |
| Positive reference discrepancies | 201 |
| `BET_IF_PRICE_AVAILABLE` | 154 |
| `WATCH` | 16 |
| `NO_BET` | 236 |
| `PRICE_TARGET` | 35 |

All 406 compared selections were classified `AGED_REFERENCE`; the other 35 prices were `NO_REFERENCE_ODDS` price targets.

Reference-age distribution:

| Minimum | Median | Maximum |
|---:|---:|---:|
| 498.7 minutes | 973.5 minutes | 973.5 minutes |

This is the central regression proof: references as old as roughly 16.2 hours were compared and reported rather than being automatically suppressed by the old three-hour rule.

## 7. Genuine live principal run

Command semantics exercised: `sports-engine run --date 2026-10-09`.

The first sandboxed network attempt failed at DNS resolution and was recorded as provider unavailable. The authorized live retry completed normally; no waiting for or fabrication of a provider refresh occurred.

Provider collection evidence:

- all 20 odds pages consumed;
- 193 provider fixture payloads observed;
- 61 new snapshots written;
- 132 unmatched provider fixtures preserved as raw evidence rather than forced into the ledger;
- 10 bookmakers represented in selected reference rows;
- provider quota after the run: 7,374 of 7,500 requests remaining, 296 of 300 minute requests remaining.

Analysis evidence:

| Measure | Result |
|---|---:|
| Analysis run | `138c0458-db2a-42b3-8912-e1e21380a77c` |
| Fixtures expected / terminal | 63 / 63 |
| Fixtures analyzed | 63 |
| Institutional predictions | 63 |
| Fundamental prices | 441 |
| Fixtures with reference odds | 58 |
| Fixtures without reference odds | 5 |
| Selections compared | 406 |
| Latest-per-bookmaker reference rows | 3,184 |
| Positive reference discrepancies | 201 |
| `BET_IF_PRICE_AVAILABLE` | 153 |
| `WATCH` | 19 |
| `NO_BET` | 234 |
| `PRICE_TARGET` | 35 |

All 406 compared selections were classified `CURRENT_REFERENCE` because a valid selected reference came from the live collection run. `CURRENT_REFERENCE` still does not imply broker executability.

Reference-age distribution:

| Minimum | Median | Maximum |
|---:|---:|---:|
| 63.6 minutes | 275.0 minutes | 291.6 minutes |

### Audited examples

These are reference comparisons, not execution instructions:

| Fixture | Market | Model p | Fair / minimum | Latest API reference | Bookmaker | Age | Reference edge | Robust estimate | Decision |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| Malaga vs Espanyol | BTTS Yes | 56.16% | 1.781 / 1.781 | 1.80 | Bet365 | 278.4m | 3.60pp | 1.09% | `BET_IF_PRICE_AVAILABLE` |
| NAC Breda vs MVV | BTTS Yes | 63.48% | 1.575 / 1.575 | 1.62 | Bet365 | 71.5m | 5.69pp | 2.83% | `BET_IF_PRICE_AVAILABLE` |
| Kashiwa Reysol vs Vissel Kobe | BTTS Yes | 59.47% | 1.682 / 1.682 | 1.73 | Betfair | 63.6m | 4.36pp | 2.88% | `BET_IF_PRICE_AVAILABLE` |

For every row, `execution_edge = UNKNOWN`. The operator must check the real broker and reject any actual price below the displayed minimum.

## 8. Odds-age research

The principal run now refreshes an append-only-snapshot research process for completed fixtures. It measures earlier pre-kickoff fair-probability observations against the final observed pre-kickoff price and can aggregate by global market, competition, and bookmaker when sample size permits.

The present production ledger has zero qualifying earlier/final observation pairs for completed fixtures. Accordingly:

- zero research rows were written;
- no age/movement correlation is claimed;
- no age penalty is active;
- `production_penalty_qualified = false` remains enforced by construction.

This is the honest result. Research will populate as the proprietary multi-snapshot ledger matures.

## 9. HTML acceptance

The institutional report now separates football pricing, market reference, and execution requirement. It includes:

- a prominent `MANUAL PRICE CONFIRMATION REQUIRED` banner;
- model probability, fair odds, and minimum acceptable odds;
- latest best API-Football reference and bookmaker;
- reference timestamp, age, snapshots, movement, and dispersion;
- reference edge and robust estimate;
- explicitly unknown execution edge;
- full price-target board, including `NO_REFERENCE_ODDS` rows;
- reference-coverage and age-distribution summary metrics;
- correct market-decision counts rather than subtracting selection candidates from fixture counts.

The global `Odds health: STALE` veto banner is gone. The generated live artifact is:

`artifacts/reports/analysis-2026-10-09-2026-10-09-138c0458-db2a-42b3-8912-e1e21380a77c.html`

After the final decision-count label correction, the exact same persisted market evidence was rendered once more in offline mode as:

`artifacts/reports/analysis-2026-10-09-2026-10-09-35c1b4f0-eb0a-4d18-97f0-edfd89964c56.html`

That final artifact reports 153 conditional candidates, 19 watch rows, 234 no-bet rows, and 35 price targets; it makes zero provider calls and labels each reference from its actual timestamp (`210 AGED_REFERENCE`, `196 LATEST_PROVIDER_REFERENCE`, `35 NO_REFERENCE_ODDS`).

## 10. Test and static-analysis evidence

The normal suite remained fully offline and passed after using a workspace-local pytest temp root required by the Windows sandbox.

| Gate | Result |
|---|---|
| Pytest | **137 passed** |
| Branch-aware coverage | **74%** overall |
| Ruff format check | **pass**, 200 files formatted |
| Ruff lint | **pass** |
| mypy | **pass**, strict mode, 156 source files |

Substantive acceptance coverage includes:

- aged reference remains usable;
- age alone does not force `NO_BET`;
- latest-per-bookmaker selection;
- old-best versus newer-lower price handling;
- multiple-bookmaker consensus and dispersion;
- movement history;
- no-reference football pricing and `PRICE_TARGET`;
- fair and minimum acceptable odds;
- unknown execution edge;
- manual threshold pass/fail;
- Asian quarter-line minimum odds;
- post-kickoff and malformed-reference invalidation;
- started-fixture invalidation;
- intervening-fixture/model-state blocking;
- line-specific no-vig normalization;
- research-only odds-age persistence;
- HTML terminology and manual confirmation notice;
- migration idempotence.

Coverage evidence was written to `artifacts/reports/coverage.json`.

## 11. Integrity and backup

- Production warehouse integrity audit: **passed**.
- Schema version: **26**, with 26 deterministic migrations registered.
- Verified backup: `artifacts/backups/api-football-reference-semantics-schema-26`.
- Backup verification: **schema 26, 1,927 files, 9 audited table-count entries**.

## 12. Acceptance decision

The corrected implementation satisfies the required principle:

> The latest API-Football reference is reported with its true age. The model's fair price and minimum acceptable execution price are separate. The operator must check brokers and proceed only at or above the minimum. No legitimate opportunity is rejected solely because the provider observation is older than an arbitrary number of minutes.

Football-data integrity, model qualification, point-in-time controls, fixture-started checks, intervening-fixture invalidation, settlement correctness, risk limits, provider provenance, and audit history remain strict.
