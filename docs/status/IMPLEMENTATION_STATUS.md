# Implementation Status

Last audited: 2026-10-10 (Africa/Nairobi)

Overall software state: `PRODUCTION_ACTIONABLE_CONDITIONAL_EXECUTION_SUPPORT`

Production current-season qualification: `VERIFIED`

The connected account dynamically reports Pro and passed controlled 2026 qualification. Automated discovery governs a broad current competition universe, but collection admission and provider `ACTIONABLE` state do not confer model/market actionability. Dixon-Coles version `dixon-coles-20261010T104725895417Z-39eeeebc` holds the audited `MATCH_ODDS_CHAMPION` role. Production decisions remain restricted to exact model/market/competition scopes that pass fixture applicability, calibration, walk-forward uncertainty, positive-margin, disagreement, bookmaker-breadth, and portfolio gates. API-Football reference odds are never treated as broker execution prices.

Status is based on exercised behavior, not file presence. The master implementation specification is authoritative.

## Phase 1 — Foundation

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Python 3.12 packaging with `uv`, `pyproject.toml`, lockfile | VERIFIED | `uv sync --all-groups`; wheel and sdist built. |
| Validated YAML/environment configuration | VERIFIED | Configuration exercised by CLI and test suite. Secret is stored only in ignored `.env`. |
| Structured configurable logging | VERIFIED | YAML-configured rotating file/console logging plus persisted structured job-run lifecycle and metrics. |
| CLI skeleton and meaningful exit codes | VERIFIED | Core groups plus tested read-only API quota command. Later-phase commands remain tracked in their phases. |
| Deterministic DuckDB migrations | VERIFIED | Migrations 001–021 apply from zero and rerun idempotently in `test_migrations.py`. |
| DuckDB connection and transactions | VERIFIED | Integration tests exercise clean migration and rollback-capable transaction helper. |
| Job-run infrastructure | VERIFIED | Success/failure lifecycle and metrics persistence covered by `test_job_runs.py`. |
| Provider base interface and typed API-Football client | VERIFIED | Wrapper, API errors, auth/parameter/rate-limit/plan typing, raw-first persistence, pagination and live authentication exercised. `ApiFootballPlanRestrictionError` retains endpoint, parameters, season, provider message, plan when known, and job-run ID. |
| Retry/backoff, safe retry classification, rate limiting | VERIFIED | 503 retry, API errors, terminal 429 typing/status and retry-after behavior covered by provider integration tests. |
| Pagination | VERIFIED | Unit pagination test. |
| Dynamic provider capability and quota discovery | VERIFIED | Typed capabilities model; `/status`; all four quota headers; persisted observations; dynamic limiter and budget. Mocked Free 100/10, Pro 7,500/300, upgrade, downgrade, and stale-status/header disagreement all pass. No plan-to-limit mapping exists. |
| Immutable raw payload and sidecar storage | VERIFIED | Integration test and live doctor payload. |
| `sports-engine api quota` | VERIFIED | Displays persisted plan, active state, daily used/limit/remaining, minute limit/remaining and observation time without consuming a request. |

Migrations: `001_core.sql` through `032_quarantine_legacy_asian_handicap_shadow.sql`.

## Phase 2 — Football reference data

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Candidate league configuration | IMPLEMENTED | Ten configurable candidates in YAML. |
| Mandatory coverage gate | IMPLEMENTED | Pure coverage decision tested. |
| Coverage audit CLI and persistence | VERIFIED PRODUCTION | All ten configured 2026 candidates passed mandatory coverage admission using provider-reported coverage. |
| Competition/season canonical IDs and provider mapping | VERIFIED OFFLINE | Deterministic IDs and repository writes are exercised. |
| Teams and squads/player reference ingestion | VERIFIED OFFLINE | Team/venue mappings and immutable squad snapshots are integration-tested. |
| Production/current vs development/replay separation | VERIFIED PRODUCTION | Explicit app mode, replay season and `ledger_mode`; production never falls back. The 2026 ledger is active and replay remains isolated. |

