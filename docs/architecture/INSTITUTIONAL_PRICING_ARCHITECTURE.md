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

The current ledger has 18,767 quality-assessed, ML-eligible completed fixtures across production and replay evidence. A
chronologically evaluated score model is available for research pricing, but there is no active market-family champion: the
configured `MATCH_ODDS` promotion policy requires a point-in-time API-Football baseline and statistically significant market
outperformance, while the persisted evaluation has zero qualifying baseline rows. The engine therefore continues to publish
research probabilities and coherent score-derived fair prices, but no fused price or real-money recommendation is authorized.
