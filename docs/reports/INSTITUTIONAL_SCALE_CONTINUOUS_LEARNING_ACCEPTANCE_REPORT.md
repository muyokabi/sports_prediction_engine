# Institutional Scale and Continuous Learning Acceptance Report

> Historical evidence only. It does not describe the current warehouse or registry; see `docs/audits/CURRENT_SYSTEM_BASELINE.md`.

Acceptance date: 2026-10-08 (Africa/Nairobi)

## Outcome

The platform is no longer capped at ten leagues or governed by a universal 500-fixture rule. It now has automated competition discovery, separated discovered/observation/actionable universes, a 50-league production collection scope, model-family evidence policies, immutable candidate lineage, warm-start and full-refit paths, a production fundamental champion, run-integrated fresh odds, settlement feedback storage and an institutional HTML research terminal.

No opportunity was fabricated. ML remains research-blocked because the current historically backfilled point-in-time matrix contains no informative varying feature—not because it has fewer than an arbitrary number of rows.

## Live scale evidence

| Measure | Before | After discovery/bootstrap |
|---|---:|---:|
| Production collection competitions | 10 | 50 |
| Provider current competitions discovered | — | 1,240 |
| Observation-qualified discoveries | — | 58 |
| Actionable incumbent universe | 10 | 10 |
| Explicit youth/friendly/reserve rejection | — | 104 |
| Teams | 180 | 881 |
| Unique fixtures | 3,174 | 17,838 |
| Completed fixture skeletons | 534 | 8,870 |
| ML-eligible detailed fixtures | 276 | 463 after the controlled scaled backfill |

The bootstrap wrote 869 team observations and 14,562 fixture records (inserts plus safe updates). The controlled detailed-backfill run increased the eligible set to 463 and left 442 assessed fixtures pending repair. It was operator-bounded at a checkpointed fixture boundary; remaining enrichment is resumable. Collection admission is deliberately not actionability: all 40 additions remain observation-only pending actual odds/data/model evidence.

## Quota evidence

API-Football remained the only odds/data provider. The live account reported Pro, active, 7,500 daily and 300 per minute. Immediately after discovery and the complete 50-league bootstrap, persisted status showed 324 used and 7,176 remaining. Discovery used one catalog call plus status; bootstrap used status plus team and fixture calls, under the protected reserve. The backfill planner can now allocate up to 1,000 safe requests per run rather than the former 40-call development ceiling.

After the provider's daily reset and the live 19-page tomorrow-odds collection, the latest persisted capability observation showed 7,394 of 7,500 daily requests remaining. The final acceptance rerun was offline and consumed no provider quota.

## Evidence policy

Policies are exact and version-controlled in `config/models/evidence.yaml`. They measure rows, unique fixtures/teams, target class support, chronological holdouts/folds, feature ratio, missingness, calibration and held-test quality.

| Model | Research rows | Validation/test | Production validation/test | Calibration | Max log-loss / Brier |
|---|---:|---:|---:|---:|---:|
| Elo | 24 | 12 / 12 | 40 / 40 | 0 | 1.15 / 0.70 |
| Poisson | 24 | 20 / 20 | 40 / 40 | 0 | 1.15 / 0.70 |
| Dixon-Coles | 30 | 24 / 24 | 50 / 50 | 0 | 1.15 / 0.70 |
| Logistic | 30 | 30 / 30 | 75 / 75 | 75 | 1.12 / 0.68 |
| CatBoost | 30 | 40 / 40 | 100 / 100 | 100 | 1.12 / 0.68 |
| LightGBM | 30 | 40 / 40 | 100 / 100 | 100 | 1.12 / 0.68 |

These are family-specific minimum evidence requirements, not guarantees. A new informative-feature gate prevents tree/linear models from training on a constant matrix.

## Fundamental models

