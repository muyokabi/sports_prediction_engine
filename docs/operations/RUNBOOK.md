# Production Runbook

The platform is currently `RESEARCH_AND_SHADOW / NOT_REAL_MONEY_APPROVED`. API-Football current-season access, dynamic quota discovery, 20-ID enrichment, player-stat semantics and current odds are provider-qualified. The historical replay ledger remains separate and must never be labeled as current-season production data.

The engine must continue to produce probabilities and fair prices when a qualified score model exists. A missing market-family champion removes the real-money label; it does not disable research prediction. Never weaken promotion gates to manufacture output.

API-Football is the sole integrated reference provider. Its odds history is short-lived, lineups are often published shortly before kickoff and are not universal, and coverage flags are planning hints rather than per-fixture guarantees. Preserve unavailable odds, injury and lineup fields as `UNKNOWN`. Do not synthesize them or assume a paid plan makes historical point-in-time observations recoverable. Consult `AGENTS.md` and `docs/research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md` before changing data requirements.

## Install and configure

```powershell
git clone <repository-url> sports_prediction_engine
Set-Location sports_prediction_engine
uv sync --all-groups
Copy-Item .env.example .env
```

Set `API_FOOTBALL_KEY` only in `.env`. Select `mode: development` for replay work and `mode: production` for the admitted current-season ledger. The checked-in configuration is now production because provider qualification passed.

```powershell
uv run sports-engine data migrate
uv run sports-engine doctor
uv run sports-engine doctor --connectivity
```

`doctor --connectivity` refreshes `/status` without an additional season probe. Use `--verify-current-season` only for deliberate qualification or after a detected subscription-state change.

## Replay acceptance

Run the quality soak first. Continue into feature/model commands only when the report contains enough `ML_ELIGIBLE` real fixtures; never loosen the gate or reinterpret provider nulls to make the pipeline advance.

```powershell
uv run sports-engine football coverage audit
uv run sports-engine football bootstrap
uv run sports-engine football quality-soak --leagues 3 --fixtures-per-league 2
uv run sports-engine football quality --summary --detailed
uv run sports-engine features build --name replay-acceptance
uv run sports-engine train --model logistic --dataset replay-acceptance --calibration platt
uv run sports-engine evaluate --model logistic --dataset replay-acceptance
uv run sports-engine models list --json
uv run sports-engine models assess-promotions --json
```

`models reliability` is a champion-only diagnostic. The audited system currently
has no champion, so that command correctly exits with status 2; it is not a
replay-acceptance prerequisite.

Historical replay odds may be unavailable even when current-season odds are accessible. This blocks replay market benchmarking, not current production collection or offline pipeline validation. Accumulate detailed historical packages in bounded tranches with `sports-engine football historical-backfill --season 2024 --max-requests 250`; configured replay history augments chronological training without changing the production prediction universe.

## Daily unattended operation and missed runs

Run `scripts\run_daily.ps1` from Windows Task Scheduler. Configure the action as:

```text
Program: powershell.exe
Arguments: -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\path\to\sports_prediction_engine\scripts\run_daily.ps1"
Start in: C:\path\to\sports_prediction_engine
```

Schedule once daily after the provider's usual finalization window. Enable “Do not start a new instance.” The application lock independently rejects a live overlapping process. A lock owned by a PID that is provably no longer running is removed on acquisition; an unreadable lock or a live owner is never removed automatically. The script establishes its working directory, loads `.env` through application configuration, writes rotating logs, and returns the CLI exit code.

The daily workflow reads `daily_discovery:<ledger>` and catches up every unprocessed date through tomorrow. It checkpoints each date only after enrichment succeeds, so a 2-, 3-, or 7-day outage resumes chronologically. Quota exhaustion leaves the checkpoint at the last completed date for the next run.

## Monitoring and quarantine

```powershell
uv run sports-engine football quality --summary
uv run sports-engine football quality --detailed
uv run sports-engine data integrity
uv run sports-engine models list --json
uv run sports-engine models assess-promotions --json
uv run sports-engine api quota
```

