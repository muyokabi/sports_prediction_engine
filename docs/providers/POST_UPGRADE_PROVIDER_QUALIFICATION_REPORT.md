# Post-Upgrade Provider Qualification Report

> Historical evidence only. It does not confer current production actionability. See `docs/reports/CURRENT_IMPLEMENTATION_STATUS.md`.

Qualification date: 2026-10-07 (Africa/Nairobi)

Decision: **API-FOOTBALL ACCEPTED AS THE PRODUCTION PROVIDER**

## Subscription and access

| Capability | Observed result |
|---|---|
| Plan | Pro |
| Subscription active | Yes |
| Subscription end | 2026-11-07 20:45:57 UTC |
| Daily limit | 7,500 |
| Per-minute limit | 300 |
| Initial remaining | 7,433 daily / 299 minute |
| Final remaining | 7,415 daily / 282 minute |
| Current-season access | PASS — one deliberate `/teams?league=39&season=2026` request returned 20 teams |

All limits came from `/status` and response headers; no plan-name quota mapping was used.

## Multi-ID enrichment

| IDs requested | Results | Requests consumed | Events | Lineups | Team stats | Player stats |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 2 | 1 | 2/2 | 2/2 | 2/2 | 2/2 |
| 10 | 10 | 1 | 10/10 | 10/10 | 10/10 | 10/10 |
| 20 | 20 | 1 | 20/20 | 20/20 | 20/20 | 20/20 |

No API-level error occurred. Paid access conclusively supports efficient 20-ID enrichment in one request.

## Current-season sample

The semantic sample contained 20 completed 2026 fixtures: four each from Premier League, La Liga, Serie A, Bundesliga and Ligue 1. Discovery found respectively 50, 69, 50, 36 and 45 completed fixtures.

All 20 sampled fixtures contained events, two lineups, two team-stat groups and two player-stat groups.

### Player participation and null frequency

| Field | Starters, n=468 | Appeared substitutes, n=154 | Unused substitutes, n=233 |
|---|---:|---:|---:|
| minutes | 0.0% | 0.0% | 90.1% |
| rating | 0.0% | 4.6% | 90.1% |
| shots.total | 42.7% | 74.0% | 90.1% |
| shots.on | 59.8% | 83.1% | 90.1% |
| passes.total | 0.0% | 1.3% | 90.1% |
| passes.key | 42.5% | 72.1% | 90.1% |
| passes.accuracy | 0.0% | 4.6% | 90.1% |
| tackles.total | 29.3% | 64.9% | 90.1% |
| interceptions | 41.7% | 83.8% | 90.1% |
| duels.total | 4.3% | 9.7% | 90.1% |
| duels.won | 6.2% | 34.4% | 90.1% |
| dribbles attempts | 34.8% | 66.2% | 90.1% |
| dribbles success | 49.4% | 79.9% | 90.1% |
| fouls drawn | 37.0% | 77.3% | 90.1% |
| fouls committed | 37.6% | 67.5% | 90.1% |
| yellow cards | 0.0% | 0.0% | 0.0% |
| red cards | 0.0% | 0.0% | 0.0% |

Three records were conservatively classified `OTHER_UNKNOWN`; they had minutes and ordinary statistics but could not be matched confidently to the lineup role flags.

Role/event-specific null rates were expectedly high: goalkeeper saves 73.1% for starters and 100% for appeared substitutes; penalties saved/won/committed exceeded 92%; goals were null for 73.1% of starters and 95.5% of substitutes; dribbles-past was null for 64.7% and 81.8%. These fields are not valid universal completeness requirements.

## NULL semantics and revised eligibility contract

The paid plan materially changed access and batching, but it did not remove action-contingent nulls. The Free/2024 finding was therefore primarily an over-strict completeness contract rather than proof of tier suppression.

The evidence-backed policy is:

