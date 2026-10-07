# Implementation Status

Last audited: 2026-10-07 (Africa/Nairobi)

Overall software state: `PRODUCTION_READY_AWAITING_CURRENT_SEASON_PROVIDER_ACCESS`

Production current-season qualification: `BLOCKED_BY_PROVIDER_PLAN`

The connected account is currently and expectedly Free. API-Football returned HTTP 200 but denied 2026 team data with its plan restriction. Development continues against an explicitly labeled 2024 replay ledger. No historical row is treated as an official current-season production record.

Status is based on exercised behavior, not file presence. The master implementation specification is authoritative.

## Phase 1 — Foundation

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Python 3.12 packaging with `uv`, `pyproject.toml`, lockfile | VERIFIED | `uv sync --all-groups`; wheel and sdist built. |
| Validated YAML/environment configuration | VERIFIED | Configuration exercised by CLI and test suite. Secret is stored only in ignored `.env`. |
| Structured configurable logging | VERIFIED | YAML-configured rotating file/console logging plus persisted structured job-run lifecycle and metrics. |
| CLI skeleton and meaningful exit codes | VERIFIED | Core groups plus tested read-only API quota command. Later-phase commands remain tracked in their phases. |
| Deterministic DuckDB migrations | VERIFIED | Migrations 001–019 apply from zero and rerun idempotently in `test_migrations.py`. |
| DuckDB connection and transactions | VERIFIED | Integration tests exercise clean migration and rollback-capable transaction helper. |
| Job-run infrastructure | VERIFIED | Success/failure lifecycle and metrics persistence covered by `test_job_runs.py`. |
| Provider base interface and typed API-Football client | VERIFIED | Wrapper, API errors, auth/parameter/rate-limit/plan typing, raw-first persistence, pagination and live authentication exercised. `ApiFootballPlanRestrictionError` retains endpoint, parameters, season, provider message, plan when known, and job-run ID. |
| Retry/backoff, safe retry classification, rate limiting | VERIFIED | 503 retry, API errors, terminal 429 typing/status and retry-after behavior covered by provider integration tests. |
| Pagination | VERIFIED | Unit pagination test. |
| Dynamic provider capability and quota discovery | VERIFIED | Typed capabilities model; `/status`; all four quota headers; persisted observations; dynamic limiter and budget. Mocked Free 100/10, Pro 7,500/300, upgrade, downgrade, and stale-status/header disagreement all pass. No plan-to-limit mapping exists. |
| Immutable raw payload and sidecar storage | VERIFIED | Integration test and live doctor payload. |
| `sports-engine api quota` | VERIFIED | Displays persisted plan, active state, daily used/limit/remaining, minute limit/remaining and observation time without consuming a request. |

Migrations: `001_core.sql` through `019_fixture_score_observations.sql`.

## Phase 2 — Football reference data

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Candidate league configuration | IMPLEMENTED | Ten configurable candidates in YAML. |
| Mandatory coverage gate | IMPLEMENTED | Pure coverage decision tested. |
| Coverage audit CLI and persistence | VERIFIED OFFLINE / REPLAY EXERCISED | Resumable, quota-safe persistence is integration-tested; all configured candidates were audited against accessible 2024 replay coverage. |
| Competition/season canonical IDs and provider mapping | VERIFIED OFFLINE | Deterministic IDs and repository writes are exercised. |
| Teams and squads/player reference ingestion | VERIFIED OFFLINE | Team/venue mappings and immutable squad snapshots are integration-tested. |
| Production/current vs development/replay separation | VERIFIED OFFLINE | Explicit app mode, replay season and `ledger_mode`; production never falls back. Live 2026 remains `BLOCKED_BY_PROVIDER_PLAN`. |