Treat non-zero exits, `failed` job runs, or error categories in `job_runs` as alerts. On restart, an orphaned `running` row for the same job name is deterministically closed as `failed` with category `INTERRUPTED` before the replacement run is created. Do not manually mark quarantined fixtures eligible. Repair upstream data and rerun bounded enrichment/backfill.

Alert categories are `PROVIDER_UNAVAILABLE`, `AUTHENTICATION_FAILURE`, `QUOTA_EXHAUSTION`, `PLAN_RESTRICTION`, `DATABASE_INTEGRITY_FAILURE`, `FIXTURE_INGESTION_FAILURE`, `ODDS_INGESTION_FAILURE`, `NO_ELIGIBLE_MODEL`, `PREDICTION_FAILURE`, `BACKUP_FAILURE`, `INTERRUPTED`, and `UNCLASSIFIED_FAILURE`. Mandatory job failures are persisted, logged at error level and returned with a non-zero process status.

Predictions are probability records. `prediction_decisions` separately records the governance state, machine-readable reasons, exact reference observation, expected value, minimum acceptable odds, bounded stake fraction, and fixture-level applicability derived from the exact training domain. Missing training lineage is `OUT_OF_DOMAIN`, never implicitly applicable. Reference age remains visible but is not an arbitrary veto. Missing/invalid/post-kickoff evidence, weak applicability, absent calibration, unvalidated uncertainty or margin, non-positive expected value, or exposure breach produces `NO_BET`. Bet placement is manual; no bookmaker execution exists.

Generated artifacts are partitioned by creation date. Daily HTML is under
`artifacts/reports/YYYY/MM/DD/`; model versions are under
`artifacts/models/YYYY/MM/DD/<version>/`; walk-forward evidence is under
`artifacts/evaluation/YYYY/MM/DD/`. The model registry stores the exact path, and evaluation
discovery is recursive, so historical flat-layout artifacts remain valid and must not be moved by
hand. New model and calibrator manifests include SHA-256 digests that are verified before loading.
Automated production promotion requires both hashes and fails closed with
`ARTIFACT_INTEGRITY_NOT_VERIFIED`; legacy hashless artifacts remain research-only compatibility.
Digest verification detects replacement but does not make pickle safe for untrusted provenance,
so pickle files must never be accepted from an untrusted source.

Promotion assessments and `model_market_role_events` are append-only governance evidence. Never
update or delete an older assessment/event to make the current projection look consistent. A
production opportunity must be validated against the latest role event and supporting evidence
that existed at or before its creation time. Before any production-ledger migration, create and
verify a backup; a faithful backup may correctly preserve known integrity findings from the source.

The HTML `Top Research` table uses an independent research-shortlist policy: HIGH/MEDIUM
applicability, validated calibration and competition probability scope, adequate bookmaker breadth,
no extreme model–market disagreement, positive calculable reference EV, and a persisted API-Football quote
at or above provisional minimum odds. It does not require a production champion or historical market
baseline merely to display a research shortlist. It keeps one selection per fixture, capped at ten,
and is not padded with prior-only or out-of-domain rows. Ranking is lexicographic: applicability tier,
number of remaining evidence warnings, normalized price cushion above minimum acceptable odds,
API-reference expected return, then model selection probability. It displays fair/minimum/reference
odds, quote time and age, valid observation count, bookmaker-breadth gate outcome, movement,
dispersion, EV, minimum-odds policy basis, validated uncertainty adjustment,
applicability, governance and every gate reason. Model probability is not a confidence interval;
API-reference EV is not guaranteed executable EV. Recheck the bookmaker price before any use.
The quality funnel reports how many price rows passed every shortlist gate and the leading row-level
blockers. It is an evidence-accumulation diagnostic, not permission to weaken a gate to fill ten rows.

## Generated-file cleanup

The daily workflow runs generated-file cleanup at most once every 24 hours and
removes only allowlisted, regenerable development/test debris older than seven
days. Inspect or run it explicitly with:

