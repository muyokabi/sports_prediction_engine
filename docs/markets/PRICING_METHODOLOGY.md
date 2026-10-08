# Institutional Pricing Methodology

## Probability layers

The platform keeps fundamental, ML, fused, and market probabilities distinct. Fundamental and ML prices are
`MARKET_INDEPENDENT` unless a versioned model manifest explicitly records market inputs. A fused price is not available until
chronological validation produces reproducible weights and demonstrates improved probability quality.

## Score distribution

Core football markets use a joint score distribution. The independent-Poisson implementation extends each marginal until its
omitted tail is below half of the configured joint tolerance, records the pre-normalization omitted mass, and then normalizes the
represented grid. Dixon-Coles retains its low-score adjustment over this dynamically sized grid.

The same grid derives 1X2, double chance, draw-no-bet, Asian handicap, Asian totals, BTTS, team totals, and correct score. This
prevents independent classifiers from silently producing contradictory prices for compatible score-derived markets.

## Asian settlement

Whole, half, and quarter lines settle to `FULL_WIN`, `HALF_WIN`, `PUSH`, `HALF_LOSS`, or `FULL_LOSS`. Quarter lines are split
equally across their adjacent whole/half lines. Fair odds solve zero expected net return across the complete settlement
distribution. Minimum acceptable odds solve the same equation for a configured minimum expected return.

## Market governance

Provider market IDs and exact names are mapped to canonical markets. An ID/name mismatch is disabled rather than guessed.
Unrecognized markets are retained as `UNSUPPORTED_SETTLEMENT`. Corners, cards, shots, and player markets remain
`RESEARCH_ONLY` until their separate stochastic models, history, calibration, and settlement contracts qualify.

## Market probabilities

Raw implied probability, proportional de-vig, power de-vig, and Shin-style de-vig are available. Production method selection by
market remains evidence-gated; no single method is declared universally superior. API-Football remains the sole odds source.

## Abstention

Positive raw edge is insufficient. Actionability additionally requires qualified model evidence, current odds, supported
settlement, resolved intervening fixtures, acceptable uncertainty/disagreement, and risk capacity. Until those conditions are
demonstrated, the terminal state remains an explicit abstention.
