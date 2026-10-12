# Current System Baseline — Pre-Upgrade Evidence

Captured 2026-10-11 (Africa/Nairobi) before the changes in the autonomous audit. This is deliberately a historical baseline, not a statement of the final state. See `docs/reports/AUTONOMOUS_INSTITUTIONAL_CODEBASE_UPGRADE_REPORT.md` for post-upgrade evidence.

## Classification at capture

`RESEARCH_ONLY / FAIL_CLOSED`

The warehouse had substantial match history, but the normal workflow had not populated competition discovery or odds. A Dixon-Coles artifact was registered as champion even though its chronological probability-forensics verdict failed. Research predictions existed, but they had no usable market-reference evidence.

## Architecture

The supported flow was immutable raw API evidence, validated normalization, DuckDB operational state, point-in-time feature datasets, chronological training/evaluation, governed registry selection, persisted analysis, and standalone HTML. Production targets and replay history were separated by `ledger_mode`; DuckDB used a serialized single-writer process.

## Verified warehouse at capture

| Evidence | Value |
|---|---:|
| Distinct competitions / competition seasons | 10 / 60 |
| Teams / fixtures / completed | 279 / 19,774 / 17,179 |
| Quality assessed / ML eligible / pending repair | 8,946 / 8,197 / 749 |
| Production seasons / fixtures / completed / ML eligible | 10 / 3,174 / 584 / 186 |
| Replay seasons / fixtures / completed / ML eligible | 50 / 16,600 / 16,595 / 8,011 |
| Odds snapshots / prices / bookmakers / markets | 0 / 0 / 0 / 0 |
| Feature datasets / model runs | 4 / 22 |
| Institutional predictions / opportunities | 6 / 42 |
| Competition-discovery rows | 0 |
| Validated competition probability scopes | 40 |

“Five seasons” meant five historical seasons for each of ten statically configured leagues: 50 replay competition-seasons. It did not mean five seasons for the provider's full league catalog.

## Material pre-upgrade defects

1. Discovery was only a specialist command. Neither the principal daily path nor `football fetch-backfill` invoked it.
2. Odds collection required an `ACTIONABLE` discovery row, so the empty discovery table produced zero request scopes and silently made no odds calls.
3. The five-season backfill always read the ten-entry YAML seed list.
4. Promotion checked several aggregate metrics but ignored the evaluator's explicit failed `probability_forensics` verdict, allowing an invalid incumbent champion to remain selected.
5. README commands were individually documented but not arranged as a safe, complete fresh-clone sequence.

## Preserved evidence

The verified pre-governance backup is `artifacts/backups/autonomous-upgrade-2026-10-11-pre-governance`. It contains schema 33, 2,865 files, and verified counts for nine critical tables.