```powershell
uv run sports-engine data cleanup
uv run sports-engine data cleanup --apply
uv run sports-engine data cleanup --apply --older-than-days 0
```

The first command is a dry run. The zero-day override is intended for deliberate
one-off cleanup after tests, not routine scheduling. Configuration lives under
`cleanup` in `config/app.yaml`; completion state is recorded in
`state/generated-cleanup.json`.

The allowlist is limited to pytest run directories in `.tmp/` and `state/`,
standard Python test/type/lint caches, coverage output, `__pycache__` under
`src/` and `tests/`, and explicitly named `artifacts/test-tmp` or
`artifacts/build-final` directories. Cleanup never targets `data/raw`, the
warehouse, Parquet datasets, quarantine evidence, models, evaluations,
backtests, reports, backups, checkpoints, active locks, or operational logs.
`logs/sports-engine.log` already uses size-based rotation (10 MiB, five backups).

`SHADOW_ACTIONABLE` means eligible for prospective paper tracking only. The default bootstrap policy accepts fresh
`MATCH_ODDS`, `BTTS`, and `TOTAL_GOALS` references from structurally fitted, actionable competitions, then caps output at
one row per fixture and ten per run. It does not imply a validated robust edge. Confirm that `robust_estimated_edge` and
`execution_edge` remain null and that `SHADOW_ONLY_NOT_PRODUCTION_APPROVED` is present until production promotion is
complete. Asian handicap is excluded pending dedicated line-semantics validation; migration 032 quarantines old rows.

Odds ingestion consumes every page for the scheduled `ACTIONABLE` league-season scopes only and checkpoints committed pages. It must not scan the provider's global date surface. Retried content is deduplicated using both its normalized content hash and the provider update time, so an unchanged provider observation does not multiply price rows merely because local collection time advanced.

## Historical training accumulation

Finish the already registered replay season before adding older season skeletons:

```powershell
uv run sports-engine football historical-backfill --season 2024 --max-requests 250
```

Review eligible yield, quarantines, and remaining daily quota after every tranche. Do not mark provider-null packages eligible or add an older season merely to inflate the row count.

## Backup and restore verification

```powershell
$backup = 'D:\sports-engine-backups\YYYY-MM-DD'
uv run sports-engine data backup $backup
uv run sports-engine data verify-backup $backup
```

Verification opens the copied DuckDB in isolation, checks the current schema and table row counts, and hashes every copied raw/config/Parquet/model file. Never restore over the live database. To recover, stop scheduled jobs, verify the backup, copy it to a new project directory, update configuration paths if necessary, then run `doctor` and `data integrity` there before switching schedules.

## Provider state and season rollover

The paid subscription passed qualification on 2026-10-07. For a future plan, credential, or season change:

1. In the API-Football dashboard, revoke/regenerate the current key.
2. Replace only `API_FOOTBALL_KEY` in `.env`; no source change is required.
3. Run `doctor --connectivity` and confirm the dynamically reported plan/quota state.
4. Run `doctor --connectivity --verify-current-season` once when qualification is warranted.
   Confirm that its detail names an exact probe pair (for example, `production league=39 season=2026`) and that the season belongs to that league. A catalog-wide maximum season can belong to a future tournament and must never be reused for another league.
5. Keep production collection stopped if access fails; otherwise run coverage audit, bootstrap, quality and integrity checks.
6. Run `football season-rollover` when a newly current season appears. Prior seasons remain intact.

## Emergency stop and recovery

Disable the Task Scheduler task. If a job is running, allow its current transaction to finish where possible. Preserve `data/raw`, the database, quarantine files and logs. Run `doctor`, `data integrity`, and `football quality --summary`. Correct the cause; do not delete checkpoints. Re-enable the schedule and run `scripts\run_daily.ps1` once manually—the catch-up workflow resumes from the last successful date. Never delete a lock merely because it exists: first confirm the recorded PID is absent. Normal startup performs this check and recovers only a confirmed dead-PID lock.