## Phase 3 — Fixture ledger

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Fixture bootstrap | VERIFIED PRODUCTION | Checkpointed bootstrap loaded 180 teams and 3,174 2026 fixtures across ten admitted competitions. |
| Fixture normalization | VERIFIED OFFLINE | Metadata, status, overall and half/full/extra-time/penalty score states are normalized. Migration 019 makes detailed score corrections append-only observations. |
| Status history and schedule snapshots | VERIFIED OFFLINE | Repository integration tests exercise changed observations and current-view reconstruction. |
| Season discovery and rollover | VERIFIED PRODUCTION | Production-only current-season admission is exercised for 2026 and retains prior seasons; rollover behavior remains integration-tested. |
| Reconciliation | VERIFIED OFFLINE | Quota-safe checkpointed fixture reconciliation is integration-tested. |

## Phase 4 — Detailed match ingestion

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Maximum-20 fixture batching | VERIFIED | `test_batching.py`. |
| Embedded event normalization/persistence | VERIFIED OFFLINE | Deterministic event rows and raw lineage are transactionally persisted. |
| Lineups and bench normalization/persistence | VERIFIED OFFLINE | Starting XI, bench, coach, formation, position and grid are persisted. |
| Team statistics normalization/persistence | VERIFIED OFFLINE | Required nullable fields preserve zero-vs-null semantics and additional fields. |
| Player statistics normalization/persistence | VERIFIED OFFLINE | Required nested statistics are flattened and original additional payload is retained. |
| Transactional complete match package | VERIFIED PRODUCTION | Real 20-ID packages were validated and persisted atomically; interrupted writes roll back safely. |
| Formal completeness and quarantine | VERIFIED PRODUCTION | Provider semantics require rows and minutes for known participants, allow unused substitutes and optional/action/role nulls, and preserve all nulls. Current counts are reported from the final ledger in the autonomous upgrade report rather than frozen here. |

## Phase 5 — Daily updater

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Orchestration lock and job run | VERIFIED LIVE/OFFLINE | The principal workflow uses an exclusive PID lock and persisted lifecycle. A confirmed dead-PID lock is recovered; live/unreadable owners are retained. Orphaned same-name runs are closed as `INTERRUPTED` before restart. |
| Global yesterday/today/tomorrow discovery | VERIFIED OFFLINE | Date-level calls are filtered locally to the selected production/replay ledger; integration test proves unrelated data is ignored. |
| New-completion detection and <=20 enrichment | VERIFIED OFFLINE | Already ML-eligible fixtures are not fetched again; full detail uses batches where supported. |
| Transactional normalization, quality and quarantine | VERIFIED OFFLINE / REPLAY EXERCISED | Atomic package, crash/resume and idempotency tests pass. Seven real 2024 fixtures across four leagues and four dates were assessed; all remained correctly quarantined because mandatory provider fields were `NULL`. |
| Idempotent rerun | VERIFIED OFFLINE | Repeated daily, post-commit/pre-checkpoint, interrupted enrichment-batch and paginated-odds tests do not duplicate canonical rows. |
| Tomorrow schedule and odds handoff | IMPLEMENTED | Tomorrow discovery is persisted; odds runs only when the selected ledger advertises odds coverage. Replay correctly skips odds. |
| Predictions and excess-quota backfill in principal daily job | VERIFIED OFFLINE | Daily uses dynamically available surplus for bounded repair and invokes the champion prediction workflow only when tomorrow fixtures and a champion exist. |
| Multi-day missed-run recovery | VERIFIED OFFLINE | Checkpoint-driven catch-up covers every missed date through tomorrow; 2-, 3- and 7-day outages plus interrupted resume are tested. |

## Phase 6 — Odds

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Odds schema and append-only grain | VERIFIED OFFLINE | Snapshot and price grain exercised; old observations are never overwritten. |
| Odds parsing | VERIFIED OFFLINE | Bookmaker, market, selection, over/under line and handicap line extraction tested. |
| Pagination and snapshot persistence | VERIFIED LIVE/OFFLINE | Service consumes every page for scheduled `ACTIONABLE` league-season scopes, stores known fixtures, reports unknown fixtures and deduplicates unchanged provider observations. The final scoped acceptance stored 33/33 relevant fixtures with zero unknown fixtures. |
| `football odds tomorrow` | IMPLEMENTED | Functional paginated command; it makes no request when selected ledger coverage says odds are unavailable. |
| Implied probability, no-vig and overround | VERIFIED | Unit and repository integration tests. Consensus across bookmakers remains a Phase 12 consumer. |