## Phase 3 — Fixture ledger

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Fixture bootstrap | VERIFIED OFFLINE | Checkpointed team/schedule bootstrap, restart at fixture stage, idempotency and append-only correction history are integration-tested. Live verification is replay-only until paid access. |
| Fixture normalization | VERIFIED OFFLINE | Metadata, status, overall and half/full/extra-time/penalty score states are normalized. Migration 019 makes detailed score corrections append-only observations. |
| Status history and schedule snapshots | VERIFIED OFFLINE | Repository integration tests exercise changed observations and current-view reconstruction. |
| Season discovery and rollover | IMPLEMENTED | Production-only current-season audit path retains prior seasons; live production verification is provider-blocked. |
| Reconciliation | VERIFIED OFFLINE | Quota-safe checkpointed fixture reconciliation is integration-tested. |

## Phase 4 — Detailed match ingestion

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Maximum-20 fixture batching | VERIFIED | `test_batching.py`. |
| Embedded event normalization/persistence | VERIFIED OFFLINE | Deterministic event rows and raw lineage are transactionally persisted. |
| Lineups and bench normalization/persistence | VERIFIED OFFLINE | Starting XI, bench, coach, formation, position and grid are persisted. |
| Team statistics normalization/persistence | VERIFIED OFFLINE | Required nullable fields preserve zero-vs-null semantics and additional fields. |
| Player statistics normalization/persistence | VERIFIED OFFLINE | Required nested statistics are flattened and original additional payload is retained. |
| Transactional complete match package | VERIFIED OFFLINE | Batched fixture package is validated and persisted in one database transaction. |
| Formal completeness and quarantine | VERIFIED OFFLINE | Fifteen explicit component states, eligibility, quality issue and deterministic quarantine artifact are tested. |

## Phase 5 — Daily updater

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Orchestration lock and job run | VERIFIED OFFLINE | `football daily` uses an exclusive file lock and persisted job-run lifecycle. |
| Global yesterday/today/tomorrow discovery | VERIFIED OFFLINE | Date-level calls are filtered locally to the selected production/replay ledger; integration test proves unrelated data is ignored. |
| New-completion detection and <=20 enrichment | VERIFIED OFFLINE | Already ML-eligible fixtures are not fetched again; full detail uses batches where supported. |
| Transactional normalization, quality and quarantine | VERIFIED OFFLINE / REPLAY EXERCISED | Atomic package tests pass. One live 2024 fixture fetched repair endpoints and was correctly quarantined for provider `NULL` mandatory statistics. |
| Idempotent rerun | VERIFIED OFFLINE | Repeated daily test does not re-enrich an eligible fixture or duplicate canonical rows. |
| Tomorrow schedule and odds handoff | IMPLEMENTED | Tomorrow discovery is persisted; odds runs only when the selected ledger advertises odds coverage. Replay correctly skips odds. |
| Predictions and excess-quota backfill in principal daily job | VERIFIED OFFLINE | Daily uses dynamically available surplus for bounded repair and invokes the champion prediction workflow only when tomorrow fixtures and a champion exist. |

## Phase 6 — Odds

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Odds schema and append-only grain | VERIFIED OFFLINE | Snapshot and price grain exercised; old observations are never overwritten. |
| Odds parsing | VERIFIED OFFLINE | Bookmaker, market, selection, over/under line and handicap line extraction tested. |
| Pagination and snapshot persistence | VERIFIED OFFLINE | Service consumes every provider page, stores known fixtures, reports unknown fixtures and deduplicates identical near-simultaneous observations. |
| `football odds tomorrow` | IMPLEMENTED | Functional paginated command; it makes no request when selected ledger coverage says odds are unavailable. |
| Implied probability, no-vig and overround | VERIFIED | Unit and repository integration tests. Consensus across bookmakers remains a Phase 12 consumer. |

