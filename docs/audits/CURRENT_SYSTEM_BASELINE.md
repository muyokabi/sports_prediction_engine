# Current System Baseline

Post-upgrade evidence snapshot taken 2026-10-10 (Africa/Nairobi). This is an operational and research baseline, not a real-money betting approval.

## Architecture and operating boundary

API-Football responses are retained as compressed raw evidence, normalized into DuckDB, qualified for point-in-time use, converted into immutable Parquet datasets, evaluated chronologically, and persisted as predictions, reference prices, governed opportunities, paper outcomes, and HTML reports. Production targets remain separate from the replay ledger; configured replay ledgers may contribute only earlier completed-match history.

The supported operating state is `SHADOW`: paper opportunities can be discovered, capped, persisted, and settled. Real-money action remains fail-closed because no market-family champion, validated uncertainty/margin policy, broker execution price, liquidity/slippage model, or settled prospective paper sample exists.

## Current ledger

| Evidence | Value |
|---|---:|
| Competitions / competition seasons | 1,240 / 1,250 |
| Teams / fixtures / completed | 882 / 17,838 / 8,877 |
| Quality assessed / ML eligible / pending repair | 5,754 / 3,203 / 2,551 |
| Production / replay ML-eligible history | 2,962 / 241 |
| Odds snapshots / price rows / fixtures with odds | 915 / 2,732,453 / 266 |
| Model runs | 30 |
| Institutional predictions / opportunities | 1,966 / 194,676 |
| Shadow rows / active / settled | 380 / 18 / 0 |
| Running jobs / running analyses | 0 / 0 |

Competition discovery remains deliberately narrow: 10 `ACTIONABLE`, 58 `OBSERVATION`, 1,068 `DISCOVERED`, and 104 `REJECTED`. Odds refresh now requests only scheduled `ACTIONABLE` competition-seasons rather than scanning the global provider date surface.

## Data and models

The 2024 replay season began with 3,276 completed skeletons and zero usable detailed packages. A request-capped tranche selected 298 fixtures across two measured runs and produced 241 ML-eligible packages; 46 provider-incomplete packages remain pending repair. The successful 250-request run used only 59 detail calls plus status to make 205 of 238 selected fixtures eligible.

All six model families were refitted on 3,203 chronological observations. Latest aggregate walk-forward evidence uses 1,567 test predictions:

| Model | Log loss | Brier | RPS | ECE |
|---|---:|---:|---:|---:|
| CatBoost | 1.045485 | 0.628637 | 0.218581 | 0.029409 |
| Dixon-Coles | 1.057779 | 0.638023 | 0.223210 | 0.016180 |
| Poisson | 1.058073 | 0.638119 | 0.223226 | 0.021366 |
| Elo | 1.067538 | 0.645178 | 0.226565 | 0.012974 |
| LightGBM | 1.125240 | 0.676498 | 0.235814 | 0.117577 |
| Logistic | 1.128485 | 0.679109 | 0.233872 | 0.096100 |

No model was promoted. The improvement in CatBoost and the score models is useful research evidence, but not proof of market superiority.

## Opportunity acceptance

The current-price acceptance run `7df3a009-ec1b-48a6-9e4f-7688298f119c` completed 125/125 fixtures for 2026-10-11. It persisted 8 retained `WATCH/SHADOW_ACTIONABLE` opportunities and 20 cap-rejected paper qualifiers. Retained markets were match odds and total goals; each had 7–10 reference snapshots. Shadow policy requires a fresh reference, actionable competition, fitted teams, minimum effective history, limited prior dependence, at least two bookmakers, expected reference return of at least 3%, probability advantage of at least 3%, and absolute model/market disagreement no greater than 15%.

Every active row is paper-only, requires manual price confirmation, carries `SHADOW_ONLY_NOT_PRODUCTION_APPROVED`, and has null robust and execution edge. Shadow settlement now supports match odds, BTTS, and whole/half/quarter total lines, but zero active candidate has matured yet.

## Known limitations

- Real-money validity is blocked by missing prospective settlement, closing-line, calibration, uncertainty, margin, commission, liquidity, and execution evidence.
- 2,551 assessed packages remain pending repair; provider-null detail is quarantined rather than imputed.
- Only the first useful 2024 historical tranche has been enriched. Finish high-yield 2024 collection before registering older seasons.
- Model artifacts use trusted-local pickle provenance; signing/verification is still recommended before remote deployment.
- Full HTML audit payloads remain large.