- `REQUIRED_CORE`: player/team identity, both lineups, every starter and substitution entrant represented in player statistics, and non-null minutes for each known participant.
- `OPTIONAL_ANALYTIC`: rating, total passes, pass accuracy, duels and similar metrics. Preserve null; downstream features expose missingness and aggregate only available observations.
- `EVENT_SPECIFIC`: shots, key passes, tackles, interceptions, dribbles, fouls, goals, assists and cards. Null is preserved and is not silently changed to zero.
- `ROLE_SPECIFIC`: goalkeeper saves and penalties saved.
- `NOT_APPLICABLE`: performance statistics for an unused substitute.
- `UNKNOWN_PROVIDER_NULL`: an optional field missing for a participant without enough evidence to call it zero or not applicable.

A fixture remains ML-ineligible when a known participant lacks its player-stat row or required-core minutes. Unused substitutes do not need performance statistics.

## Tomorrow odds qualification

For 2026-10-08, all nine pages were retrieved: 88 fixtures, 10 bookmakers, 13,128 market blocks and 108,011 selections. Every fixture had a provider update timestamp. Updates ranged from 2026-10-07 16:15:14 UTC to 20:18:12 UTC; the newest was approximately 35 minutes old when inspected and therefore inside the configured 180-minute freshness limit.

There were 82,702 selections with a numeric line/handicap-like value. API-Football supplied 405 prices that were not greater than 1.0. They are treated as invalid provider observations and excluded during normalization; 107,606 valid decimal prices remain. Raw responses are retained unchanged.

The qualification calls preserved all odds pages as immutable raw payloads. Canonical append-only snapshots are collected only after production coverage admission and fixture bootstrap provide canonical fixture associations.

## Controlled production activation

Provider acceptance was followed by the ordered production activation requested by the operator:

| Step | Result |
|---|---|
| Coverage admission | 10/10 configured competitions admitted for 2026 |
| Fixture bootstrap | 180 teams and 3,174 fixtures |
| Completed schedule fixtures | 534 |
| Detailed fixtures assessed | 326 |
| ML eligible | 276 |
| Quarantined | 50 |
| Production feature dataset | `production-2026-accumulation`, 276 immutable rows |

The deliberately capped backfill processed 210 fixtures in its final 40-request run: 183 became eligible and 27 were quarantined. Earlier interrupted-but-committed batches bring the durable warehouse totals to 276 eligible and 50 quarantined. The cap now counts both multi-ID batches and targeted repair requests, and the resume checkpoint includes a signature of the exact candidate sequence.

The 2026-10-08 qualification feed contained 88 odds fixtures but none belonged to the admitted production schedule, so it correctly created no orphan canonical snapshots. The next admitted match day, 2026-10-09, required all 19 pages: 183 provider fixtures were inspected, eight matched the official ledger, and 175 unrelated fixtures were rejected from canonical association. Those eight fixtures have 13 append-only snapshots containing 47,889 valid canonical prices; repeated/interrupted observations explain why snapshot count exceeds fixture count. Batched persistence replaced slow row-at-a-time writes without changing the immutable raw or append-only contracts.

Model training was not started merely because data became available. The production dataset has 276 eligible rows and therefore remains below the configured 500-fixture minimum evidence gate. No champion exists, and prediction/betting workflows must continue to abstain until the configured chronological training, validation, evaluation and promotion requirements are met.

The final offline acceptance pass reports 99 tests, 73% combined line/branch coverage, clean Ruff lint/format checks, strict mypy success across 139 source files and a passing warehouse integrity audit. A post-upgrade schema-21 backup was independently opened and verified with 512 files and nine critical table counts.

## Anomalies and conclusion

- Status-body usage and response-header remaining values can differ briefly; scheduling continues to prefer fresh headers conservatively.
- Action and role fields use null extensively even on Pro.
- A small fraction of odds prices are invalid for decimal-odds use and must be excluded, not coerced.
- Multi-ID enrichment has no observed plan restriction on Pro and returns full embedded packages through 20 IDs.
- One live fixture package used provider player ID `0` for multiple placeholder players. The raw response is retained, while non-positive IDs are now rejected from canonical player-stat rows to prevent identity collisions.

The provider passes qualification for production admission with the revised, evidence-backed completeness policy and existing raw preservation, null preservation, odds validation, quota protection and abstention controls.

Machine-readable evidence: `artifacts/reports/post-upgrade-provider-qualification.json`.
