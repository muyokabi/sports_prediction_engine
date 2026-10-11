# Implementation Status

Last audited: 2026-10-11 (Africa/Nairobi)

Overall state: `RESEARCH_ONLY_FAIL_CLOSED`

## Implemented and verified

- Typed API-Football collection, immutable raw payloads, dynamic quota evidence, pagination, retry classification, and resumable job/checkpoint infrastructure.
- DuckDB migrations, production/replay ledger separation, transactional normalization, quality assessment, quarantine, repair planning, backups, and integrity checks.
- Point-in-time feature datasets and chronological training for Elo, Poisson, Dixon-Coles, logistic regression, CatBoost, and LightGBM.
- Candidate-specific walk-forward evaluation, validation-era calibration, exact artifact lineage, fail-closed promotion, and governed market decisions.
- Standalone HTML analysis plus date-partitioned HTML/model/evaluation artifacts for all new outputs.
- Model/calibrator SHA-256 verification for new artifacts.
- Offline verification: 190 tests, Ruff, and strict mypy pass.

## Current production evidence

| Dimension | State |
|---|---|
| Production ledger | 3,174 fixtures; 584 completed; 107 ML eligible |
| Replay ledger | 16,600 fixtures; 16,595 completed; 54 ML eligible |
| Odds | None stored |
| Models | Ten candidates; latest trained on 107 observations |
| Champion | None; every role is `CHALLENGER` |
| Predictions/opportunities/shadow | None |
| Probability scopes/applicability evidence | None |

The code paths are implemented, but data and validation evidence do not support production actionability. Earlier documents that claimed an actionable champion or live selections were inconsistent with this warehouse and have been superseded.

## Active operational work

The five-season replay backfill is safely interrupted by DNS failure. Its checkpoint remains intact. When connectivity is restored, rerun:

```powershell
uv run sports-engine football fetch-backfill --past-seasons 5 --max-requests 5000
```

The resume path now skips completed historical season bootstrap calls, preserves current-season refresh behavior, and records durable request counts even on failure. Do not run concurrent writers.

## Promotion boundary

Production actionability requires all of the following, none inferred by default: an exact production-actionable model, an exact candidate evaluation report, fixture applicability from artifact lineage, a validated competition/market scope, valid normalized probabilities, a validated uncertainty adjustment and minimum-return policy, valid contemporaneous reference evidence, and exposure gates. Broker price, liquidity, commission, and slippage remain external evidence.

