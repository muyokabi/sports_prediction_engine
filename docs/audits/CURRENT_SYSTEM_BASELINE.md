# Current System Baseline

Verified 2026-10-11 (Africa/Nairobi) from the current DuckDB warehouse. This file supersedes earlier snapshots whose counts and production claims do not describe this checkout's warehouse.

## Classification

`RESEARCH_ONLY / FAIL_CLOSED`

The software is suitable for offline research and data accumulation. It is not suitable for real-money decisions: there are no odds observations, institutional predictions, opportunities, shadow results, production-actionable models, or model/market champions in the current warehouse.

## Architecture

The supported flow is immutable raw API evidence, validated normalization, DuckDB operational state, point-in-time feature datasets, chronological training/evaluation, governed registry selection, persisted analysis, and standalone HTML. Production targets and replay history are separated by `ledger_mode`. DuckDB is operated as a serialized single-writer store.

## Verified warehouse

| Evidence | Value |
|---|---:|
| Competitions / competition seasons | 10 / 60 |
| Teams / fixtures / completed | 279 / 19,774 / 17,179 |
| Quality assessed / ML eligible / pending repair | 250 / 161 / 89 |
| Production seasons / fixtures / completed / ML eligible | 10 / 3,174 / 584 / 107 |
| Replay seasons / fixtures / completed / ML eligible | 50 / 16,600 / 16,595 / 54 |
| Odds snapshots / prices / bookmakers / markets | 0 / 0 / 0 / 0 |
| Feature datasets / model runs | 2 / 10 |
| Legacy or institutional predictions | 0 |
| Opportunities / shadow observations | 0 / 0 |
| Competition-discovery states / probability scopes / applicability rows | 0 / 0 / 0 |

All 89 pending repairs have one recorded attempt. Of 250 assessed fixtures, team-stat components are incomplete for 76 and player-stat components are incomplete for 17. Missing provider data remains quarantined rather than imputed.

## Models

The registry contains ten immutable candidates: Elo, Poisson, Dixon-Coles, logistic, CatBoost, and LightGBM across two small training rounds. The latest candidates used 107 observations; earlier candidates used 40. Elo is `VALIDATION_ELIGIBLE`; the remaining latest models are `RESEARCH_TRAINABLE`. Every recorded market role is `CHALLENGER`; there is no champion.

Artifact applicability now derives from exact fitted fixture/team/competition lineage. New pickle artifacts carry SHA-256 digests for the model and calibrator. Older hashless artifacts remain readable only as trusted-local legacy artifacts and cannot acquire missing lineage implicitly.

## Current interrupted backfill

`football.fetch_backfill.replay.last-5` stopped at 2026-10-11 09:06:05 +03:00 with `PROVIDER_UNAVAILABLE` after DNS resolution failed. Durable request evidence records 112 logical requests since the run began, 111 billable when `/status` is excluded. The old failure summary incorrectly recorded zero requests; subsequent runs now derive request counts from the durable request log on both success and failure.

The detailed-ingestion checkpoint is preserved at index 3. Bootstrap state is resumable. Completed historical replay seasons are now recognized from their local teams/fixtures and marked complete without downloading them again; current production seasons still refresh normally.

## Artifact layout

New artifacts are partitioned by creation date:

- `artifacts/reports/YYYY/MM/DD/analysis-*.html`
- `artifacts/models/YYYY/MM/DD/<version>/`
- `artifacts/evaluation/YYYY/MM/DD/*.json`

Existing flat artifacts are intentionally not moved. Registry paths remain authoritative, and recursive evaluation discovery preserves compatibility.

## Operational boundary

- Resume the same backfill command after connectivity returns; do not edit checkpoints manually.
- Do not run a second writer while backfill, training, or analysis is active.
- No provider request or connectivity probe was made after the reported outage.
- Collect prospective odds before claiming any market comparison, calibration scope, shadow performance, or execution edge.
- Retrain and re-evaluate after a materially larger ML-eligible replay sample exists.

## Acceptance evidence

Offline analysis `a12eaf9a-95e5-42f4-884d-6fc49904d407` reconciled 6/6 fixtures without provider calls and produced a dated HTML artifact. Backup `artifacts/backups/institutional-audit-2026-10-11` independently verified schema 33, 571 files, and nine critical table counts. The post-run warehouse integrity audit passed.
