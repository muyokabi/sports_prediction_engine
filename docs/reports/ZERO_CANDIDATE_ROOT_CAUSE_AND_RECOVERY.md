# Zero-candidate root-cause analysis and recovery

Date: 2026-10-10

## Outcome

The system was not seeing “no market disagreement.” It had persisted 17,571 positive reference discrepancies, but its
admission logic made a shadow candidate conditional on already having production-qualified calibration, market-role,
uncertainty, margin and applicability policies. Those policies require prospective evidence, so the shadow ledger could
never bootstrap. At the same time, the score model used by institutional pricing was frozen at 272 observations with a
2026-09-18 cutoff, while the current feature dataset contained 2,962 observations.

The repaired point-in-time replay `5b2a3b8d-e328-4f8b-af5c-fca87898fa94` completed 165/165 fixtures and persisted ten
capped `SHADOW_ACTIONABLE` rows plus 62 cap-rejected shadow rows. The active rows are only from `MATCH_ODDS`, `BTTS`,
and `TOTAL_GOALS`. They remain `WATCH`, require manual price confirmation, have null robust/execution edge, and carry
`SHADOW_ONLY_NOT_PRODUCTION_APPROVED`. This is proof that opportunity discovery now works; it is not evidence that any
row is suitable for a real-money wager.

## Root causes

1. **Circular governance.** `SHADOW_ACTIONABLE` required all production gates. No shadow sample could exist to validate
   those gates.
2. **Stale fundamental model.** Continuous learning covered only logistic, CatBoost and LightGBM, even though the
   institutional market engine consumes Poisson/Dixon-Coles score distributions.
3. **Evaluation artifact used as deployment artifact.** Statistical artifacts were fitted only on the chronological
   training partition. Validation/test rows correctly remained untouched for evaluation, but no post-evaluation all-data
   refit occurred, leaving production coverage needlessly stale.
4. **Missing applicability policy.** Even structurally in-domain, partially pooled fixtures failed production actionability
   because no model-specific history threshold had prospective validation.
5. **No fundamental market-family champion.** Promotion currently creates `MATCH_ODDS` roles for classifiers, while the
   fundamental engine prices several score-derived families. Calibration, uncertainty and margin policies therefore remain
   absent for those families.
6. **Narrow competition governance.** Only ten competition-seasons are `ACTIONABLE`; 58 are observation-only. Collection
   breadth therefore does not imply execution eligibility.
7. **Derivative line orientation defect.** API-Football Asian-handicap lines are home-perspective values for both selections,
   but the away selection had been settled as if the line were away-perspective. This created impossible-looking apparent
   edges. Migration 032 quarantines every previously active Asian-handicap shadow row.
8. **Large-slate persistence cost.** The engine wrote tens of thousands of low-value derivative research rows serially.
   The governed live candidate universe is now restricted to three explicitly allowed families, cutting the replay from
   37,780 to 7,454 opportunity rows.
9. **Interrupted analysis rows.** A killed process can leave `analysis_runs.state='RUNNING'`. Startup now closes runs older
   than the configured stale threshold as `FAILED`.

## Executable upgrades delivered

- Added `shadow_candidates` configuration with explicit freshness, probability advantage, reference return, effective
  history, prior-dependence, family allowlist and portfolio caps.
- Separated shadow admission from production approval. Missing production gates remain visible and still block execution.
- Kept `robust_estimated_edge` and `execution_edge` null until their respective evidence exists.
- Added one candidate per fixture and ten per run caps; excess rows become `SHADOW_REJECTED`/research signals.
- Extended due-model orchestration to Elo, Poisson and Dixon-Coles.
- Added post-holdout full-data refits for statistical deployment artifacts while recording both evaluation and deployment
  cutoffs. The refreshed score artifacts use 2,962 rows and a 2026-10-06 deployment cutoff.
- Permitted the newest production-evidence statistical challenger to generate research/shadow prices without promoting it
  to a production market role.
- Corrected away Asian-handicap line orientation, excluded that family from shadow admission pending dedicated validation,
  and quarantined legacy rows via migration 032.
- Limited dynamically discovered pricing rows to the governed shadow family allowlist.
- Added stale analysis-run recovery and focused regression tests.

## Evidence and interpretation

