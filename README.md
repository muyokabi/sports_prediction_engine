# Sports Prediction Engine

An offline-first, command-line football data, analytics, and prediction platform. API-Football v3 supplies source facts; immutable raw payloads and the local DuckDB/Parquet ledger are the durable research asset. The design protects point-in-time history, quota, data lineage, and training eligibility.

## Architecture

Responsibilities are deliberately separated:

- `providers/api_football`: authenticated HTTP, validation, pagination, retries, and quota headers.
- `quota`: priority-aware request admission and protected reserves.
- `warehouse`: migrations, repositories, transactions, raw JSON gzip, and Parquet.
- `sports/football`: domain records, ingestion, normalization, quality, features, and prediction context.
- `models`: statistical and ML algorithms only.
- `training` and `evaluation`: chronological datasets, fitting, calibration, promotion, and audits.
- `jobs`: idempotent workflows; `cli`: terminal presentation only.

The canonical update path is: immutable raw response → validated provider envelope → normalized package in memory → quality assessment → one database transaction. Failed packages remain recoverable from raw storage and are excluded from ML.

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync --all-groups
Copy-Item .env.example .env
```

Set `API_FOOTBALL_KEY` in `.env`. Never commit `.env`.

Initialize and inspect the warehouse:

```powershell
uv run sports-engine data migrate
uv run sports-engine doctor
```

## Operations

```powershell
# Validate configured candidate league-season coverage before admission
uv run sports-engine football coverage audit

# Build current-season reference data and fixture skeletons
uv run sports-engine football bootstrap

# Enrich completed fixtures in API-supported batches of at most 20 IDs
uv run sports-engine football enrich --limit 20

# Progressively enrich completed current-season fixtures within spare quota
uv run sports-engine football backfill

# Normal idempotent operation
uv run sports-engine daily

# Focused workflows
uv run sports-engine football reconcile
uv run sports-engine football seasons
uv run sports-engine football season-rollover
uv run sports-engine football odds tomorrow
uv run sports-engine football quality

# Provider state (status is quota-free; current-season probing is explicit)
uv run sports-engine api capabilities
uv run sports-engine api quota
uv run sports-engine doctor --connectivity
uv run sports-engine doctor --connectivity --verify-current-season

