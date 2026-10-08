# Institutional Pricing Architecture

The pricing layer is independent from Typer and report presentation:

1. `markets.score_distribution` creates a tail-controlled joint score grid.
2. `markets.pricing` derives coherent core football market probabilities.
3. `markets.settlement` represents all Asian return states and prices them by expected return.
4. `markets.implied_probability` exposes multiple de-vig methods.
5. `markets.taxonomy` governs exact API-Football market mappings.
6. `analysis.dependencies` distinguishes football-state staleness from market-price staleness.
7. `analysis.service` persists and reconciles the complete requested fixture universe.
8. `reporting.html` renders a standalone report exclusively from the analysis result passed to it.

Migration 022 adds governed market mappings, date-range analysis runs, full-universe manifests, immutable institutional
prediction metadata, dependency/freshness state, exact source snapshots, engine independence labels, and per-engine market
prices. Existing prediction tables are preserved for compatibility and historical evidence.

The current operational evidence gate remains 500 training fixtures. The production ledger has 276 eligible fixtures, so no
institutional fused price or wagering recommendation is authorized.
