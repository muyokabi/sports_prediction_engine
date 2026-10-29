# Sports Prediction Engine

<div align="center">

**Point-in-time football intelligence, institutional pricing, and auditable market research**

![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![DuckDB](https://img.shields.io/badge/Warehouse-DuckDB-FFF000?logo=duckdb&logoColor=black)
![CLI](https://img.shields.io/badge/Interface-Typer_CLI-0B7285)
![Tests](https://img.shields.io/badge/Tests-Offline_by_default-2E8B57)
![Execution](https://img.shields.io/badge/Execution-Manual_price_confirmation-C05621)
[![Support on Ko-fi](https://img.shields.io/badge/Ko--fi-Buy%20Me%20a%20Coffee-FF5E5B?logo=kofi&logoColor=white)](https://ko-fi.com/muyokabi)

<sub>API-Football facts in. Immutable evidence, calibrated probabilities, fair prices, and conditional execution targets out.</sub>

<br><br>

<a href="https://ko-fi.com/muyokabi">
  <img src="docs/assets/kofi_qr.png" width="130" alt="Ko-fi QR Code (Scan or Click)" title="Scan to buy me a coffee on Ko-fi" />
</a>

<br>

<sub>☕ <b>Buy me a coffee on <a href="https://ko-fi.com/muyokabi">Ko-fi</a></b> (scan or click)</sub>

</div>

> [!IMPORTANT]
> This software does **not** place wagers and does **not** know the price currently available at your broker. API-Football odds are reference observations. Every candidate requires a manual price check: proceed only when the actual broker price is at or above the displayed **minimum acceptable odds**, subject to every non-price risk gate.

## Table of contents

- [What the engine does](#what-the-engine-does)
- [Current operating status](#current-operating-status)
- [The three-price operating model](#the-three-price-operating-model)
- [Architecture and data flow](#architecture-and-data-flow)
- [Quick start](#quick-start)
- [Daily operator workflow](#daily-operator-workflow)
- [Complete command guide](#complete-command-guide)
- [Market-reference semantics](#market-reference-semantics)
- [Models, evaluation, and promotion](#models-evaluation-and-promotion)
- [Data quality and point-in-time safety](#data-quality-and-point-in-time-safety)
- [Quota and provider behavior](#quota-and-provider-behavior)
- [Configuration](#configuration)
- [Reports and artifacts](#reports-and-artifacts)
- [Backup, recovery, and integrity](#backup-recovery-and-integrity)
- [Generated-file retention](#generated-file-retention)
- [Development and verification](#development-and-verification)
- [Troubleshooting](#troubleshooting)
- [Repository layout](#repository-layout)
- [Safety boundary](#safety-boundary)

## What the engine does

Sports Prediction Engine is an offline-first Python platform for collecting football data, maintaining a point-in-time research warehouse, training and governing prediction models, pricing supported markets, and producing auditable HTML analysis.

Its production workflow:

1. discovers and reconciles the complete requested fixture universe;
2. collects every available API-Football odds page and preserves raw evidence;
3. settles completed predictions and refreshes performance feedback;
4. checks fixture dependencies, data quality, model qualification, and football-state validity;
5. produces fundamental probabilities for every qualified fixture;
6. derives fair odds and settlement-aware minimum acceptable odds;
7. compares those prices with the newest valid API-Football reference per bookmaker;
8. ranks conditional opportunities without treating reference age as an automatic veto;
9. writes persisted decisions, price targets, provenance, and an interactive HTML report.

The current fundamental board supports seven selections per analyzed fixture: home/draw/away, over/under 2.5, and both-teams-to-score yes/no. Settlement utilities also support push, half-win, half-loss, and Asian quarter-line economics.

## Current operating status

**`RESEARCH_AND_SHADOW / NOT_REAL_MONEY_APPROVED`** (verified 2026-10-14,
Africa/Nairobi).

The engine currently produces research probabilities and fair prices, but no
market family has an active champion. The previous Dixon-Coles match-odds
champion was demoted because the required timestamp-correct market baseline had
zero rows. It remains available as a qualified research score model, so the
missing production role does not suppress fixture pricing. `RESEARCH_ONLY`,
`RESEARCH_VALUE_SIGNAL`, `PRICE_TARGET`, and `SHADOW_ACTIONABLE` are not betting
approval.

See [Current Implementation Status](docs/reports/CURRENT_IMPLEMENTATION_STATUS.md)
for the latest reconciled warehouse counts and acceptance evidence. Do not copy
those changing counts into operating decisions without rechecking the warehouse.

## The three-price operating model

| Price | Meaning | Known by the engine? | Used for |
|---|---|---:|---|
| **Model fair odds** | Odds implied by the settlement-aware football probability | Yes | Valuation |
| **API-Football reference odds** | Latest valid observation supplied for a bookmaker/market/selection | Yes | Market comparison and movement research |
| **Operator execution odds** | Actual price currently offered by the operator's broker | No, until manually supplied | Final execution decision |

```text
football evidence ──> model probability ──> fair odds
                                 │
                                 ├──> uncertainty + required return
                                 │              └──> minimum acceptable odds
                                 │
API-Football snapshots ──> latest-per-bookmaker references ──> reference edge

actual broker price (manual) ──> compare with minimum odds ──> PASS / DO NOT BET
```

### The execution rule

```text
IF actual broker odds >= minimum acceptable odds:
    price requirement passes, subject to every non-price gate
ELSE:
    DO NOT BET
```

An API-Football observation of `1.96` is never presented as guaranteed execution. If fair odds are `1.72` and minimum acceptable odds are `1.84`, the instruction is: **check brokers and proceed only at 1.84 or better**.

## Architecture and data flow

```text
API-Football
    │
    ├── authenticated requests, pagination, retries, quota headers
    ▼
immutable raw JSON.gz + request metadata
    │
    ├── envelope validation and domain normalization
    ├── quarantine on malformed/incomplete packages
    ▼
DuckDB operational ledger + append-only odds snapshots
    │
    ├── point-in-time features ──> immutable Parquet datasets
    ├── model training/evaluation ──> immutable model registry
    └── fixture analysis ──> prices, references, decisions, HTML
```

| Area | Responsibility |
|---|---|
| `providers/api_football` | HTTP authentication, validation, pagination, retries, provider headers |
| `quota` | Priority-aware admission, observed provider limits, protected reserves |
| `warehouse` | Migrations, repositories, transactions, raw storage, Parquet |
| `sports/football` | Domain records, ingestion, normalization, quality, features, prediction context |
| `models` | Statistical and machine-learning algorithms |
| `training` / `evaluation` | Chronological datasets, calibration, walk-forward evaluation, promotion, backtests |
| `markets` | References, no-vig normalization, settlement, thresholds, decisions |
| `analysis` / `reporting` | Complete-universe pricing, ranking, persistence, HTML |
| `jobs` / `orchestration` | Idempotent workflows, locks, checkpoints, telemetry, recovery |
| `cli` | Operator commands; business logic remains in services |

The canonical write path is `immutable raw response -> validated envelope -> normalized package -> quality assessment -> one database transaction`. Failed packages remain recoverable from raw storage and are excluded from machine learning.

## Quick start

### Requirements

- Python 3.12 or newer.
- [`uv`](https://docs.astral.sh/uv/) for environment and command execution.
- API-Football v3 credentials for live collection. Offline analysis and normal tests need no network.

### Fresh-clone setup

```powershell
git clone https://github.com/muyokabi/sports_prediction_engine.git
Set-Location sports_prediction_engine
uv sync --all-groups
Copy-Item .env.example .env
```

Set `API_FOOTBALL_KEY=replace-with-your-key` in `.env`. Never commit secrets.

```powershell
# Create/upgrade the warehouse and verify local configuration.
uv run sports-engine data migrate
uv run sports-engine doctor
uv run sports-engine data integrity

# With API credentials configured, refresh plan/quota state. The explicit
# current-season probe spends one provider request and is not a daily command.
uv run sports-engine doctor --connectivity
uv run sports-engine doctor --connectivity --verify-current-season
```

At this point the application and warehouse are initialized. A fresh warehouse
still needs historical fixture evidence and at least one qualified score model
before it can price fixtures. The following is the full historical bootstrap,
not part of ordinary daily operation:

```powershell
# Discover the catalog, select up to 40 governed collection leagues, fetch each
# league's latest five completed seasons, and spend at most 5,000 requests on
# detailed enrichment. Coverage and fixture-skeleton calls are outside that cap.
uv run sports-engine football fetch-backfill --past-seasons 5 --max-requests 5000

# Build one current + replay dataset, train/evaluate all six model families,
# and run fail-closed promotion assessment.
uv run sports-engine models train-historical

# Run the normal live workflow and produce tomorrow's research report.
uv run sports-engine run --date tomorrow
```

`fetch-backfill` performs discovery automatically. A fresh clone does **not**
need separate `leagues discover`, coverage, bootstrap, or detailed-backfill
commands before this sequence. The default is a bounded 40-league collection
universe: already admitted leagues first, followed by the strongest observation
candidates. Observation collection does not make a league betting-actionable.

If the historical setup is interrupted, rerun the identical command. Use
`--no-discovery`, `--no-coverage`, or `--no-bootstrap` only for deliberate
checkpoint recovery, not for the first run.

The detailed-enrichment request cap is a real ceiling, not a promise that five
seasons across 40 leagues will fit into 5,000 total provider calls. The command prints
`detail_coverage`, `pending_repair`, and `unassessed`. A successful run means
its bounded tranche completed safely; if either outstanding count is non-zero,
rerun the same command to continue. Fixture skeletons can cover all five
seasons while detailed ML-eligible packages are still incomplete.

### Normal use after setup

```powershell
# Complete live run; discovery, current fixtures, odds, settlement, due model
# maintenance, pricing, and reporting are orchestrated automatically.
uv run sports-engine run --date tomorrow
uv run sports-engine run --date today

# Explicit date and bounded 1–31 day horizon
uv run sports-engine run --date 2026-10-09 --days 3

# Reprice from persisted evidence without provider calls
uv run sports-engine run --date tomorrow --offline
```

The command prints an analysis run ID and report path. Open the HTML under the date-partitioned
`artifacts/reports/YYYY/MM/DD/` tree and confirm every candidate against a real broker.

## Daily operator workflow

```powershell
# These are the normal operator commands. Run either or both as needed.
uv run sports-engine run --date tomorrow
uv run sports-engine run --date today
```

These live commands are autonomous: preflight, catch-up, settlement, ledger repair, a bounded maintenance tranche, due-only model retraining, chronological evaluation, audited champion promotion, fresh requested-date odds, full-universe pricing, and the HTML report all run in sequence. Routine historical repair is capped at 100 API requests per invocation so delivery cannot silently become a full archive rebuild. `run --offline` deliberately skips provider calls, maintenance, training, and promotion and is visibly labelled `OFFLINE REPLAY`.

A live `run` always separates probability production from real-money governance. When a qualified score model exists it prices the requested fixtures even if no market-role champion exists; those outputs remain research prices. Promotion to a market role additionally requires probability integrity, chronological holdout and walk-forward uncertainty, calibration, fixture applicability, competition-specific validation, and incumbent quality. When policy requires significant market outperformance, an unavailable timestamp-correct API-Football baseline fails promotion rather than silently passing. Every assessment is persisted with gate evidence and reason codes.

### Occasional diagnostics — run separately

Do not chain these to the daily prediction command. Run them in a separate terminal session only after the prior command has finished.

```powershell
# Weekly: fast local health checks (no provider quota)
uv run sports-engine doctor
uv run sports-engine data integrity
uv run sports-engine football quality --summary --detailed

# Weekly or when the report shows a repair backlog:
# may consume substantial API quota and take a long time
uv run sports-engine football backfill

# Monthly, or before/after a major data/model change
uv run sports-engine evaluate --all
uv run sports-engine backtest --all
uv run sports-engine models list --json
uv run sports-engine models assess-promotions --json

# Champion-only diagnostic. This currently exits with status 2 because the
# audited system has no champion; use it only after a governed promotion.
uv run sports-engine models reliability --json

# Only when intentionally adding depth from an already registered replay season;
# keep the request cap explicit and run one season at a time
uv run sports-engine football historical-backfill --season 2023 --max-requests 250

# Before upgrades or major maintenance
$backup = 'D:\sports-engine-backups\YYYY-MM-DD'
uv run sports-engine data backup $backup
uv run sports-engine data verify-backup $backup
```

Do not launch two write commands simultaneously. If a command is interrupted, rerun the same command; checkpointing, immutable raw evidence, stale-run recovery, and file locks are designed for restart rather than manual database edits.

## Complete command guide

Every command supports `--help`. Use global `--verbose` / `-v` before the command for detailed logs.

```powershell
uv run sports-engine --help
uv run sports-engine --verbose run --date tomorrow
uv run sports-engine football --help
uv run sports-engine models --help
```

### Principal analysis and diagnostics

| Command | Purpose |
|---|---|
| `sports-engine run --date today` | Live collection and analysis for today |
| `sports-engine run --date tomorrow` | Live collection and analysis for tomorrow |
| `sports-engine run --date YYYY-MM-DD --days N` | Explicit inclusive window, 1–31 days |
| `sports-engine run --date … --offline` | Persisted evidence only; no provider calls |
| `sports-engine daily` | Alias for principal football maintenance; it does not render the institutional HTML report |
| `sports-engine models assess-promotions` | Re-run audited fail-closed ML promotion assessment |
| `sports-engine doctor` | Local configuration, schema, directory, and state checks |
| `sports-engine doctor --connectivity` | Refresh quota-free provider subscription status |
| `sports-engine doctor --connectivity --verify-current-season` | Also spend one request on an exact competition-season access probe |

### Provider and quota

```powershell
uv run sports-engine api quota
uv run sports-engine api quota --json
uv run sports-engine api capabilities
uv run sports-engine api capabilities --json
```

`api quota` reads the last persisted observation and makes no provider request.
`api capabilities` calls API-Football `/status`, updates persisted capability
metadata, and reports production and replay access separately. Use `doctor
--connectivity --verify-current-season` when an actual current-season access
probe is required.

### League discovery and admission inspection

```powershell
uv run sports-engine leagues discover
uv run sports-engine leagues list --limit 100
uv run sports-engine leagues admit-observation --limit 40
uv run sports-engine football coverage audit
uv run sports-engine football coverage audit --json
```

The principal live workflow automatically fills a bounded 40-league observation
collection universe after discovery. That admission permits fixture and odds
collection only: it does not make a competition production/model actionable.
These specialist commands are for inspection or an intentional collection
override, not prerequisites for the normal workflow.

### Football ingestion, repair, and quality

```powershell
# Teams and fixture skeletons for admitted competition-seasons
uv run sports-engine football bootstrap

# Specialist maintenance commands (normally orchestrated by `sports-engine run`)
uv run sports-engine football daily
uv run sports-engine football daily --as-of 2026-10-08

# Completed-fixture enrichment and safe-surplus repair
uv run sports-engine football enrich --limit 20
uv run sports-engine football backfill

# Combined coverage + team/fixture fetch + detailed completed-fixture backfill
uv run sports-engine football fetch-backfill
uv run sports-engine football fetch-backfill --season 2023 --max-requests 250
uv run sports-engine football fetch-backfill --past-seasons 5 --max-requests 5000
uv run sports-engine football fetch-backfill --season 2023 --no-coverage
uv run sports-engine football fetch-backfill --season 2023 --no-bootstrap

# Two-step compatibility workflow for a single replay season. Prefer
# fetch-backfill --season for new work unless registration and enrichment must
# be deliberately separated.
uv run sports-engine football historical-register --season 2023
uv run sports-engine football historical-backfill --season 2023 --max-requests 250

# Mutable results and season lifecycle
uv run sports-engine football reconcile
uv run sports-engine football seasons
uv run sports-engine football season-rollover

# Focused odds collection
uv run sports-engine football odds tomorrow
uv run sports-engine football odds tomorrow --date 2026-10-09

# Quality views and bounded live completeness probe
uv run sports-engine football quality
uv run sports-engine football quality --summary --detailed
uv run sports-engine football quality --json
uv run sports-engine football quality-soak --leagues 3 --fixtures-per-league 2
```

`football fetch-backfill` is the one-command seasonal ingestion workflow. It
first refreshes the provider's current league catalog, then selects up to 40
governed candidates: admitted leagues first and the highest-scoring observation
leagues next. This expands historical evidence without silently promoting an
observation league to production actionability. With no
historical selector, it targets the configured current ledger (production in the
default configuration). Supplying `--season YYYY` or `--past-seasons N` safely
targets the replay ledger so historical data cannot expand the live production
fixture universe. After discovery, the multi-season path reads API-Football's
historical `/leagues` catalog once, selects completed seasons independently for
each selected league, applies
that season's coverage flags, and then fetches teams and fixtures for every
qualified league-season. Its flags are:

| Flag | Default | Meaning |
|---|---:|---|
| `--season YYYY` | current | Fetch and enrich one historical season in the replay ledger |
| `--past-seasons N` | unset | Fetch the latest 1–10 completed seasons for every selected league; cannot be combined with `--season` |
| `--max-requests N` | `1000` | Cap detailed enrichment requests to 1–5000; coverage and skeleton fetching are separate |
| `--league-limit N` | `40` | Bound the discovered collection universe to 1–200 leagues; admitted leagues rank first |
| `--discovery` / `--no-discovery` | `--discovery` | Refresh the current provider catalog; skip only when resuming from persisted discovery |
| `--coverage` / `--no-coverage` | `--coverage` | Run or skip competition coverage qualification |
| `--bootstrap` / `--no-bootstrap` | `--bootstrap` | Run or skip team and fixture-skeleton fetching |

The command is checkpointed and idempotent. Completed scores become immediately
available to Elo, Poisson, Dixon-Coles, and ML training after the season fixture
bootstrap. Event, lineup, team-statistic, and player-statistic payloads are
optional enrichment tiers: missing detail is preserved as missing and never
causes a per-fixture repair request or blocks a valid completed result. Batched
`/fixtures?ids=...` calls collect whatever enrichment API-Football actually
supplies. Rerun after a quota stop or transient network/DNS failure only when
you want to finish that optional enrichment; score-model training does not need
the enrichment pass to be complete.

API-Football identifies a season by its starting year, so the command does not
derive five years by subtracting from the calendar year. It uses each league's
returned season list and excludes the entry marked `current`. Historical fixture,
event, lineup, team-statistic, and player-statistic data can be backfilled when
available. Provider season coverage flags are planning hints, not guarantees
that every fixture contains every component. Historical pre-match odds cannot be
reconstructed: API-Football retains `/odds` observations for only seven days, so
the daily workflow must collect and preserve them prospectively.

The narrower commands have different limits: `football enrich --limit N`
selects 1–200 completed fixtures; `football historical-backfill` requires a
previously registered replay season and accepts a 1–5,000 hard request cap;
standalone `football backfill` uses `backfill.maximum_requests_per_run` from
configuration (currently 1,000). The maintenance embedded in the daily workflow
uses the smaller `maximum_daily_requests_per_run` limit (currently 100).

### Features, training, and calibration

```powershell
uv run sports-engine features build --name football-training
uv run sports-engine features build --name football-training --json
# Explicit research dataset containing discovered observation leagues too
uv run sports-engine features build --name expanded-research --include-observation-leagues

uv run sports-engine train --model elo
uv run sports-engine train --model poisson
uv run sports-engine train --model dixon-coles
uv run sports-engine train --model logistic
uv run sports-engine train --model catboost
uv run sports-engine train --model lightgbm

# Build one current + replay dataset, then full-refit and evaluate all six models
uv run sports-engine models train-historical

# Restrict the historical run to one model or use a rolling evaluation window
uv run sports-engine models train-historical --model lightgbm
uv run sports-engine models train-historical --rolling-periods 100
uv run sports-engine models train-historical --no-assess-promotions
uv run sports-engine models train-historical --include-observation-leagues --no-assess-promotions

# Dataset selection and validation-holdout calibration
uv run sports-engine train --model logistic --dataset football-training
uv run sports-engine train --model logistic --calibration platt
uv run sports-engine train --model logistic --calibration isotonic

# Explicit immutable parent lineage
uv run sports-engine train --model lightgbm --mode warm_start --parent <model-version>
```

`--mode` accepts `full_refit` or `warm_start`. Warm-start training requires the immutable parent version.

`models train-historical` is the dedicated post-backfill training workflow. It
requires ML-eligible completed fixtures in the replay ledger, builds one
point-in-time feature dataset from the current target ledger plus replay history,
and forces immutable full-refit candidates rather than waiting for the daily
retraining schedule. All six model families are trained by default. Each
successful candidate is walk-forward evaluated, ML models receive Platt
calibration, and the normal fail-closed promotion assessment runs after the
suite. The command also writes an exact paired out-of-fold comparison across
successful candidates. Production training includes only `ACTIONABLE` leagues;
discovered `OBSERVATION` leagues remain collected but cannot dilute a production
candidate until they graduate. Use `--include-observation-leagues` only for an
explicit research experiment. A failed model is reported without discarding
successful candidates from the same run.

| Flag | Default | Meaning |
|---|---:|---|
| `--model TYPE` | all models | Train only `elo`, `poisson`, `dixon-coles`, `logistic`, `catboost`, or `lightgbm` |
| `--dataset-name NAME` | timestamped | Set the immutable feature-dataset name |
| `--rolling-periods N` | expanding | Use the latest N periods for each walk-forward training window |
| `--assess-promotions` / `--no-assess-promotions` | `--assess-promotions` | Run or skip audited promotion assessment after evaluation |
| `--include-observation-leagues` | off | Include observation leagues in a research dataset; production training is ACTIONABLE-only |

Training is local and consumes no API quota. It does not repair incomplete
historical fixtures: rerun `football fetch-backfill` first if the command reports
that no ML-eligible replay fixtures are available.

### Evaluation, backtesting, and model governance

```powershell
uv run sports-engine evaluate --model dixon-coles
uv run sports-engine evaluate --all
uv run sports-engine evaluate --model logistic --dataset football-training
uv run sports-engine evaluate --model logistic --rolling-periods 100
uv run sports-engine backtest --all

uv run sports-engine models list
uv run sports-engine models list --json
uv run sports-engine models leaderboard
uv run sports-engine models reliability
uv run sports-engine models reliability --json
uv run sports-engine models promote <candidate-version>
uv run sports-engine models reject <candidate-version>
```

`models promote` is not an override: despite its compatibility-oriented name,
it runs the same automated fail-closed governance assessment and exits without
promotion if any required gate fails. `models reliability` requires an active
champion and currently exits with status 2. Promotion requires held-out
probability-quality evidence; profit alone is never a promotion criterion.

### Prediction compatibility workflow

```powershell
uv run sports-engine predict tomorrow
uv run sports-engine predict tomorrow --date 2026-10-09
```

The institutional `run` report is the preferred full-universe workflow. The prediction command remains available and uses the same rule: reference age is informational, not an automatic veto.

### Warehouse assurance

```powershell
uv run sports-engine data migrate
uv run sports-engine data integrity
uv run sports-engine data cleanup
uv run sports-engine data cleanup --apply
$backup = 'D:\sports-engine-backups\YYYY-MM-DD'
uv run sports-engine data backup $backup
uv run sports-engine data verify-backup $backup
```

## Market-reference semantics

### Reference states

| State | Meaning | Automatic price veto? |
|---|---|---:|
| `CURRENT_REFERENCE` | Latest observation is inside the configured display-age band | No |
| `LATEST_PROVIDER_REFERENCE` | Newest valid source observation | No |
| `AGED_REFERENCE` | Latest observation is older; its age is shown honestly | **No** |
| `HISTORICAL_REFERENCE` | Historical or research-only context | Not a live execution price |
| `NO_REFERENCE_ODDS` | No valid API-Football reference | No fabricated edge; price target only |
| `INVALID_REFERENCE` | Malformed odds, mapping, fixture, or provenance | Yes |
| `POST_KICKOFF_INVALID` | Prematch observation occurred after kickoff | Yes |

Age is a market-quality attribute, not proof of invalidity. The report preserves provider observation time, local collection time, analysis time, kickoff, age, bookmaker, price, snapshot count, movement, consensus, and dispersion.

### Latest-per-bookmaker selection

For each bookmaker/market/selection, the engine selects the newest valid observation known at analysis time. It then calculates the best latest reference, worst latest reference, median consensus, dispersion, and first-to-latest movement. An older high price is movement history—not a substitute for that bookmaker's newer lower price.

### Decision states

| Decision | Operator meaning |
|---|---|
| `RESEARCH_VALUE_SIGNAL` | Positive reference discrepancy, but one or more institutional gates are unvalidated |
| `RESEARCH_ONLY` | Research price with no qualified positive signal |
| `SHADOW_ACTIONABLE` | Structurally credible research candidate, but one or more production gates remain unvalidated |
| `BET_IF_PRICE_AVAILABLE` | `PRODUCTION_ACTIONABLE` selection; execute only if the broker price is at or above the displayed minimum |
| `WATCH` | Legacy compatibility state; current research uses explicit governance states |
| `NO_BET` | Price, evidence, or risk requirements are not met |
| `PRICE_TARGET` | Football price exists but no valid market reference exists |

Reference edge compares the model with API-Football. Execution edge remains unknown until an actual operator price exists.

### Minimum acceptable odds

The threshold solves for the decimal price that meets an evidence-qualified required expected-return margin after a validated uncertainty adjustment. When either policy is absent, the displayed fair price is a research reference only and no `ROBUST_EXPECTED_RETURN` is claimed. Ordinary outcomes use their win/loss distribution. Push and Asian quarter-line markets use the complete settlement distribution, including half wins and half losses; they are never reduced to a binary shortcut.

### Strict invalidation and safety gates

Removing the age veto does not weaken other controls. Decisions remain blocked for impossible odds, malformed/unsupported selections, wrong fixture associations, post-kickoff observations, a started fixture, corrupt provenance, unresolved intervening fixtures, stale football/model state, unqualified models, failed calibration/evidence requirements, unsupported settlement, or risk/exposure limits.

## Models, evaluation, and promotion

- Feature datasets are immutable and content-addressed, with schema/data hashes and cutoff ranges.
- Splits are chronological train/validation/test periods; random splitting is forbidden.
- ML tuning is deliberately small and CPU-bounded.
- Platt or isotonic calibration fits only the validation holdout.
- Walk-forward reports include log loss, Brier score, RPS, ECE, calibration curves, confusion matrices, chronological block-bootstrap intervals, paired market differences where timestamps permit, and closing-market comparison where evidence exists.
- `sports-engine evaluate-ml-score-fusion SCORE_REPORT ML_REPORT` evaluates a research-only ML adjustment of a coherent score matrix. It selects the ML weight before the final fold, preserves one normalized cross-market distribution, writes a hash-bound artifact, and never promotes or changes live serving.
- `sports-engine evaluate-ml-family-specialist ML_REPORT --score-report SCORE_REPORT` retrains the selected ML specification directly for BTTS and over 2.5 on identical chronological folds. Its evidence is strictly family-scoped and the command cannot promote or change serving.
- Promotion requires non-inferiority or improvement over the champion on held-out probability metrics and, where available, the timestamp-correct bookmaker benchmark.
- Backtests use persisted predictions and only odds known at each historical prediction timestamp.

Probabilities, market comparisons, and execution decisions are separate records. No result is reverse-engineered into an earlier prediction.

## Data quality and point-in-time safety

Scores alone do not make a fixture trainable. Completeness independently tracks metadata, scores, events, goal/assist/card/substitution relationships, both lineups and benches, both team-stat rows, both player-stat groups, and player minutes for known starters and entrants.

Unused substitutes need no match-performance row. Unknown upstream values remain `NULL`; known zero remains `0`. Eligibility is `ML_ELIGIBLE`, `NOT_ML_ELIGIBLE`, or `PENDING_REPAIR`. Problems are recorded in `data_quality_issues` and `data/quarantine/` with bounded repair attempts.

Every feature row has a prediction timestamp. Completed-match results and statistics use `RECONSTRUCTED_EVENT_TIME` provenance with a conservative completion effective time; late database retrieval does not erase facts that were historically knowable. Odds, injuries, and lineup snapshots remain `OBSERVED_POINT_IN_TIME` and may contribute only when genuinely captured before the cutoff. A zero-injury value is trusted only from a dated collection completed before the cutoff. An intervening team fixture makes football state genuinely stale and requires recomputation.

Fixture applicability is tied to immutable model lineage. New statistical artifacts record the exact competition-seasons represented by their chronological training rows; the secondary 1X2 prediction path reconstructs Elo/ML membership from the exact chronological training partition and persists its classification. A competition merely existing in the warehouse does not make it in-domain. Missing/older lineage, unseen teams, non-actionable competitions, missing market-family roles, and unvalidated uncertainty or margin policies all fail closed for betting actionability.

## Quota and provider behavior

Provider `/status` and response headers are authoritative. Every response refreshes observed daily and per-minute limits; fresher headers win if status differs. Plan upgrades, downgrades, and expiry are therefore detected without code changes.

| Priority | Work |
|---|---|
| P0 | Accounting, status, protected reserve |
| P1 | Finalize completed matches |
| P2 | Discover tomorrow and capture odds |
| P3–P6 | Optional work that stops before reserves |

```text
backfill budget = remaining - protected reserve - estimated mandatory work
```

Unused quota is acceptable. An unchanged provider timestamp or price is valid evidence and is deduplicated; it is not proof that the observation is wrong.

## Configuration

Primary settings live in [`config/app.yaml`](config/app.yaml); candidates live under [`config/leagues/`](config/leagues/).

Important areas include mode, provider transport, timezone, quota reserves, backfill limits, odds deduplication, the **display-only** aged-reference band, model evidence and CPU bounds, calibration, risk thresholds, minimum expected return, Kelly fraction, exposure caps, and data/artifact/state/log paths.

Development uses an explicitly configured replay season and labels its rows `replay`. Production targets current-season data and never silently falls back to history. Replay records are never silently promoted into the official ledger.

## Reports and artifacts

Principal reports are written to `artifacts/reports/YYYY/MM/DD/analysis-*.html` and include the full-universe audit, football probabilities, fair odds, minimum acceptable odds, latest references, provenance, per-selection age and movement, reference/robust edge, unknown execution edge, decisions, and model/data/quota health. A prominent notice always requires manual price confirmation. Four concise views prevent governance abstention from hiding useful forecasts: `Top Forecasts` shows up to ten in-domain 1X2 views without making a value claim; `Research Basket` shows up to ten one-per-fixture equal-unit learning hypotheses with exact-family global calibration, usable reference breadth, positive expected return and price above the provisional minimum while displaying unresolved competition validation; `Validated Research` additionally requires competition probability scope; and `Top Opportunities` remains limited to shadow/production governance states. The basket ranks model-expected return before decimal-odds payout reach, never invents A/B setup grades, and documents that one odds-4.0 winner cannot cover ten equal stakes. See [`docs/research/EQUAL_STAKE_RESEARCH_BASKET_POLICY.md`](docs/research/EQUAL_STAKE_RESEARCH_BASKET_POLICY.md). None of these views invents executable prices or pads missing qualifiers with prior-only or out-of-domain guesses. New model and evaluation artifacts use the same `YYYY/MM/DD` partition beneath their category; registry paths and recursive discovery retain compatibility with older flat artifacts.

| Path | Contents |
|---|---|
| `artifacts/models/YYYY/MM/DD/` | Immutable version directories, models, calibrators, and hash-bearing manifests; production promotion requires verified model/calibrator digests |
| `artifacts/evaluation/YYYY/MM/DD/` | Walk-forward and calibration evidence |
| `artifacts/backtests/` | Historical decision simulations |
| `artifacts/reports/YYYY/MM/DD/` | HTML analysis and acceptance evidence |
| `data/parquet/` | Immutable analytical datasets |
| `data/raw/` | Gzipped payloads and request metadata |
| `data/quarantine/` | Rejected packages and investigation context |

## Backup, recovery, and integrity

Stop running jobs before a coherent backup:

```powershell
$backup = 'D:\sports-engine-backups\YYYY-MM-DD'
uv run sports-engine data backup $backup
uv run sports-engine data verify-backup $backup
```

Verification hashes every copied file, validates schema and row counts, opens copied DuckDB read-only, and runs relational/artifact checks without touching production. Scheduler setup, lock recovery, alerts, and Windows Task Scheduler commands are in the [operations runbook](docs/operations/RUNBOOK.md).

> [!WARNING]
> Raw payloads, odds snapshots, predictions, decisions, and registered artifacts are audit history. Do not prune or rewrite them without an explicit retention and governance decision.

## Generated-file retention

`sports-engine data cleanup` is dry-run by default. Add `--apply` to remove
allowlisted, regenerable files older than `cleanup.retention_days` (seven days in
the checked-in configuration), or use `--older-than-days 0` for a deliberate
one-off post-test cleanup. The daily workflow invokes the same cleanup at most
once per configured 24-hour interval.

Eligible targets are pytest run directories under `.tmp/` and `state/`, standard
pytest/mypy/Ruff/coverage caches, `src`/`tests` bytecode caches, and explicitly
named test/build scratch directories. The cleanup service has no rule capable of
targeting raw provider evidence, the DuckDB warehouse, Parquet datasets,
quarantine evidence, models, evaluations, backtests, reports, backups,
checkpoints, active locks, or logs. Operational log retention remains the
existing size-based rotation policy in `config/logging.yaml`.

## Development and verification

Normal tests are offline. Live provider-contract checks carry the `live` marker and must be selected deliberately.

```powershell
# Test and coverage
uv run pytest
uv run pytest --cov=sports_engine --cov-branch --cov-report=term --cov-report=json:artifacts/reports/coverage.json
uv run pytest tests/unit/test_reference_odds.py
uv run pytest -k "minimum_acceptable_odds"

# Static quality gates
uv run ruff format --check .
uv run ruff check .
uv run mypy

# Apply formatting intentionally
uv run ruff format .

# Deliberate live tests; consumes quota
uv run pytest -m live
```

Recommended pre-commit sequence:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv run sports-engine data integrity
```

## Troubleshooting

| Symptom | Action |
|---|---|
| `uv` is not recognized | Install `uv`, restart the terminal, then run `uv --version` and `python --version` |
| Credentials are missing | Copy `.env.example` to `.env`, set the key, then use `doctor --connectivity` |
| Principal-run lock exists | Confirm no engine process is active; inspect the lock/job ledger and follow the runbook—never blindly remove an active lock |
| `NO_REFERENCE_ODDS` | Football pricing still exists; use the minimum as a price target, but do not fabricate a reference edge |
| `AGED_REFERENCE` | The observation is older but not automatically invalid; check brokers and enforce minimum odds |
| Zero shadow candidates | Inspect quote freshness, fitted-domain coverage, competition state, history/prior gates, and the family allowlist. Production gates still block real execution. |
| Low provider quota | Preserve the reserve; optional work will stop and resume later |

Offline tests and `run --offline` remain usable without live credentials.

## Repository layout

```text
config/                 validated YAML behavior, leagues, models, risk controls
migrations/             deterministic DuckDB schema history
src/sports_engine/
  analysis/             complete-universe institutional pricing
  cli/                  Typer command surface
  core/                 configuration, paths, logging, telemetry
  evaluation/           walk-forward metrics and backtests
  markets/              references, decisions, settlement, age research
  models/               algorithms and registry behavior
  orchestration/        locks and job lifecycle
  providers/            API-Football transport and validation
  quota/                provider-aware budgeting
  reporting/            interactive HTML generation
  sports/football/      ingestion, quality, features, prediction
  training/             datasets, fitting, calibration, feedback
  warehouse/            database, migrations, backup, integrity
tests/                  offline unit, integration, regression, contract tests
data/raw/               immutable gzipped provider payloads
data/warehouse/         DuckDB operational ledger
data/parquet/           immutable feature datasets
data/quarantine/        rejected packages and repair evidence
artifacts/              models, evaluations, backtests, backups, reports
state/                  checkpoints, locks, scheduler, quota state
logs/                   rotating operational logs
docs/                   runbooks and acceptance reports
```

## Safety boundary

- No automated bookmaker execution.
- No claim that an API-Football reference is currently executable.
- No execution edge until an actual broker price is supplied.
- No arbitrary odds-age haircut or universal time-based invalidation.
- No weakening of fixture, data-quality, model, settlement, or exposure gates.
- No fabricated probabilities, odds, opportunities, or observations.

The intended operating statement is:

> API-Football's latest reference was **X**. The model's fair price is **Y**. The minimum acceptable execution price is **Z**. The observation was recorded **T** ago. Check brokers now and proceed only if the actual executable price is **Z or better**.