# Modeling
uv run sports-engine features build --name football-training
uv run sports-engine train --model elo
uv run sports-engine train --model poisson
uv run sports-engine train --model dixon-coles
uv run sports-engine train --model logistic
uv run sports-engine train --model catboost
uv run sports-engine train --model lightgbm
# Optional validation-holdout probability calibration
uv run sports-engine train --model logistic --calibration platt
uv run sports-engine evaluate --all
uv run sports-engine evaluate --model logistic --rolling-periods 100
uv run sports-engine backtest --all
uv run sports-engine predict tomorrow
uv run sports-engine models list
uv run sports-engine models leaderboard
uv run sports-engine models promote <candidate-version>
uv run sports-engine models reject <candidate-version>
```

Commands support `--help`; read-only status commands support `--json` where useful. Live commands fail clearly if credentials or prerequisite data are absent. They never manufacture data or probabilities.

## Quota behavior

Provider response headers are the runtime authority. `/status` supplies the account plan, activation state, subscription end (when supplied), and daily usage. No plan name is mapped to a hardcoded quota. Every provider response refreshes the observed daily and per-minute limits; a status/header disagreement is logged and the fresher headers win. A later upgrade, downgrade, or expiration is therefore detected without a code change.

P0 protects accounting/reserves; P1 finalizes matches; P2 discovers tomorrow and captures odds; P3–P6 stop automatically before configured daily or minute reserves. Enrichment uses batches of at most 20 fixture IDs. Backfill budget is:

```text
remaining - protected reserve - estimated mandatory work
```

Unused quota is acceptable.

## Development replay and production ledger

`config/app.yaml` explicitly selects `development` or `production`. Development uses the configured accessible replay season (currently 2024) and labels its competition-season rows `replay`. Production always targets the provider's current season and never silently falls back to historical data. The current Free subscription leaves production qualification at `BLOCKED_BY_PROVIDER_PLAN`; this does not block replay implementation or offline verification.

`doctor --connectivity` refreshes quota-free subscription state without repeatedly probing inaccessible current-season data. A current-season data call occurs only with `--verify-current-season` or after a genuine subscription-plan change is detected. Replay records are never presented as the official live ledger.

## Data-quality policy

Scores alone do not make a match trainable. The completeness ledger independently tracks metadata, scores, events, goals/assists/cards/substitutions, both lineups and benches, both team-stat rows, and both player-stat groups. Unknown upstream values remain `NULL`; known zero remains `0`. Final eligibility is `ML_ELIGIBLE`, `NOT_ML_ELIGIBLE`, or `PENDING_REPAIR`. Incomplete/malformed packages are recorded in `data_quality_issues` and `data/quarantine` with bounded retries.

Every feature row has a prediction timestamp. Only source observations strictly available by that timestamp may contribute. Official evaluation is chronological or walk-forward; random splitting is forbidden.

Training selects a named or latest registered feature dataset, preserves its schema/data hashes, uses chronological train/validation/test periods, and writes an immutable model plus complete JSON manifest. ML tuning is deliberately small and CPU-bounded. Platt or isotonic calibration fits only the validation holdout. Promotion requires better held-out log loss and Brier score than the current champion and, when available, the independent bookmaker benchmark. Walk-forward reports include ECE, calibration curves, confusion matrices and closing-market comparison where historical snapshots exist.

Backtests consume persisted historical predictions and the latest real odds snapshot available at each prediction timestamp. A simulated wager requires both a configured probability difference and positive expected value; profitability never substitutes for probability-quality promotion criteria.

Injury availability is append-only and point-in-time: a zero is trusted only when a dated injury collection completed before the prediction cutoff. Lineup strength is populated only from a lineup observation already known at that cutoff. Feature datasets are immutable, content-addressed Parquet artifacts with persisted schema, data hash, cutoff range, and configuration.

## Daily routine

`sports-engine daily` acquires a local lock, records a job run, checks quota, discovers yesterday globally, filters admitted competitions, enriches new finals in ≤20-ID batches, validates and commits packages, discovers tomorrow, follows all odds pages, writes append-only price snapshots, predicts only when artifacts and data qualify, spends safe surplus on backfill, checkpoints, and prints a concise summary. Re-running does not duplicate canonical rows.

## Season rollover

The season monitor discovers newly exposed provider seasons, retains all earlier seasons unchanged, re-runs mandatory coverage gates, creates an admitted/rejected competition-season, loads teams and the schedule skeleton, then lets ordinary daily collection take over. Older seasons are not fetched automatically.

## Directory layout

```text
config/       validated YAML behavior and model settings
migrations/   deterministic DuckDB schema history
src/          application packages
tests/        offline unit/integration/regression/provider-contract tests
data/raw/     immutable gzipped source payloads plus metadata
data/warehouse/sports.duckdb
data/parquet/ immutable analytical datasets
data/quarantine/ rejected packages and investigation metadata
artifacts/    versioned models, evaluations, backtests, and reports
state/        scheduler, quota, checkpoints, and locks
logs/         rotating operational logs
```

## Backup

Stop running jobs before copying the DuckDB file. Back up `data/raw`, `data/warehouse/sports.duckdb`, `data/parquet`, `artifacts/models`, and `config`. A local PowerShell example:

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$destination = Join-Path 'D:\sports-engine-backups' $stamp
New-Item -ItemType Directory -Path $destination
Copy-Item data\raw, data\parquet, artifacts\models, config -Destination $destination -Recurse
Copy-Item data\warehouse\sports.duckdb -Destination $destination
```

Test restoration periodically into a separate directory and run `sports-engine doctor`. Raw payloads and historical odds/predictions are append-only; do not prune them without an explicit retention and audit decision.

## Development and verification

```powershell
uv run pytest
uv run ruff check .
uv run mypy
```

Normal tests are offline. Live contract checks are marked `live` and skipped unless deliberately selected with credentials available.

