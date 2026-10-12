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
| GOV-004 | P1 | Promotion ignored an evaluator's explicit failed aggregate probability-forensics verdict, and did not reassess the selected incumbent. | Promotion now requires `probability_forensics.passed=true`; governed incumbents are reassessed and demoted immediately when evidence fails. | Fixed |
| OPS-001 | P1 | Failed jobs reported zero requests despite durable request-log evidence. | Job summaries derive billable request counts from `api_request_log`, excluding `/status`, on success and failure. | Fixed going forward |
| OPS-002 | P1 | Replay bootstrap reset completed seasons to index zero, wasting roughly two calls per season on every retry. | Exact season signatures and local-completion detection skip already complete historical teams/fixtures; current seasons still refresh. | Fixed |
| OPS-004 | P1 | Principal orchestration never ran competition discovery, while odds scoping required `ACTIONABLE` discovery rows. Empty scope silently caused zero odds requests. | Live daily runs discovery before fixtures/odds; empty odds scope returns an explicit blocker. The acceptance run stored odds for all six target fixtures. | Fixed |
| OPS-005 | P1 | `fetch-backfill --past-seasons` was permanently bound to ten YAML seeds, so “five seasons” meant only 50 league-seasons. | Backfill now discovers first and selects a bounded 40-league governed universe by default, without auto-promoting observation leagues. | Fixed |
| DOC-002 | P1 | README commands were fragmented and easy for a fresh-clone operator to run out of order or omit. | Quick start is now an ordered migrate/verify → discovery-backed backfill → train → live-run sequence; specialist commands are labelled optional. | Fixed |
| ART-001 | P2 | HTML, model, and evaluation artifacts accumulated in flat directories. | New artifacts use `YYYY/MM/DD` partitions; old paths remain valid and evaluation discovery is recursive. | Fixed |
| SEC-001 | P2 | Pickle loads had no content-integrity verification. | New model/calibrator manifests include and verify SHA-256 digests. Legacy hashless artifacts remain trusted-local only. | Fixed for new artifacts; legacy limitation open |
| RISK-001 | P1 | Repeated repricing of one fixture could double-count portfolio exposure. | Exposure is deduplicated per fixture before daily aggregation. | Fixed |
| DATA-001 | P1 | Only a small fraction of the historical archive had been enriched. | Backfill raised ML-eligible rows to 8,271; 770 assessed packages remain pending repair and are excluded. | Mitigated; repair backlog open |
| MKT-001 | P1 | There were zero odds snapshots because discovery produced no request scopes. | Live validation stored 7 snapshots and 30,258 prices across 10 bookmakers for all six target fixtures. Prospective depth and settled baselines remain insufficient for actionability. | Code fixed; evidence accumulation open |
| MOD-001 | P1 | The registered champion failed aggregate probability forensics. | Invalid incumbent was demoted. Six fresh model candidates were trained on 8,271 observations; no production champion was allowed through. | Fixed fail-closed; evidence blocker remains |
| MOD-002 | P2 | Dixon-Coles rho optimization is not time-weighted with the base fit. | Benchmark as a chronological challenger experiment; do not change it without evidence. | Open research |
| OPS-003 | P2 | Existing failed job rows retain their original zero-request metrics. | Preserved as immutable history; the audit reconciles them against the request log. | Controlled |

No known unresolved feasible P0/P1 code defect remains. Remaining P1 limitations are prospective evidence deficits—market history, settled shadow performance, and a statistically qualified champion—and are enforced as hard actionability blocks.
