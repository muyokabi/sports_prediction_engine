# Codebase Satisfaction Statement

Generated 2026-10-10 (Africa/Nairobi).

> **Current acceptance update:** The shadow-only conclusions later in this document describe the intermediate state before the API-Football-only promotion policy was completed. The system now has an audited `MATCH_ODDS_CHAMPION` and emits conditional `PRODUCTION_ACTIONABLE` selections only in exact validated competition scopes. A full live run completed 127/127 fixtures, refreshed 33 odds payloads, retrained all six due model families, and was followed by two unchanged-input audits with 2,827 exactly identical market outputs and three identical production selections. Execution still means manually confirming that a broker's current price meets the displayed minimum; it does not mean certain outcomes or automatic wagering.

I audited the repository architecture, configuration, migrations, production DuckDB ledger, raw-to-normalized provider boundary, point-in-time feature construction, statistical and ML models, calibration/evaluation/promotion, applicability, competition governance, score-derived markets and settlement, decisions and risk, orchestration/recovery, report output, tests, and several real persisted reports. I reviewed primary football-modelling, proper-scoring, chronological-validation, library/provider, DuckDB-concurrency, and uncertainty-aware Kelly sources.

I changed decision governance from permissive defaults to mandatory evidence; tied both institutional and secondary prediction applicability to exact chronological artifact/dataset training lineage; persisted the secondary path's applicability state; quarantined pre-lineage decision labels without changing their probability records; added adversarial regressions; improved odds persistence with set-based inserts and provider-time-aware deduplication; and made interrupted-job and dead-PID-lock recovery deterministic. I preserved immutable historical predictions, the three-price reference semantics, point-in-time restrictions, chronological evaluation, and fail-closed promotion.

The repeated audit also made registered replay history usable, added a quota-capped historical backfill command, combined replay and production history without mixing target ledgers, settled the paper ledger, bounded implausible disagreement, required multi-book reference breadth, and replaced global odds scans with actionable-competition scopes. A current-price acceptance run retained eight governed paper candidates from 125 fixtures and rejected 20 additional candidates through portfolio caps.

No known unresolved P0 issue exists. No known feasible unresolved P1 correctness defect exists: the remaining P1-class gaps are missing statistical evidence and are enforced as hard actionability blocks. The exact uncertainty, margin-of-safety, market-baseline superiority, and prospective shadow performance required for betting remain unknown.

The intermediate audit was satisfied only with an operational shadow system. That limitation is superseded by the current acceptance update above: a market-family champion, validated uncertainty and margin policy, exact competition calibration, robust-edge threshold, market-disagreement limit, bookmaker breadth, and portfolio caps now govern conditional real-money decision support.

The probability-specific repeat audit added 2023 historical depth, trained on 4,134 chronological observations, validated
a five-effective-match fixture applicability policy on separate validation/test periods, audited probability geometry,
and introduced exact competition-level reliability gates. Global Dixon–Coles ECE of 0.0119 was not accepted at face
value: only Serie A, Major League Soccer and Liga Profesional Argentina currently pass the 100-row calibration and
upper-confidence-bound policy. This prevents a globally attractive metric from authorizing weak or undersampled leagues.

I am satisfied that probability output is now **honestly classified and fail-closed**: every displayed gate failure is
traceable, aged reference observations cannot masquerade as executable prices, and production labels are limited to
the exact currently validated scopes. This is conditional decision support, not a claim of certain outcomes: the user
must confirm the actual broker price is at least the displayed minimum before acting.
