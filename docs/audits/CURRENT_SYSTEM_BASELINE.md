# Current System Baseline — Pre-Upgrade Evidence

Captured 2026-10-12 17:00 Africa/Nairobi from the production DuckDB ledger before this audit changed production logic. This snapshot supersedes the 2026-10-11 baseline. Counts were reproduced with `scripts/warehouse_audit.py` and direct read-only SQL against `data/warehouse/sports.duckdb`.

## Independent pre-change capture — 2026-10-14

Before the 2026-10-14 re-audit changed schema or production governance, the live warehouse was copied and independently verified at schema 33. It contained 1,241 competitions, 1,046 teams, 69,542 fixtures, 23,850 ML-eligible quality assessments, 76 odds snapshots over 38 fixtures, 65 model runs, 161 institutional predictions, and 6,496 opportunities. There was no active champion, but integrity found three older `PRODUCTION_ACTIONABLE` opportunities whose claimed champion status could not be proven at their creation time.

The root cause was historical evidence loss: promotion assessments and current market-role rows were overwritten during reassessment. This made the current projection look correct while preventing a point-in-time proof of earlier decisions. The verified pre-change backup is `artifacts/backups/2026-10-14-pre-append-only-governance/backup_manifest.json`. Migration 034 and the resulting state are deliberately not part of this baseline; they are documented in the improvement register and final report.

## Classification at capture

`RESEARCH + EARLY SHADOW / REAL-MONEY STATUS REQUIRES RE-AUDIT`

The code is fail-closed in several important paths and has a newly selected match-odds champion, but the prospective market ledger spans only 2026-10-11 through 2026-10-12, no shadow opportunity has settled, and three records are already labelled `PRODUCTION_ACTIONABLE`. Those labels require adversarial re-verification before they can support a real-money claim.

## Architecture and workflow

`API-Football -> immutable compressed raw payloads -> validated normalization -> DuckDB ledger -> point-in-time Parquet features -> immutable model/evaluation artifacts -> fixture applicability -> settlement-aware prices -> reference comparison -> governed opportunities -> HTML research report`.

The principal command is `sports-engine run --date ...`. The configured production workflow performs discovery, current fixture/result/injury/odds collection, bounded repair, due model maintenance, analysis, persistence, reporting, and post-run integrity. Replay and production evidence are separated by `competition_seasons.ledger_mode`. DuckDB writes are serialized by orchestration locks.

## Verified warehouse at capture

| Evidence | Value |
|---|---:|
| Competitions / competition seasons | 1,241 / 1,442 |
| Teams | 869 |
| Fixtures / completed | 58,650 / 55,732 |
| Production fixtures / completed / ML eligible | 3,194 / 584 / 584 |
| Replay fixtures / completed / ML eligible | 55,456 / 55,148 / 18,183 |
| Quality-assessed / ML eligible | 18,767 / 18,767 |
| Completed replay fixtures not yet assessed | 36,965 |
| Odds snapshots / prices / covered fixtures | 33 / 108,309 / 22 |
| Bookmakers / provider markets observed | 10 / 182 |
| Feature datasets / model runs | 9 / 53 |
| Institutional predictions / opportunities | 56 / 2,009 |
| Shadow opportunities / settled shadow | 34 / 0 |
| Competition states | 10 actionable, 66 observation, 1,062 discovered, 104 rejected |
| Applicability rows | 56 |
| Duplicate probability/xG clusters | 7 clusters / 38 rows |

## Models and governance at capture

- Registered families: Elo, Poisson, Dixon-Coles, logistic regression, CatBoost, and LightGBM.
- Match-odds roles: one `CHAMPION`, 38 `CHALLENGER`, four `RESEARCH_ONLY`.
- Calibration records: 35 validated and 16 failed, all for `MATCH_ODDS`.
- Competition probability scopes: 253 validated, 30 failed, 11 insufficient-sample.
- Persisted opportunity states: three production-actionable, seven shadow-actionable, 548 research value signals, and 1,451 research-only/no-reference price targets.
- Only match odds has a governed champion. Score-derived BTTS and total-goals prices exist, but no independent BTTS or totals champion/calibration role exists.

## Data completeness at capture

All 18,767 assessed packages are labelled `ML_ELIGIBLE`. Component coverage is uneven: final score/events/cards/lineups are almost complete, team statistics are complete for 16,886 packages, and player statistics for 15,212. The most recent five-season/40-league backfill used 2,659 provider calls and explicitly reported 41,245 historical detail items remaining; 36,965 completed replay fixtures remain unassessed in the current ledger.

## Operator and report evidence

The latest complete live runs were:

- 2026-10-12: six requested and six terminal fixtures, report `analysis-2026-10-12-2026-10-12-99ca616b-95ac-4dfc-927e-60b466395ec7.html`;
- 2026-10-13: 19 requested and 19 terminal fixtures, report `analysis-2026-10-13-2026-10-13-56bfd60b-debe-44c6-83d4-58bae4fa1dfb.html`.

The latest live principal run succeeded and persisted six odds snapshots. The two real HTML reports above are inputs to this audit; their fixture, opportunity, and model-health claims must reconcile to the ledger.

## Initial high-risk hypotheses

1. **P1 evidence sufficiency:** real-money labels exist despite only two days of prospective odds and no settled shadow record. Verify that model promotion and production opportunity gates do not overstate the evidence.
2. **P1 market-family governance:** a score-model match-odds champion is used to price BTTS and totals, while calibration/role lookup is market-family-specific and currently absent for those families. Confirm they cannot become production actionable.
3. **P1 duplicate decisions:** seven repeated probability/xG clusters cover 38 applicability rows. Distinguish legitimate repricing from generic or duplicated predictions and ensure exposure remains fixture-deduplicated.
4. **P1 ledger semantics:** all assessed packages are now ML-eligible even where player/team-stat components are missing. Verify this is the documented tiered eligibility contract and cannot leak missing values or future observations.
5. **P2 historical completeness:** 36,965 completed replay fixtures are unassessed. Quantify whether score-only training uses them safely and whether detailed-feature training silently excludes or imputes them.
6. **P2 market evidence:** 22 fixtures with odds cannot establish a market baseline, closing-price result, or threshold robustness.
7. **P2 operational warning:** current daily runs ignore 155 injury rows for unknown teams. Verify this is visible and fail-safe for affected fixtures.

## Preserved evidence

The production warehouse and immutable artifacts present at capture are authoritative. No historical prediction or model artifact was rewritten to produce this baseline. The machine-readable companion is `docs/audits/CURRENT_SYSTEM_BASELINE.json`.