## Phase 7 — Backfill planner

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Dynamic surplus calculation | VERIFIED OFFLINE | Planner derives capacity from the latest reported quota, mandatory estimate, configured reserve and run cap; it contains no plan constants. |
| Candidate prioritization | VERIFIED OFFLINE | Completed non-eligible fixtures are ordered by fewest attempts then recency. |
| Bounded repairs and backoff | VERIFIED OFFLINE | Migration 017 records attempts, next retry and missing components; exhausted/not-yet-due repairs are excluded. |
| Resumable execution | VERIFIED OFFLINE | Detailed ingestion retains checkpoints and quota-stop behavior. |
| `football backfill` | VERIFIED PRODUCTION | Status refresh, prioritization and enrichment are exercised. The run cap now applies to both batches and targeted repairs; checkpoints are bound to the exact candidate sequence. |
| `football historical-backfill` | VERIFIED LIVE | Season-filtered replay enrichment preserves quota reserve and production isolation. A measured 2024 tranche made 205/238 selected fixtures eligible; combined replay history now contributes 241 of 3,203 training observations. |

## Phase 8 — Feature store

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Team-perspective history | VERIFIED OFFLINE | Home/away fixture rows are transformed into prior team histories with goals, shots, corners, possession, passing, discipline and player-rating aggregates. |
| Point-in-time source cutoff | VERIFIED OFFLINE | Completed results/statistics use reconstructable event time; odds, injuries and lineups retain observation-time cutoffs. Configured replay history can augment production training without becoming a production target. |
| Configurable windows, season and EW histories | VERIFIED OFFLINE | Windows and half-life are configuration-driven; rolling form, attack/defence, venue, rest and congestion features are emitted. |
| Elo and opponent adjustment | VERIFIED OFFLINE | Pre-match Elo is updated only after its source becomes known; opponent goal-difference adjustment is emitted. |
| Odds features | VERIFIED PRODUCTION | Latest eligible fair consensus is restricted to snapshots at/before prediction time; current odds were paginated, normalized and persisted for eight associated fixtures. |
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
| Training orchestration and registry metadata | VERIFIED OFFLINE | Latest/named content-addressed dataset loading, temporal holdouts, immutable artifact/manifest, versions, library versions, git commit, metrics, exact fitted competition-season lineage, and candidate registration are integration-tested. Old artifacts without lineage fail closed for competition applicability. |
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
| Model promotion | VERIFIED LIVE/OFFLINE | Candidate/champion/retired/rejected states are implemented. Promotion requires calibrated holdout quality, bounded walk-forward uncertainty, incumbent non-inferiority, validated uncertainty and minimum-margin policy. A time-correct bookmaker baseline is mandatory when sufficiently available; API-Football baseline absence is recorded explicitly under the configured `when_available` policy rather than misclassified as model failure. |
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
| First-class betting abstention | VERIFIED OFFLINE | Separate immutable decisions emit machine-readable `NO_BET` reasons. Five institutional gates are mandatory keyword-only inputs; missing/invalid odds, insufficient applicability, competition/market status, calibration, uncertainty, margin, EV, or exposure cannot silently pass. Migration 030 also persists fixture-level applicability on the secondary prediction path. |
| Reference-odds semantics and bounded risk | VERIFIED LIVE/OFFLINE | Decisions use valid quotes observed at/before prediction time, retain age as visible information rather than a universal veto, select latest-per-bookmaker references, and enforce settlement-aware minimum acceptable odds plus bounded fractional-Kelly/exposure caps; bookmaker execution remains manual. |

## Cross-cutting requirements