## Phase 7 — Backfill planner

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Dynamic surplus calculation | VERIFIED OFFLINE | Planner derives capacity from the latest reported quota, mandatory estimate, configured reserve and run cap; it contains no plan constants. |
| Candidate prioritization | VERIFIED OFFLINE | Completed non-eligible fixtures are ordered by fewest attempts then recency. |
| Bounded repairs and backoff | VERIFIED OFFLINE | Migration 017 records attempts, next retry and missing components; exhausted/not-yet-due repairs are excluded. |
| Resumable execution | VERIFIED OFFLINE | Detailed ingestion retains checkpoints and quota-stop behavior. |
| `football backfill` | IMPLEMENTED | Status refresh, plan, enrichment and concise summary are wired. Live bulk backfill was intentionally not run merely to spend quota. |

## Phase 8 — Feature store

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Team-perspective history | VERIFIED OFFLINE | Home/away fixture rows are transformed into prior team histories with goals, shots, corners, possession, passing, discipline and player-rating aggregates. |
| Point-in-time source cutoff | VERIFIED OFFLINE | A history row is usable only when its persisted source observation predates the prediction timestamp; automated tests inspect emitted cutoffs. |
| Configurable windows, season and EW histories | VERIFIED OFFLINE | Windows and half-life are configuration-driven; rolling form, attack/defence, venue, rest and congestion features are emitted. |
| Elo and opponent adjustment | VERIFIED OFFLINE | Pre-match Elo is updated only after its source becomes known; opponent goal-difference adjustment is emitted. |
| Odds features | IMPLEMENTED | Latest eligible fair consensus is restricted to snapshots at/before prediction time; movement-known state is explicit. Production data verification awaits paid current-season odds. |
| Player availability | VERIFIED OFFLINE | Migration 018 adds append-only injury observations and dated collection manifests. Availability is known only after a completed pre-prediction collection; squad denominator remains nullable when unavailable. |
| Expected/confirmed lineup strength | VERIFIED OFFLINE | Values remain null unless lineup observations predate prediction time; strength then uses only player ratings retrieved before cutoff. |
| Immutable Parquet datasets and lineage | VERIFIED OFFLINE | Builder writes content-addressed Parquet and persists schema hash, dataset hash, cutoff range and feature config. `features build` is wired. |
| Leakage auditing | VERIFIED OFFLINE | Tests reject post-match feature names, future observations, overlapping chronological partitions and transformers fitted on validation/future rows. |

## Phase 9 — Statistical models

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Elo | VERIFIED OFFLINE | Chronological fitting, normalized 1X2 probabilities, serialization and training registration are tested. |
| Poisson | VERIFIED OFFLINE | Regularized team attack/defence, home effect, configurable time decay, score matrix, result, totals, BTTS and correct-score markets are tested. |
| Dixon-Coles | VERIFIED OFFLINE | Time-decayed Poisson base plus fitted bounded low-score correction is tested. |
| Training orchestration and registry metadata | VERIFIED OFFLINE | Latest/named content-addressed dataset loading, temporal holdouts, immutable artifact/manifest, versions, library versions, git commit, metrics and candidate registration are integration-tested. |
| `sports-engine train --model ...` | IMPLEMENTED | All six model types run through the real training service; missing prerequisites return exit 2. |

## Phase 10 — ML models

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Multinomial logistic regression | VERIFIED OFFLINE | Median imputation, scaling, class-balanced multinomial probabilities, chronological tuning and serialization pass integration tests. |
| CatBoost | VERIFIED OFFLINE | Conservative CPU/thread-bounded candidates train, predict and register in the shared service. |
| LightGBM | VERIFIED OFFLINE | Conservative CPU/thread-bounded candidates train, predict and register in the shared service. |
| Leakage-safe constrained tuning | VERIFIED OFFLINE | Candidate selection uses validation only; final reported test remains unseen. Random splitting is absent. |

