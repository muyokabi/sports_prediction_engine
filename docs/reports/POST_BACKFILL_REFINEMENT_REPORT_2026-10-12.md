# Post-backfill refinement report — 2026-10-12

## Decision

Keep the existing Dixon–Coles champion. Do not promote the newly trained
expanded-universe candidates. Separate discovery collection from production
training: `ACTIONABLE` leagues train production candidates by default, while
`OBSERVATION` leagues remain available for explicit research.

## What the completed backfill actually produced

The successful `football.fetch_backfill.replay.last-5` run used 2,646 billable
requests. It registered 38,856 fixture skeletons and attempted 4,761 detailed
packages; 2,952 became ML-eligible and 1,809 were quarantined.

Request composition:

| Endpoint purpose | Requests | Provider rows |
|---|---:|---:|
| Batched detailed fixtures | 239 | 4,761 |
| Player-stat repairs | 1,662 | 2,750 |
| Team-stat repairs | 493 | 428 |
| Season fixture bootstrap | 125 | 38,856 |
| Team bootstrap | 125 | 2,220 |
| Discovery and historical catalog | 2 | 2,390 |

Warehouse state after the run:

| Measure | Value |
|---|---:|
| Provider competitions discovered | 1,241 |
| Governed historical collection universe | 40 competitions / 200 registered seasons |
| Replay fixtures / completed fixtures | 55,456 / 55,148 |
| Replay ML-eligible | 10,963 |
| Replay pending repair | 2,459 |
| Replay completed but not yet assessed | 41,726 |
| Production ML-eligible | 260 |
| Total eligible model rows | 11,223 |
| Historical odds snapshots | 0 |
| Total live odds snapshots | 7 snapshots for 6 fixtures |

This explains the apparent contradiction. Five seasons were registered for the
eligible league-season universe, but a 5,000-request detail cap cannot enrich
roughly 55,000 completed fixtures. The old command reported success without
making that distinction sufficiently prominent.

The repair backlog is empirical provider incompleteness, dominated by 1,512
fixtures missing both player-stat components, 690 missing both team-stat
components, and 376 missing both groups.

## League depth

The original ten actionable competitions still contribute exactly 8,271
training rows (8,011 replay plus 260 production). The completed run added 2,952
eligible rows from observation leagues. Their evidence is uneven: several have
more than 100 rows, while some have 0–20. Therefore “37 leagues with at least
one eligible match” is not equivalent to 37 mature model domains.

## Expanded-universe model experiment

All six families were full-refit on the immutable 11,223-row dataset
`post-backfill-refinements-20261012` and evaluated on the same 5,185
out-of-fold fixtures.

| Model | Log loss | Brier | RPS | ECE |
|---|---:|---:|---:|---:|
| CatBoost | 1.031843 | 0.620021 | 0.213875 | 0.009949 |
| Logistic | 1.033987 | 0.621456 | 0.214369 | 0.011781 |
| Dixon–Coles | 1.035277 | 0.622134 | 0.215286 | 0.015174 |
| Poisson | 1.035820 | 0.622337 | 0.215320 | 0.016488 |
| LightGBM | 1.040180 | 0.625257 | 0.216062 | 0.009792 |
| Elo | 1.041411 | 0.626501 | 0.217005 | 0.016567 |

Paired chronological block bootstrap found no significant all-metric dominance
among CatBoost, Logistic, Dixon–Coles, and Poisson. CatBoost did significantly
dominate LightGBM and Elo. This is not sufficient evidence to add CatBoost to
the deployable market-role allow-list.

Cohort analysis exposed the actual weakness:

| Model | Mature ten log loss | Observation-league log loss |
|---|---:|---:|
| CatBoost | 0.999116 | 1.059916 |
| Dixon–Coles | 1.009691 | 1.082735 |
| Poisson | 1.005413 | 1.061903 |

The expansion data are useful for research but are not yet interchangeable with
the mature training domain. Both new score candidates also failed a resolved
top-confidence calibration band and failed to outperform the incumbent, so the
promotion system correctly withheld them. A targeted Platt-calibrated
Dixon–Coles experiment worsened walk-forward log loss from 1.035277 to 1.049009
and retained the forensic failure; that candidate was explicitly rejected.

## Implemented refinements

- Automatic ML updates now use full refits. Warm starts remain an explicit
  research capability and are promotion-ineligible.
- Poisson and Dixon–Coles select regularization and decay half-life on a
  chronological validation window; Dixon–Coles rho fitting now uses the same
  time decay as team strengths.
- Walk-forward evaluation persists hash-bound, exact out-of-fold predictions.
- Multi-model historical training automatically writes paired chronological
  bootstrap comparisons.
- Calibration forensics use Wilson intervals and minimum materiality/sample
  thresholds instead of failing on a small raw band gap.
- Model manifests now contain feature missingness, cardinality, dominance, and
  variance audits.
- Production feature/training workflows admit replay history only from
  `ACTIONABLE` leagues. `--include-observation-leagues` enables the wider
  research experiment explicitly.
- Competition probability validation now uses canonical competition UUIDs and
  is attached only to the exact immutable model evaluated. This prevents
  same-name leagues from being merged and prevents evidence leaking across
  same-dataset versions.
- Historical country normalization no longer erases provider country metadata;
  the 40 affected warehouse competition records were repaired.
- Backfill output now reports total detail coverage, pending repairs, and
  unassessed completed fixtures, and explicitly instructs the operator to rerun
  the same resumable command when work remains.
- The current champion's probability scopes were regenerated under canonical
  IDs: all ten actionable competitions validated.

## Operational consequence

The system can generate tomorrow's fundamental prices with the incumbent
Dixon–Coles champion. A betting recommendation still requires fresh, correctly
associated pre-match odds and all pricing/risk gates. Historical odds cannot be
created by match backfill; they must accumulate prospectively through the live
daily workflow.

