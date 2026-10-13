# Implementation Status

Last audited: 2026-10-13 (Africa/Nairobi)

Overall state: `RESEARCH_AND_SHADOW / NOT_REAL_MONEY_APPROVED`

## Implemented and verified

- Typed API-Football collection, immutable raw payloads, dynamic quota evidence, complete pagination, retry classification, scoped odds, and resumable checkpoints.
- Production/replay ledger separation, transactional normalization, quality evidence, repair planning, verified backups, and warehouse integrity.
- Point-in-time features and chronological training for Elo, Poisson, Dixon-Coles, logistic regression, CatBoost, and LightGBM.
- Exact artifact lineage, fixture applicability, calibration and uncertainty evidence, market-family roles, and fail-closed promotion.
- Complete probability pricing even when no real-money market role is active. Research output and actionability are independent.
- Per-dataset feature-quality sidecars and model manifests that record excluded all-null/constant features.
- Premium standalone HTML research terminal with interactive navigation, responsive visualizations, market filtering/search, audit tables, and reduced-motion support.

## Current evidence

| Dimension | State |
|---|---|
| Competitions | 1,241: 10 actionable; 66 observation; 1,062 discovered; 104 rejected |
| Production ledger | 3,214 fixtures; 584 completed |
| Replay ledger | 55,456 fixtures; 55,148 completed |
| Quality evidence | 18,767 `ML_ELIGIBLE` assessments |
| Odds | 44 snapshots; 25 fixtures; 128,394 prices; 10 bookmakers; 182 provider markets |
| Models | 53 immutable runs; no active market-family champion |
| Predictions | 113 retained institutional predictions |
| Shadow | 34 observations; zero settled |
| Final live acceptance | 19/19 fixtures; 19 references; 19 predictions; 837 prices; zero production labels |

## Promotion boundary

The latest Dixon-Coles core is qualified to issue research probabilities, but no candidate has the configured 200 point-in-time market-baseline rows or settled shadow evidence required for a real-money claim. Missing historical odds, injuries, and lineups are explicit `UNKNOWN`, not synthesized data.

Continue normal prospective runs:

```powershell
uv run sports-engine run --date today
uv run sports-engine run --date tomorrow
```

Do not manually promote a model or weaken the baseline requirement to create bets. Read `AGENTS.md`, `docs/audits/IMPROVEMENT_REGISTER.md`, and `docs/research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md` before altering data or governance behavior.
