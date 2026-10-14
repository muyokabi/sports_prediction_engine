# Documentation Map

Use this page to distinguish current operating guidance from historical audit
evidence. Dated acceptance reports describe the system at the time of capture;
they are not automatically updated when model roles, warehouse counts, provider
access, or schema versions change.

## Current guidance

- [`../README.md`](../README.md): installation, normal commands, complete CLI
  guide, safety boundary, and generated-file retention.
- [`reports/CURRENT_IMPLEMENTATION_STATUS.md`](reports/CURRENT_IMPLEMENTATION_STATUS.md):
  latest reconciled operating classification and warehouse summary.
- [`operations/RUNBOOK.md`](operations/RUNBOOK.md): operator procedures,
  recovery, monitoring, backup, and scheduled maintenance.
- [`audits/IMPROVEMENT_REGISTER.md`](audits/IMPROVEMENT_REGISTER.md): open and
  closed findings. Open evidence deficits remain actionability blockers.
- [`research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md`](research/INSTITUTIONAL_IMPROVEMENT_RESEARCH.md):
  provider constraints and research decisions that govern future changes.
- [`prompts/PREDICTION_PATH_CODEX_PROMPT.md`](prompts/PREDICTION_PATH_CODEX_PROMPT.md):
  reusable Codex prompt for focused, iterative prediction-quality research and
  improvement runs.
- [`../AGENTS.md`](../AGENTS.md): non-negotiable repository guardrails.

## Historical evidence

The pre-upgrade baseline, provider qualification, forensics, and acceptance
reports under `audits/`, `providers/`, and `reports/` are retained as dated audit
evidence. Statements such as an active champion, an older schema number, a
specific quota balance, or an earlier fixture count are historical unless the
current status document repeats them.

Do not delete or rewrite historical reports merely because the state they
captured has changed. Supersede them through the current status, improvement
register, and a new dated report.

## Retention boundary

Immutable provider payloads, prediction/decision records, model artifacts,
feature datasets and sidecars, evaluation evidence, reports, quarantine
evidence, verified backups, and the DuckDB ledger are not disposable generated
files. The automated cleanup allowlist covers only regenerable test/development
debris documented in the README and runbook.