## Phase 11 — Evaluation

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Chronological and walk-forward evaluation | VERIFIED OFFLINE | Timestamp groups cannot cross partitions; expanding and rolling windows are tested; reports are persisted as immutable JSON. |
| Probability and classification metrics | VERIFIED OFFLINE | Log loss, multiclass Brier, RPS, accuracy, balanced accuracy, ECE, calibration curves and confusion matrix are computed. |
| Calibration | VERIFIED OFFLINE | Multiclass Platt and isotonic calibrators fit validation-only probabilities; calibrated and uncalibrated held-test metrics are retained. |
| Bookmaker benchmark | VERIFIED OFFLINE | Prediction-time fair probabilities, mean absolute probability delta and closing snapshot benchmark (where available) remain independent evaluation results. |
| Model promotion | VERIFIED OFFLINE | Candidate/champion/retired/rejected states are implemented; promotion requires log-loss and Brier improvement and bookmaker outperformance when that benchmark exists. |
| Backtesting | VERIFIED OFFLINE | Chronological stored predictions use only contemporaneous odds; a wager requires both probability disagreement and positive expected value; immutable decisions and reports are tested. |
| `sports-engine evaluate`, `models promote/reject`, `backtest` | IMPLEMENTED | Commands invoke real services and return meaningful prerequisite failures. |

## Phase 12 — Production prediction workflow

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Tomorrow point-in-time feature assembly | VERIFIED OFFLINE | Upcoming fixtures use only completed observations available at the prediction timestamp; no targets or future lineups enter inference. |
| Champion loading and calibrated inference | VERIFIED OFFLINE | Versioned model, manifest feature contract and optional calibrator are loaded; random/fallback probabilities are never generated. |
| Market comparison | VERIFIED OFFLINE | Model and fair market probabilities plus explicitly named probability differences are retained; differences are not labeled guaranteed edge. |
| Immutable prediction persistence | VERIFIED OFFLINE | Prediction timestamp, cutoff, odds timestamp, model version and per-fixture probabilities append on repeat runs. |
| `sports-engine predict tomorrow` | IMPLEMENTED | Terminal output includes fixture context, model/market probabilities, differences, quality, model version and odds time. |

## Cross-cutting requirements

- Security: `.env` is ignored and secret audit passed; live key should still be rotated because it appeared in chat.
- Normal tests consume no live quota: VERIFIED.
- README: broad foundation documentation exists; later workflows must be updated as they become real.
- Backups: documented local procedure exists.
- Full prescribed architectural boundaries: VERIFIED; supporting modules were added only with functioning behavior.

## Verification dimensions

- Implementation readiness: all software phases have functioning offline services and tests. Final state is `PRODUCTION_READY_AWAITING_CURRENT_SEASON_PROVIDER_ACCESS`.
- Replay/integration verification: all ten configured competitions were coverage-audited and bootstrapped for labeled 2024 replay: 192 team observations and 3,276 fixtures. Historical `odds=false` is preserved, so all remain production `admitted=false` and replay-only eligible.
- Production verification: current-season ingestion is not verified and remains `BLOCKED_BY_PROVIDER_PLAN`.
- Provider blocker: external only for current-season data. It does not justify weakening production code or relabeling replay data.

## Current validation baseline

- `pytest`: 73 passed, entirely offline.
- `ruff format --check`: passed.
- `ruff check`: passed.
- `mypy`: passed over 132 source files.
- Migrations: 001–019; clean-from-zero, forward migration and idempotency tests pass.
- Package build: wheel and source distribution passed after resolving the declared Hatchling backend.
- Live API: `/status` authenticated and dynamically reported Free, 100/day and 10/minute on 2026-10-07; 2026 access was deliberately verified once and remains plan-blocked. It will not be repeatedly probed.

## Next concrete implementation task

No software implementation task remains before production qualification. Preserve the Free-plan quota and replay separation. After a legitimate provider subscription-state change is observed, run the deliberate current-season access qualification, coverage audit and production bootstrap. Until that external dependency changes, production current-season ingestion remains `BLOCKED_BY_PROVIDER_PLAN`.

