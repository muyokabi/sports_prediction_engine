# Current Implementation Status

Verified 2026-10-14 (Africa/Nairobi).

## Status

`RESEARCH_AND_SHADOW / NOT_REAL_MONEY_APPROVED`

The engine continues to produce fixture probabilities and fair prices without an active market-family champion. Production actionability is a separate fail-closed label: the current warehouse has zero `PRODUCTION_ACTIONABLE` opportunities and zero active champions.

The live ledger is at schema 34 and contains 1,241 competitions, 1,046 teams, 69,542 fixtures, 60,773 completed fixtures (`FT`, `AET`, or `PEN`), 23,850 ML-eligible quality assessments, 76 prospective odds snapshots over 38 fixtures, 11 feature datasets, 65 model runs, 185 institutional predictions, and 7,534 opportunities. Opportunity governance is 5,181 `RESEARCH_ONLY`, 2,346 `RESEARCH_VALUE_SIGNAL`, seven `SHADOW_ACTIONABLE`, and zero production-actionable. No claim of real-money readiness is justified by these counts.

## Latest acceptance

Offline analysis `8116e66f-d46c-47b0-ad9a-8abb1103de88` completed all 12 requested fixtures for 2026-10-14, retained reference odds for 11 fixtures, wrote 24 predictions and 1,038 research prices/opportunities, and emitted zero production or shadow candidates. The report is:

`artifacts/reports/2026/10/14/analysis-2026-10-14-2026-10-14-8116e66f-d46c-47b0-ad9a-8abb1103de88.html`

The HTML now includes a populated `Top Research` section with exactly ten selections. It ranks one selection per fixture by applicability quality and then by `model probability - uncertainty buffer`. This is a compact probability-confidence view, not an expected-value or betting recommendation. `PRIOR_ONLY` and out-of-domain rows may appear only after stronger applicability tiers and are visibly labelled.

## Governance and evidence

Migration 034 makes promotion assessments and market-role changes append-only. Integrity validates a production label against the role, calibration, competition scope, and other evidence that existed at the opportunity's creation time. Three legacy production labels lacking provable historical role events were quarantined as `RESEARCH_VALUE_SIGNAL / NO_BET`; their immutable predictions and fair prices were not changed.

The prior Dixon-Coles model remains usable as a qualified research score model. It is not a champion because the policy-required historical point-in-time market baseline is absent. API-Football's short odds retention means that evidence must accumulate prospectively and cannot be reconstructed. Missing odds, injuries, lineups, and movement remain explicit unknowns.

The schema-33 warehouse was backed up and verified before migration at:

`artifacts/backups/2026-10-14-pre-append-only-governance/backup_manifest.json`

## Verification

| Check | Result |
|---|---|
| Full test suite | 230 passed |
| Focused final regressions | 50 passed |
| Ruff | Passed |
| Strict mypy | Passed for 163 source files |
| Migrations | Schema 34/current |
| Warehouse integrity | Passed after migration and final acceptance |
| Pre-change backup | Verified schema 33; 14,648 files; nine critical tables |
| Offline principal acceptance | 12/12 terminal; 11 fixtures with references; zero production/shadow labels |
| Report acceptance | 1,079,935 bytes; exactly ten Top Research rows; warnings present |

## Remaining limitations

- Only 38 fixtures have prospective reference odds, and no sufficient settled-shadow history demonstrates durable edge.
- There is no active market-family champion.
- Historical pre-match odds, injuries, expected/confirmed lineups, and movement cannot be invented where they were not captured.
- Injury/lineup features have no useful historical training coverage; provider-dependent all-null or constant columns remain explicit but are excluded from fitted information.
- Competition admission, applicability, family qualification, calibration, uncertainty, and risk gates remain independent.
- DuckDB remains a coordinated single-writer local store, not a multi-process service database.

The correct next step is continued prospective collection and settlement, followed by predeclared chronological evaluation—not weaker gates or reinterpretation of research rankings as bets.

## Durable evidence

- Documentation map: `docs/README.md`
- Future-agent guardrails: `AGENTS.md`
- Pre-change baseline: `docs/audits/CURRENT_SYSTEM_BASELINE.md`
- Findings register: `docs/audits/IMPROVEMENT_REGISTER.md`
- Research record: `docs/research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md`
- Full audit report: `docs/reports/AUTONOMOUS_INSTITUTIONAL_CODEBASE_UPGRADE_REPORT.md`
- Satisfaction boundary: `docs/reports/CODEBASE_SATISFACTION_STATEMENT.md`
