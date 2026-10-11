# Autonomous Institutional Codebase Upgrade Report

Generated 2026-10-11 (Africa/Nairobi). Work after the connectivity outage was strictly offline.

## Executive verdict

The repository is materially safer, more reproducible, and easier to operate. It is suitable for continued offline research and checkpointed data accumulation. It is **not suitable for real-money decision support** in its current evidence state.

The current warehouse contains no odds, no production-actionable champion, no institutional predictions or opportunities, and no prospective shadow outcomes. The correct classification is `RESEARCH_ONLY / FAIL_CLOSED`. Earlier acceptance text claiming millions of odds rows, an actionable champion, or live selections was not supported by this database and has been replaced.

## Verified baseline

The database contains 10 competitions, 60 competition seasons, 279 teams, 19,774 fixtures, and 17,179 completed fixtures. Only 250 packages have been assessed: 161 are ML eligible and 89 await repair. Production contributes 107 eligible matches; replay contributes 54. Ten model candidates exist, the latest trained on 107 rows. All market roles are challengers.

The interrupted five-season backfill ended with a DNS `PROVIDER_UNAVAILABLE` error. Its durable request log records 111 billable requests after excluding `/status`, and its detailed checkpoint remains at index 3. No network retry or connectivity probe was performed during the outage.

## Material changes

### Governance and numerical safety

- Promotion requires exact `PRODUCTION_ACTIONABLE` evidence; null no longer passes.
- Prediction and analysis consume governed minimum-return and uncertainty policies; missing, negative, malformed, or nonfinite values fail closed.
- Probability vectors must be finite, bounded, and normalized. Invalid quotes are ignored safely with explicit reasons.
- Daily portfolio exposure deduplicates repeated repricing of a fixture.

### Model lineage and evaluation

- Statistical artifacts persist exact fitted fixtures, team-history counts, and competition counts.
- Applicability uses artifact lineage; old artifacts without it are `OUT_OF_DOMAIN`.
- Walk-forward reports are tied to the exact candidate version, features, hyperparameters, and calibration method.
- Calibrated folds reserve a later training-era calibration segment rather than fitting calibration on test observations.
- Promotion cannot reuse a report from another candidate, and a missing report now follows the intended rejection path.

### Artifact integrity and organization

- New model and calibrator pickle files carry verified SHA-256 digests.
- New reports, models, and evaluations are stored beneath `YYYY/MM/DD` directories.
- Old flat artifacts remain in place so registry links do not break; discovery is recursive for compatibility.

### Resumability and quota evidence

- Failed and successful jobs derive billable request counts from durable request records.
- Historical bootstrap checkpoints carry an exact season-universe signature.
- Completed replay seasons with local teams and fixtures are marked complete without repeated provider calls; current seasons still refresh.

### Auditability

- `scripts/warehouse_audit.py` emits a read-only JSON warehouse snapshot.
- Authoritative baseline, implementation status, improvement register, research notes, and acceptance statements now match the current database.

## Verification

| Check | Result |
|---|---|
| Full offline test suite | 190 passed in 90.65 seconds |
| Ruff | Passed for `src`, `tests`, and `scripts` |
| Strict mypy | Passed for 160 source files |
| Warehouse audit | Read-only snapshot completed |
| Offline end-to-end | 6 expected = 6 terminal; dated HTML report written |
| Backup verification | Schema 33; 571 files; nine critical table counts verified |
| Warehouse integrity | Passed after offline acceptance |
| Network use after outage | None |

Targeted regressions cover promotion evidence, invalid probabilities, governed policies, exact lineage, candidate-bound reports, calibrated evaluation, artifact tampering, request telemetry, dated artifact paths, and historical-bootstrap resume behavior.

The end-to-end analysis run was `a12eaf9a-95e5-42f4-884d-6fc49904d407`; it reconciled 6/6 fixtures with no provider calls and wrote `artifacts/reports/2026/10/11/analysis-2026-10-12-2026-10-12-a12eaf9a-95e5-42f4-884d-6fc49904d407.html`. The verified backup manifest is `artifacts/backups/institutional-audit-2026-10-11/backup_manifest.json`.

## Remaining blockers

The backfill must finish and produce a materially larger eligible sample. Models must then be retrained and evaluated without bypassing exact candidate gates. Prospective odds and shadow outcomes must be accumulated before market comparison, uncertainty/margin calibration, or return claims are possible. Legacy hashless pickle artifacts must remain trusted-local only. Dixon-Coles weighted-rho and more complex models are research hypotheses, not automatic improvements.

No known feasible P0 defect remains. The unresolved P1 items are missing evidence and are enforced as hard abstention conditions.