- Security: `.env` is ignored and secret audit passed; live key should still be rotated because it appeared in chat.
- Normal tests consume no live quota: VERIFIED.
- README and runbook: installation, replay/production qualification, scheduling, catch-up, quarantine, integrity, reliability, no-bet interpretation, backup/restore, rollover, plan change and emergency recovery are documented.
- Backups: `data backup` and `data verify-backup` hash and independently open the copied warehouse, compare schema/table counts, verify critical artifacts and run integrity checks. The post-upgrade schema-21 backup verified 512 files and nine critical table counts.
- Full prescribed architectural boundaries: VERIFIED; supporting modules were added only with functioning behavior.

## Verification dimensions

- Implementation readiness: all specified software phases are implemented and offline-tested. Production provider qualification passed; data/model evidence accumulation is the remaining operational gate.
- Replay/integration verification: all ten configured competitions were coverage-audited and bootstrapped for labeled 2024 replay: 192 team observations and 3,276 fixtures. Historical `odds=false` is preserved, so all remain production `admitted=false` and replay-only eligible.
- Production verification: current-season access, batched detailed enrichment, injury collection and complete current-odds pagination are verified against the live provider. Exact final counts are maintained in the autonomous upgrade report.
- Provider access is not the promotion blocker. Missing prospective, point-in-time market/shadow evidence and unvalidated uncertainty/margin policies correctly prevent premature actionability.

## Current validation baseline

- Final verification counts and commands are recorded in `docs/reports/AUTONOMOUS_INSTITUTIONAL_CODEBASE_UPGRADE_REPORT.md` so this status page does not retain a stale test snapshot.
- Governance-focused branch run: 22 passed, 85% combined; decision 85%, applicability 79%, trainer 87%.
- Migrations: 001–033; clean-from-zero, forward migration and idempotency tests pass.
- Final regression baseline: 161 tests passed; Ruff passed; strict mypy passed over 161 source files; warehouse integrity passed.
- Exact rerun audit: two unchanged-input tomorrow runs each persisted 2,827 market outputs with zero value or decision differences and three identical `PRODUCTION_ACTIONABLE` selections.
- Package build: wheel and source distribution passed after resolving the declared Hatchling backend.
- Live API: `/status` dynamically reported Pro, active, 7,500/day and 300/minute; current-season access passed. The latest persisted observation was 222 used / 7,278 remaining daily and 294 remaining per minute at 2026-10-08 00:26:09 +03:00. These are observations, not hardcoded plan mappings.

## Production qualification and accumulation

Status: **PRODUCTION PROVIDER QUALIFIED; DATA AND MODEL EVIDENCE ACCUMULATING**.

Controlled qualification established:

- one deliberate current-season access request succeeded;
- 2-, 10- and 20-ID enrichment each returned every requested fixture in one request with events, lineups, team statistics and player statistics;
- a 20-fixture, five-league semantics audit proved that action- and role-contingent nulls persist on Pro, justifying a participant/minutes core gate rather than an all-fields-non-null rule;
- all nine qualification odds pages and all 19 production-collection odds pages were consumed, with invalid decimal prices excluded only from canonical rows while raw payloads remained immutable;
- ten production competition-seasons were admitted and bootstrapped.

The production warehouse contains 3,174 fixtures across ten competitions. There are 534 completed schedule fixtures; 326 have been assessed, 276 are eligible and 50 are quarantined for genuine core gaps. Eight associated tomorrow fixtures have 13 append-only snapshots and 47,889 canonical valid prices. The immutable `production-2026-accumulation` feature dataset contains 276 rows.

Two live-data anomalies were hardened: non-positive provider player IDs are preserved in raw data but excluded from canonical player statistics, and request caps now cover both batch and targeted-repair calls. Detailed-ingestion checkpoints also include the candidate-sequence signature, preventing an index from being reused against a changed plan. Bulk odds writes were optimized without changing append-only semantics.

Training was deliberately not started: 276 rows do not satisfy the configured 500-fixture minimum, and no production champion exists. Consequently prediction and betting workflows continue to abstain. The authoritative qualification evidence is in `docs/providers/POST_UPGRADE_PROVIDER_QUALIFICATION_REPORT.md`; pre-payment evidence remains historical context in `docs/reports/PRE_PAYMENT_ACCEPTANCE_REPORT.md`.