The current Dixon-Coles challenger recognizes 134/164 priceable fixtures on the 2026-10-10 replay as partially pooled,
versus 32 under the stale champion in earlier audits. On the 2026-10-11 replay it recognizes 106/123 priceable fixtures;
tomorrow still has no candidate because all persisted quotes are aged. That abstention is correct.

The ten replay candidates are prospective paper records only. Their historical reference ages were 112.7–174.8 minutes,
inside the configured 180-minute limit at the replay cutoff. They must not be presented as current prices or bets.

Model comparison continues to use chronological partitions and proper probability scores. Time-ordered splitting avoids
training on future observations, and log loss/Brier/RPS remain appropriate evaluation tools. See scikit-learn's
[TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html),
[Gneiting and Raftery on proper scoring rules](https://doi.org/10.1198/016214506000001437), and the original
[Dixon–Coles football-score model](https://doi.org/10.1111/1467-9876.00065).

## Remaining route to real execution

1. Accumulate and settle the new shadow ledger prospectively.
2. Validate an applicability threshold on validation periods, then confirm it on untouched test periods.
3. Build per-family calibration and uncertainty reports for fundamental prices.
4. Compare candidates against timestamp-aligned bookmaker baselines and closing prices with paired uncertainty intervals.
5. Promote a market-family role only after significant non-inferiority/outperformance and adequate sample size.
6. Add broker/exchange quotes, commission, liquidity and slippage. Until then execution edge is unknowable.
7. Bulk-write reference and opportunity rows to reduce large-slate latency further.

The useful operating state is now **paper opportunity discovery with fail-closed real-money execution**.

## Repeat audit: historical learning and current-price acceptance

On 2026-10-10 the repeat audit found two additional availability defects. The 2024 replay ledger contained 3,276
completed fixture skeletons but zero ML-eligible detail packages, and production features could not consume replay
history. In addition, odds collection scanned the provider's global date surface instead of the locally actionable
competition universe. That global scan was stopped once observed; the corrected path requests only scheduled
`ACTIONABLE` league-season scopes.

The new quota-capped historical operator enriched 241 replay matches from 62 detail requests (including batch and
targeted repair requests), with 46 provider-incomplete fixtures retained as `PENDING_REPAIR`. Combined chronological
training then used 3,203 observations. All six model families were refitted and evaluated; none was promoted. CatBoost
log loss improved from 1.053878 to 1.045485, while Elo, Poisson, and Dixon-Coles also improved modestly on the larger
test sample. Logistic regressed slightly, demonstrating why adding rows is measured rather than assumed beneficial.

The corrected 2026-10-11 live price refresh collected 33 relevant fixtures with zero unknown fixtures. Analysis run
`7df3a009-ec1b-48a6-9e4f-7688298f119c` reconciled 125/125 fixtures, retained eight `SHADOW_ACTIONABLE` candidates, and
rejected 20 additional qualifiers under the one-per-fixture/ten-per-run portfolio policy. Each retained candidate had
7–10 reference snapshots; the new policy also requires at least two distinct bookmakers and rejects absolute probability
disagreements above 0.15. These rows still carry `SHADOW_ONLY_NOT_PRODUCTION_APPROVED`, require manual price confirmation,
and have null robust/execution edge.

## Probability reliability re-audit

The combined 2023/2024 replay and production ledger now supplies 4,134 training rows. The newest Dixon–Coles challenger
has a validated five-effective-match applicability policy, and its four-fold walk-forward result over 1,904 predictions
is log loss 1.054578, Brier 0.635710, RPS 0.222855 and ECE 0.011938. Probability geometry passes, 1X2 normalization error
is below `6e-16`, and the live board does not exhibit a generic-vector collapse.

The deeper review also proved that the strong global calibration average concealed league heterogeneity. Migration 033
now persists model-version-specific competition validation and runtime requires it for production actionability. Only
Serie A, Major League Soccer and Liga Profesional Argentina presently clear the 100-row, ECE and upper-confidence-bound
policy. Premier League, Bundesliga and every undersampled league fail closed. See
[Prediction Probability Forensics](./PREDICTION_PROBABILITY_FORENSICS.md) for the full evidence.

Aged references are still retained, because quote age is not an arbitrary veto, but they no longer outrank current
references merely because an old price implies a large paper return. Reports label them for recheck and expose all gate
failures. Shadow rows are explicitly described as prospective observations, never betting picks.
