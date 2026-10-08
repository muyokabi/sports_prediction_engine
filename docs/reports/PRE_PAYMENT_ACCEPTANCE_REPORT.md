# Pre-Payment Acceptance Report

Audit date: 2026-10-07 (Africa/Nairobi)

Decision: **NOT YET ACCEPTED FOR PRODUCTION READINESS**

Repository state: `PRE_PRODUCTION_HARDENING`

Current-season qualification: `BLOCKED_BY_PROVIDER_PLAN`

The software hardening work is implemented and the offline acceptance suite passes. The repository is not returned to `PRODUCTION_READY_AWAITING_CURRENT_SEASON_PROVIDER_ACCESS`, because real accessible API-Football 2024 payloads have not produced an `ML_ELIGIBLE` fixture under the non-negotiable completeness gate. No null was converted to zero and no eligibility rule was weakened.

## Acceptance evidence

| Area | Result | Evidence |
|---|---:|---|
| Offline tests | PASS | 95 passed; no live quota used by tests. |
| Coverage | PASS WITH DISCLOSED GAPS | 72% line/branch aggregate. Provider client 80%, quota budget 84%, rate limiter 86%, pagination 100%, raw storage 95%, fixture normalization 100%, daily updater 92%, detailed ingestion 90%, completeness 94%, odds ingestion 100%, feature dataset 93%, leakage audit 83%, prediction service 72%, training 92%. CLI presentation modules remain largely uncovered; service layers carry the critical tests. |
| Static analysis | PASS | Ruff and mypy pass. |
| Migrations | PASS | 001–021 are current, contiguous, clean-from-zero and idempotent. |
| Warehouse integrity | PASS | `sports-engine data integrity` returned success after the live soak. |
| Backup/restore verification | PASS | Isolated backup opened at schema 21; 173 files and nine critical table counts were verified, followed by relational/artifact integrity checks. |
| Secret audit | PASS | Zero key matches outside ignored `.env`; zero matching commits in git history. The current key must still be rotated before a paid upgrade because it appeared in chat. |
| Multi-day catch-up | PASS | Automated 2-, 3- and 7-day outage tests prove chronological discovery from the last successful checkpoint through tomorrow. Interrupted catch-up resumes at the first unfinished date. |
| Crash/restart safety | PASS | Tests cover preserved raw evidence, normalization failure, pre-commit rollback, post-commit/pre-checkpoint rerun, interrupted ≤20-ID enrichment, interrupted odds pagination, bounded backfill selection, idempotency and overlapping-job rejection. |
| Odds safety | PASS OFFLINE | Observation time and fixture/market/bookmaker/selection grain are preserved; future observations are excluded; configurable expiry produces `NO_ACTION_STALE_ODDS`. Historical replay odds remain unavailable from the selected Free-access corpus. |
| Abstention/evidence/risk | PASS OFFLINE | Probability and betting decision are separate. Missing/stale markets, weak history/evidence/calibration/confidence/edge/EV and exposure limits produce explicit `NO_BET` reasons. Fractional Kelly is bounded; automated bookmaker execution does not exist. |
| Model reliability gate | PASS BY ABSTENTION | The real warehouse has no champion because no real fixture is eligible. `models reliability` exits non-zero with “No champion model is registered”; prediction cannot silently substitute a model. |

## Real API-Football 2024 soak

The warehouse contains 3,276 replay fixtures across ten configured competitions. Seven real completed fixtures across Premier League, La Liga, Serie A and Jupiler Pro League were fully assessed over four distinct match dates from 2024-07-26 through 2025-05-25. Six of these were added during this audit; one was the earlier baseline fixture.

| Component | Available | Assessed |
|---|---:|---:|
| Fixture metadata and final score | 7 | 7 |
| Events, goalscorers, assists, cards and substitutions | 7 | 7 |
| Both starting XIs and benches | 7 | 7 |
| Home and away team statistics | 6 | 7 |
| Home and away player statistics meeting the mandatory non-null contract | 0 | 7 |

Results:

- Fully complete: 0/7 (0%).
- `ML_ELIGIBLE`: 0/7 (0%).
- Quarantined: 7/7 (100%).
- Fixtures with recorded repair attempts: 6; repair successes: 0 (0%).
- The six newer samples had team-level shots, shots on target, corners, possession, passes, fouls and offsides.
- API-Football returned null player minutes/ratings and action fields such as shots, passes, tackles, interceptions and duels. Nulls affected unused substitutes and, for action-specific fields, participating players. The provider response therefore does not distinguish every unknown from a known zero required by this ledger contract.
- One earlier Jupiler fixture also lacked both team-stat groups.

This is recorded as a provider-data production risk. Additional quota was not spent after the anomaly repeated across leagues and dates.

Reports:

- `artifacts/reports/completeness-soak-5022076f-68f3-48b1-8d2f-3d909ee6d6d7.json`
- `artifacts/reports/completeness-soak-9a3611a3-3ea5-4640-b72d-52cbe30ff813.json`
- `artifacts/reports/coverage.json`

## Real replay end-to-end result

| Stage | Real provider fixtures reaching stage |
|---|---:|
| Immutable raw payloads / normalized fixture ledger | 3,276 fixture skeletons; detailed payloads retained for the assessed sample |
| Formal detailed quality assessment | 7 |
| `ML_ELIGIBLE` | 0 |
| Team-perspective training history | 0 |
| Point-in-time Parquet training dataset | 0 |
| Real-provider model training/evaluation/registration | 0 |
| Real-provider prediction replay | 0 |

`features build --name replay-acceptance` correctly stops with `No ML-eligible replay fixtures are available`. Consequently, synthetic/offline model tests are not represented as a real-provider end-to-end pass.

## Remaining blockers

Before pre-payment readiness can be accepted:

1. Resolve or formally renegotiate the mandatory player-stat completeness contract using authoritative provider semantics; the current implementation must not guess that null means zero.
2. Obtain enough real `ML_ELIGIBLE` replay fixtures to exercise feature creation, chronological training, evaluation, registry and prediction replay end to end.
3. Obtain historical market observations if bookmaker benchmarking is required for the replay corpus; Free coverage currently advertises odds unavailable for the selected competitions.

Validations that genuinely require paid/current-season access and therefore remain deferred:

- successful 2026 access qualification after a detected subscription change or explicit operator request;
- current-season coverage admission, reference bootstrap and fixture ingestion;
- live current-season detailed completeness and repair behavior;
- live current-season odds pagination/freshness and market benchmarking;
- an unattended production daily cycle against the official production ledger;
- production champion inference and decision generation on current-season fixtures.

No further 2026 probe was performed during this audit. The Free account’s freshest observed daily remaining value after the bounded soak was 34, with the configured reserve preserved.