## Institutional pricing stage

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Dynamic-tail score distribution | VERIFIED_OFFLINE | Grid expands to the configured tail tolerance; normalization and high-intensity expansion are tested. |
| Coherent score-derived core markets | VERIFIED_OFFLINE | 1X2, double chance, DNB, BTTS, totals, team totals and correct score share one distribution. |
| Asian handicap and total settlement | VERIFIED_OFFLINE | Whole, half and quarter lines retain full/half win, push and full/half loss states; fair and target-EV odds are tested. |
| Multiple de-vig methods | VERIFIED_OFFLINE | Proportional, power and Shin-style probabilities normalize; production selection remains evidence-gated. |
| Governed API-Football market taxonomy | IMPLEMENTED | Exact observed provider IDs/names map core score markets; mismatches are disabled and unknowns remain unsupported. Persistence is available in migration 022. |
| Fundamental engine independence | IN_PROGRESS | Existing Poisson/Dixon-Coles models price independently of market data and now use dynamic grids; a separately versioned production institutional fit/evaluation is not yet qualified. |
| ML engine | BLOCKED | Implemented challengers remain below the 500-fixture production evidence gate (276 eligible). |
| Fused price | BLOCKED | No arbitrary blend is produced; chronological weight qualification has not occurred. |
| Date-flexible full-universe run | IMPLEMENTED | `sports-engine run --date today|tomorrow|YYYY-MM-DD --days N` persists an analysis run and terminal manifest for all admitted fixtures in range. It abstains when no model qualifies. |
| Intervening-fixture protection | VERIFIED_OFFLINE | Unresolved intervening fixtures block; final, enriched, quality-passed dependencies resolve. Prediction persistence columns exist in migration 022. |
| Standalone HTML report | VERIFIED_OFFLINE | Executive health summary and escaped full-universe audit render without a server. Fixture-detail/opportunity sections await qualified persisted prices. |
| Institutional prediction ledger | IMPLEMENTED | Migration 022 preserves dependency, freshness, model versions, feature dataset, source odds snapshots, supersession link, independence and settlement probabilities. End-to-end production writes await qualified prices. |
| Live acceptance | IN_PROGRESS | One `/status` request reconfirmed Pro/active and access. Persisted-data runs reconciled today 0/0, tomorrow 8/8, seven-day 90/90, and 2026-10-16 dependency blocking 6/6. Fresh odds collection was not repeated. |

Canonical methodology: `docs/markets/PRICING_METHODOLOGY.md`.

Acceptance status: `docs/reports/INSTITUTIONAL_PRICING_ENGINE_ACCEPTANCE_REPORT.md`.

Current validation baseline after this stage: 112 offline tests passed; Ruff lint and format passed; strict mypy passed over
148 source files; migration 022 passed clean-from-zero/idempotency and is applied to production; warehouse integrity passed.

