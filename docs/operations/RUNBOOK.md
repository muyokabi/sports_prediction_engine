# Production Runbook

The platform is currently `PRODUCTION_PROVIDER_QUALIFIED_DATA_ACCUMULATING`. API-Football current-season access, dynamic quota discovery, 20-ID enrichment, player-stat semantics and current odds were deliberately qualified before production bootstrap. The historical 2024 replay ledger remains separate and must never be labeled as current-season production data.

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
uv run sports-engine models reliability
```

Historical replay odds may be unavailable even when current-season odds are accessible. This blocks replay market benchmarking, not current production collection or offline pipeline validation.

## Daily unattended operation and missed runs

Run `scripts\run_daily.ps1` from Windows Task Scheduler. Configure the action as:

```text
Program: powershell.exe
Arguments: -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\path\to\sports_prediction_engine\scripts\run_daily.ps1"
Start in: C:\path\to\sports_prediction_engine
```

Schedule once daily after the provider's usual finalization window. Enable “Do not start a new instance.” The application lock independently rejects overlap. The script establishes its working directory, loads `.env` through application configuration, writes rotating logs, and returns the CLI exit code.

The daily workflow reads `daily_discovery:<ledger>` and catches up every unprocessed date through tomorrow. It checkpoints each date only after enrichment succeeds, so a 2-, 3-, or 7-day outage resumes chronologically. Quota exhaustion leaves the checkpoint at the last completed date for the next run.

## Monitoring and quarantine

```powershell
uv run sports-engine football quality --summary
uv run sports-engine football quality --detailed
uv run sports-engine data integrity
uv run sports-engine models reliability
uv run sports-engine api quota
```

Treat non-zero exits, `failed` job runs, or error categories in `job_runs` as alerts. Do not manually mark quarantined fixtures eligible. Repair upstream data and rerun bounded enrichment/backfill.

Alert categories are `PROVIDER_UNAVAILABLE`, `AUTHENTICATION_FAILURE`, `QUOTA_EXHAUSTION`, `PLAN_RESTRICTION`, `DATABASE_INTEGRITY_FAILURE`, `FIXTURE_INGESTION_FAILURE`, `ODDS_INGESTION_FAILURE`, `NO_ELIGIBLE_MODEL`, `PREDICTION_FAILURE`, `BACKUP_FAILURE`, and `UNCLASSIFIED_FAILURE`. Mandatory job failures are persisted, logged at error level and returned with a non-zero process status.

Predictions are probability records. `prediction_decisions` separately records `BET` or `NO_BET`, machine-readable reasons, the exact observed price, expected value, minimum acceptable odds and bounded stake fraction. Any stale/missing price, weak evidence, absent calibration, low history, weak advantage, non-positive expected value, or exposure breach produces `NO_BET`. Bet placement is manual; no bookmaker execution exists.

## Backup and restore verification

```powershell
uv run sports-engine data backup D:\sports-engine-backups\2026-10-07
uv run sports-engine data verify-backup D:\sports-engine-backups\2026-10-07
```

Verification opens the copied DuckDB in isolation, checks the current schema and table row counts, and hashes every copied raw/config/Parquet/model file. Never restore over the live database. To recover, stop scheduled jobs, verify the backup, copy it to a new project directory, update configuration paths if necessary, then run `doctor` and `data integrity` there before switching schedules.

## Provider state and season rollover

The paid subscription passed qualification on 2026-10-07. For a future plan, credential, or season change:

1. In the API-Football dashboard, revoke/regenerate the current key.
2. Replace only `API_FOOTBALL_KEY` in `.env`; no source change is required.
3. Run `doctor --connectivity` and confirm the dynamically reported plan/quota state.
4. Run `doctor --connectivity --verify-current-season` once when qualification is warranted.
5. Keep production collection stopped if access fails; otherwise run coverage audit, bootstrap, quality and integrity checks.
6. Run `football season-rollover` when a newly current season appears. Prior seasons remain intact.

## Emergency stop and recovery

Disable the Task Scheduler task. If a job is running, allow its current transaction to finish where possible. Preserve `data/raw`, the database, quarantine files and logs. Run `doctor`, `data integrity`, and `football quality --summary`. Correct the cause; do not delete checkpoints. Re-enable the schedule and run `scripts\run_daily.ps1` once manually—the catch-up workflow resumes from the last successful date.
