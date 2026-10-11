# Improvement Register

Audited 2026-10-11. Severity reflects possible decision impact.

| ID | Sev | Finding | Resolution / remaining work | Status |
|---|---|---|---|---|
| DOC-001 | P1 | Baseline and acceptance documents claimed warehouse populations and production actionability absent from the current database. | Replaced authoritative baseline, report, status, and satisfaction statement with warehouse-derived facts. | Fixed |
| GOV-001 | P1 | Registry promotion treated a missing evidence state as acceptable. | Promotion now requires exact `PRODUCTION_ACTIONABLE`; null/unassessed fails closed. | Fixed |
| GOV-002 | P1 | Prediction and analysis could ignore governed minimum-return and uncertainty policies or accept malformed numeric values. | Both paths consume validated nonnegative finite policy values; absent/malformed policy blocks robust actionability. | Fixed |
| GOV-003 | P1 | Invalid, nonfinite, out-of-range, or non-normalized probabilities and malformed quotes could enter a decision. | Explicit probability-vector validation and safe quote filtering added with reason codes. | Fixed |
| APP-001 | P1 | Statistical applicability could use unrelated warehouse history rather than exact model-fit rows. | Artifacts persist fitted fixture, team-history, and competition lineage; missing legacy lineage is out of domain. | Fixed |
| EVAL-001 | P1 | A promotion could consume a walk-forward report from a different candidate of the same family/dataset. | Evaluation binds candidate version, features, hyperparameters, and calibration; promotion requires that exact candidate. | Fixed |
| EVAL-002 | P1 | Missing evaluation reports were represented by `{}`, bypassing the intended missing-report branch. | Missing report now returns `None` and emits `WALK_FORWARD_REPORT_MISSING`. | Fixed |
| OPS-001 | P1 | Failed jobs reported zero requests despite durable request-log evidence. | Job summaries derive billable request counts from `api_request_log`, excluding `/status`, on success and failure. | Fixed going forward |
| OPS-002 | P1 | Replay bootstrap reset completed seasons to index zero, wasting roughly two calls per season on every retry. | Exact season signatures and local-completion detection skip already complete historical teams/fixtures; current seasons still refresh. | Fixed |
| ART-001 | P2 | HTML, model, and evaluation artifacts accumulated in flat directories. | New artifacts use `YYYY/MM/DD` partitions; old paths remain valid and evaluation discovery is recursive. | Fixed |
| SEC-001 | P2 | Pickle loads had no content-integrity verification. | New model/calibrator manifests include and verify SHA-256 digests. Legacy hashless artifacts remain trusted-local only. | Fixed for new artifacts; legacy limitation open |
| RISK-001 | P1 | Repeated repricing of one fixture could double-count portfolio exposure. | Exposure is deduplicated per fixture before daily aggregation. | Fixed |
| DATA-001 | P1 | Only 161 fixtures are ML eligible, including 54 from 16,595 completed replay fixtures. | Resume the checkpointed backfill after connectivity returns; do not weaken quality gates. | Open; blocks actionability |
| MKT-001 | P1 | There are zero odds snapshots and no time-correct market baseline. | Accumulate immutable prospective pre-match observations. Historical odds cannot be reconstructed honestly. | Open; blocks actionability |
| MOD-001 | P1 | Ten candidates exist, but no champion, validated scope, or production applicability evidence exists. | Retrain/evaluate after backfill, then allow normal exact-candidate gates to decide. | Open; blocks actionability |
| MOD-002 | P2 | Dixon-Coles rho optimization is not time-weighted with the base fit. | Benchmark as a chronological challenger experiment; do not change it without evidence. | Open research |
| OPS-003 | P2 | Existing failed job rows retain their original zero-request metrics. | Preserved as immutable history; the audit reconciles them against the request log. | Controlled |

No known unresolved P0 defect remains. Open P1 items are evidence deficits that are enforced as hard actionability blocks, not permissions to relax controls.