The initial 276-row qualification established that a regularized Poisson model could become actionable. After scaled enrichment, the final candidates used 272 chronological training, 131 validation and 60 unseen test fixtures from dataset `production-scale-2026` (`c25c3070-ac45-5196-a57c-6094c53011bb`).

| Model | State/status | Log-loss | Brier | RPS | ECE | Decision |
|---|---|---:|---:|---:|---:|---|
| Elo | production-actionable candidate | 1.017674 | 0.611881 | 0.233024 | 0.094862 | Retained challenger; it does not produce the score distribution required by the institutional core-market ledger. |
| Poisson | production-actionable retired champion | 1.029902 | 0.622219 | 0.238960 | 0.134260 | Actionable score engine, superseded by Dixon-Coles on held-out log-loss and Brier. |
| Dixon-Coles | production-actionable champion | 1.025738 | 0.619874 | 0.238570 | 0.128646 | Promoted as the immutable production champion; preserves the fitted low-score correction in every persisted market price. |

An earlier weakly regularized Poisson and Dixon-Coles pair produced log-loss above 4 and were explicitly rejected. Increasing regularization from 0.01 to 10 implements necessary partial pooling for sparse multi-league team effects and restored chronological generalization.

## ML research and continuous learning

Logistic, CatBoost and LightGBM research was attempted immediately. All eleven features in the existing historical backfill dataset are constant because strict source-observation cutoffs correctly prevent newly retrieved historical details from masquerading as information known before old kickoffs. Logistic was rejected after this diagnosis; CatBoost refused the matrix; LightGBM is now pre-emptively blocked with `NO_INFORMATIVE_MODEL_FEATURES`. This preserves point-in-time correctness.

Warm-start candidates create new immutable artifacts and retain `parent_model_version`; logistic uses validated sklearn warm start, CatBoost `init_model`, and LightGBM its prior booster. Clean full refits remain the benchmark. Scheduler triggers cover new observations, elapsed time, drift, calibration deterioration, league expansion and schema changes. No production champion is mutated.

## Principal run and research terminal

The principal `sports-engine run --date today|tomorrow|YYYY-MM-DD --days N` path now acquires its lock/job run, refreshes provider status, fetches all fresh odds pages for expected admitted fixtures, writes deduplicated snapshots, preserves unmatched evidence, settles completed prior predictions, refreshes performance rollups, analyzes the complete fixture universe and writes standalone HTML.

The live run for 2026-10-09 consumed all 19 odds pages and reconciled 63/63 fixtures; it preserved 122 unmatched provider fixture payloads rather than forcing associations. After the qualified-pricing integration, offline acceptance run `28909885-ac38-4789-9437-31bac1223677` again reconciled 63/63 and persisted 63 immutable institutional predictions plus 441 fundamental prices: 1X2, BTTS yes/no and over/under 2.5 for every fixture. All terminal states are `ANALYZED`. Odds health is honestly `STALE`, so the decision layer produced zero opportunities and zero exposure.

The HTML implements Overview, Top Opportunities, All Matches, Market Board, Model Health, Data Health and Audit sections; executive health, quota/model/data timestamps, filters, expandable fixture research, market matrix and escaped embedded data. Empty/no-model/no-opportunity states remain explicit.

## Validation and remaining limits

- Migrations 001–025 apply cleanly and migration 025 is applied to production.
- Warehouse integrity passed after scale-up.
- Ruff passed.
- Strict mypy passed over 154 source files.
- Full offline suite: 130 passed in 48.68 seconds.
- Combined line/branch coverage: 74% (130 passed in 80.20 seconds).
- Ruff format and lint pass; strict mypy passes over 153 source files.
- Detailed enrichment of 8,870 completed skeletons is inherently multi-run work; it is checkpointed, request-capped and reserve-protected rather than claimed complete.
- ML production actionability awaits naturally accumulated or prospectively observed varying point-in-time features.
- New observation leagues await measured odds/bookmaker/core-market quality and model calibration before actionability.