## Institutional scale and continuous learning stage

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Model-specific evidence states | VERIFIED | Policies independently govern Elo, Poisson, Dixon-Coles, logistic, CatBoost and LightGBM through research, validation, candidate and actionable states. Measurements and reasons are persisted. The universal 500-row blocker is removed. |
| Fundamental production champion | VERIFIED PRODUCTION | Poisson champion `poisson-20261007T231148246967Z-e9c21172` is immutable, serialized and registered. Chronological held-test log-loss is 1.102952, Brier 0.669365, RPS 0.236072 and ECE 0.139636 on 64 test fixtures. Strong partial pooling corrected sparse-team overfit. |
| ML early research | VERIFIED / DATA BLOCKED | Research attempts were made. The production backfill dataset has 11 constant point-in-time features, so logistic was rejected and CatBoost/LightGBM are blocked by the explicit `NO_INFORMATIVE_MODEL_FEATURES` reason, not row count. |
| Versioned continuous learning | VERIFIED OFFLINE | Full-refit and immutable warm-start candidate paths exist for logistic, CatBoost and LightGBM; parent lineage, cutoff and observations are persisted. Configurable new-observation/time/drift/calibration/league/schema triggers produce advisory candidate events. |
| Automated competition discovery | VERIFIED LIVE | One paginated-independent catalog request discovered 1,240 current competitions: 58 observation-qualified, 104 youth/friendly/reserve rejected and 1,078 retained as discovered. Rediscovery preserves admission state. |
| Expanded collection universe | VERIFIED LIVE | Production collection expanded from 10 to 50 competition-seasons. New leagues remain observation-only; collection admission never implies model or wagering actionability. Bootstrap wrote 869 team records and 14,562 fixture records. Warehouse totals are 881 teams and 17,838 fixtures, including 8,870 completed fixtures. |
| Dynamic quota use | VERIFIED LIVE | Development cap increased to 1,000 requests per backfill run; the planner still derives a safe budget from live remaining quota, mandatory work and reserve. After discovery/bootstrap the provider reported 324/7,500 used and 7,176 remaining. |
| Fresh odds in principal run | VERIFIED OFFLINE | `sports-engine run` refreshes status, collects all requested-date odds pages, deduplicates append-only snapshots, associates canonical fixtures and only then analyzes the full universe. `--offline` is explicit. |
| Institutional research terminal | VERIFIED OFFLINE | Standalone dark terminal includes Overview, Top Opportunities, All Matches, Market Board, Model Health, Data Health and Audit tabs; dense fixture panels, filters and honest no-model/no-opportunity states are tested. |
| Settlement/performance/drift loop | IMPLEMENTED | Migration 025 adds immutable prediction outcomes, model/league/market/time performance rollups and advisory drift signals. Daily and principal runs settle finalized prior predictions without mutation and refresh rollups; drift never replaces a champion automatically. |

Migrations 001–025 are applied to production. Warehouse integrity passes. Ruff passes and strict mypy passes over 154 source files. The authoritative execution evidence and remaining limits are in `docs/reports/INSTITUTIONAL_SCALE_CONTINUOUS_LEARNING_ACCEPTANCE_REPORT.md`.

## Shadow opportunity recovery — 2026-10-10

The zero-candidate condition was traced to circular shadow/production gates and a stale score-model lifecycle. Statistical
continuous learning, post-evaluation all-data refit, conservative shadow-only admission, portfolio caps, stale-run recovery,
market-family allowlisting, Asian-handicap orientation correction, and legacy quarantine are implemented. Point-in-time
replay `5b2a3b8d-e328-4f8b-af5c-fca87898fa94` persisted ten capped paper candidates from 165/165 terminal fixtures.
They are not production approved; robust and execution edge remain null. See
`docs/reports/ZERO_CANDIDATE_ROOT_CAUSE_AND_RECOVERY.md`.

## Final institutional pricing acceptance — 2026-10-08

The scaled production dataset now contains 463 eligible fixtures. Dixon-Coles champion
`dixon-coles-20261008T000706120575Z-f397b876` is `PRODUCTION_ACTIONABLE` and supersedes the earlier Poisson champion.
Its held-test metrics are log-loss 1.025738, Brier 0.619874, RPS 0.238570 and ECE 0.128646 over 60 test fixtures.

The principal analysis service now loads only a production-actionable Poisson-family champion, retains the champion's
actual score matrix (including Dixon-Coles correction), and writes append-only institutional predictions with source
cutoff, dependency state, dataset lineage and source odds snapshot IDs. Acceptance run
`28909885-ac38-4789-9437-31bac1223677` reconciled all 63 fixtures for 2026-10-09 as `ANALYZED` and persisted 441
fundamental prices. The report remains deliberately at zero opportunities because available odds are stale or absent.

Final verification: migrations 001–025 and warehouse integrity pass; 130 offline tests pass; combined line/branch
coverage is 74%; Ruff format/lint pass; strict mypy passes over 153 source files. The final report is
`artifacts/reports/analysis-2026-10-09-2026-10-09-28909885-ac38-4789-9437-31bac1223677.html`.

