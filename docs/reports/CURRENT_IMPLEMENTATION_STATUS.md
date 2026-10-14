# Current Implementation Status

Verified 2026-10-14 (Africa/Nairobi).

## Status

`RESEARCH_AND_SHADOW / NOT_REAL_MONEY_APPROVED`

The engine continues to produce fixture probabilities and fair prices without an active market-family champion. Production actionability is a separate fail-closed label: the current warehouse has zero `PRODUCTION_ACTIONABLE` opportunities and zero active champions.

The live ledger is at schema 34 and contains 1,241 competitions, 1,443 competition-seasons, 1,046 teams, 69,542 fixtures, 60,815 completed fixtures (`FT`, `AET`, or `PEN`), 23,850 ML-eligible fixture-quality assessments, 106 prospective odds snapshots over 55 fixtures, 13 feature datasets, 71 model runs, 207 institutional predictions, and 8,520 opportunities. Opportunity governance is 5,894 `RESEARCH_ONLY`, 2,619 `RESEARCH_VALUE_SIGNAL`, seven historical `SHADOW_ACTIONABLE`, and zero production-actionable. All seven shadow records have now settled as paper-tracking evidence; that sample is not sufficient to demonstrate calibration, durable edge, or bankroll safety. No claim of real-money readiness is justified by these counts.

## Latest acceptance

Final offline analysis `ec603dc8-13c4-4431-aec7-eb3a4e51b017` completed all 12 requested fixtures for 2026-10-14, retained reference odds for ten fixtures, wrote ten predictions and 467 research prices/opportunities, including 135 research value signals, and emitted zero production or shadow candidates. The report is:

`artifacts/reports/2026/10/14/analysis-2026-10-14-2026-10-14-ec603dc8-13c4-4431-aec7-eb3a4e51b017.html`

The HTML now includes an independently evidence-qualified `Top Research` section with at most ten selections and one selection per fixture. Admission requires HIGH/MEDIUM applicability, valid model/reference prices, validated calibration and competition probability scope, adequate bookmaker breadth, no extreme model–market disagreement, positive calculable reference EV, and an API-Football quote at or above provisional minimum odds. A production champion or historical market baseline is not required merely to appear in this research shortlist. Ranking is lexicographic: applicability quality, fewer remaining evidence warnings, normalized price cushion above minimum odds, reference expected return, then model probability. Full pricing, provenance, EV, minimum-odds basis, the bookmaker-breadth gate, validated uncertainty state, applicability, governance, and gate reasons remain visible. A quality funnel reports the leading blockers when fewer than ten rows qualify, and the table is never padded with prior-only/out-of-domain guesses.

The earlier live analysis `e75f38b4-ecaa-4be9-9590-76a3e557d371` completed 12/12 fixtures and wrote 519 price rows. Eleven fixtures were `MEDIUM / PARTIALLY_POOLED`; one fixture was `PRIOR_ONLY`. Its report contained one genuinely evidence-qualified Top Research row for Millonarios v Once Caldas and correctly excluded the other rows, principally for missing competition probability validation or calibration. This proves the section can populate from persisted evidence without manufacturing a fixed daily quota. It does not prove predictive edge or real-money readiness.

## Governance and evidence

Migration 034 makes promotion assessments and market-role changes append-only. Integrity validates a production label against the role, calibration, competition scope, and other evidence that existed at the opportunity's creation time. Three legacy production labels lacking provable historical role events were quarantined as `RESEARCH_VALUE_SIGNAL / NO_BET`; their immutable predictions and fair prices were not changed.

The prior Dixon-Coles model remains usable as a qualified research score model. It is not a champion because the policy-required historical point-in-time market baseline is absent. API-Football's short odds retention means that evidence must accumulate prospectively and cannot be reconstructed. Missing odds, injuries, lineups, and movement remain explicit unknowns.

The schema-33 warehouse was backed up and verified before migration at:

`artifacts/backups/2026-10-14-pre-append-only-governance/backup_manifest.json`

## Verification

| Check | Result |
|---|---|
| Full test suite | 233 passed |
| Focused report/discovery regressions | 22 passed |
| Ruff | Passed |
| Strict mypy | Passed for 163 source files |
| Migrations | Schema 34/current |
| Warehouse integrity | Passed after migration and final acceptance |
| Pre-change backup | Verified schema 33; 14,648 files; nine critical tables |
| Pre-final-acceptance backup | Verified schema 34; 14,719 files; nine critical tables |
| Offline principal acceptance | 12/12 terminal; 11 fixtures with references; zero production/shadow labels |
| Final offline principal acceptance | 12/12 terminal; ten predictions; 467 prices; 135 research value signals; zero production/shadow labels |
| Historical offline report acceptance | 29 headers/cells reconciled; shortlist correctly empty because no row satisfied the independent evidence policy |
| Latest shortlist regression contract | 32 truthful columns plus quality funnel; one persisted live row independently reconciled |

## Remaining limitations

- Only 55 fixtures have prospective reference odds and seven shadow records have settled; this is not a sufficient prospective sample to demonstrate durable edge.
- There is no active market-family champion.
- Calibration and competition-scope validation currently cover `MATCH_ODDS` only. BTTS and totals remain research-priced but cannot enter the evidence-qualified shortlist until dedicated chronological validation exists.
- Historical pre-match odds, injuries, expected/confirmed lineups, and movement cannot be invented where they were not captured.
- Injury/lineup features have no useful historical training coverage; provider-dependent all-null or constant columns remain explicit but are excluded from fitted information.
- Competition admission, applicability, family qualification, calibration, uncertainty, and risk gates remain independent.
- DuckDB remains a coordinated single-writer local store, not a multi-process service database.

The correct next step is continued prospective collection and settlement, followed by predeclared chronological evaluation—not weaker gates or reinterpretation of research rankings as bets.

## Prediction-family experiment — 2026-10-14

PXR-001 extended new score-model evaluation artifacts with coherent BTTS and over/under 2.5 probabilities, observed goals, family-specific proper scores, direct-event calibration, fold-local empirical baselines, and paired chronological block-bootstrap comparison. On 9,460 identical out-of-fold fixtures, Dixon–Coles BTTS recorded log loss 0.691331 / Brier 0.248950 / ECE 0.035114; over 2.5 recorded 0.689288 / 0.247858 / 0.041127. Neither family clearly outperformed the simple fold-local event-rate baseline. Only 18/28 adequately sampled competitions passed the BTTS ECE bound and 15/28 passed the totals bound.

The hypothesis that global score-family evidence was sufficient for blanket validation was rejected. No live calibration, probability-scope, role, prediction, price, or opportunity row was changed. BTTS and totals remain research-priced but fail closed for the evidence-qualified shortlist. The durable record is `docs/research/PREDICTION_EXPERIMENT_REGISTER.md`; the implementation/result summary is `docs/reports/PREDICTION_PATH_UPGRADE_REPORT.md`.

Post-change verification: 239 tests passed, Ruff passed, mypy passed for 163 source files, and warehouse integrity passed. The final offline acceptance report was re-reconciled to the ledger: 12 expected / 12 terminal fixtures, ten predictions, 467 opportunities, 135 research-value signals, and zero shadow/production labels.

## Durable evidence

- Documentation map: `docs/README.md`
- Future-agent guardrails: `AGENTS.md`
- Pre-change baseline: `docs/audits/CURRENT_SYSTEM_BASELINE.md`
- Findings register: `docs/audits/IMPROVEMENT_REGISTER.md`
- Research record: `docs/research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md`
- Full audit report: `docs/reports/AUTONOMOUS_INSTITUTIONAL_CODEBASE_UPGRADE_REPORT.md`
- Satisfaction boundary: `docs/reports/CODEBASE_SATISFACTION_STATEMENT.md`
