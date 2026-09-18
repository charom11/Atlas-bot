# Atlas Institutional Backtest Remediation Plan

## Baseline
The prior 4-year audit showed negative expectancy, high friction costs, and capital starvation from minimum-notional rejection. This plan separates research validity from strategy optimization.

## Implemented in canonical_audit_v2.py
- Risk-based sizing at configurable equity risk per trade.
- 5x leverage cap by default.
- $5 minimum-notional gate.
- Portfolio simultaneous-position cap.
- 10% hard drawdown halt.
- 5 consecutive-loss halt.
- Real cached funding only; no synthetic funding.
- Fees and slippage included.
- Dataset schema and 15-minute gap validation.
- Chronological signal evaluation with no future-bar access.

## Next required work
1. Populate and validate real historical Binance funding for every symbol.
2. Wire every production Atlas signal component only when historical inputs are available.
3. Add independent P&L reconciliation against the trade ledger.
4. Add walk-forward train/validation/test periods.
5. Add ablation tests for MA, Fibonacci, MSS/SMC, divergence, liquidity, funding and adaptive weighting.
6. Add portfolio correlation/exposure limits.
7. Add restart-state/reconciliation tests to the live execution engine.
8. Add minimum-viable-balance persistent HALTED state to live execution.
9. Keep experimental backtest scripts clearly labeled and do not use them as production evidence.

## Research gates
A strategy change is not accepted merely because win rate improves. Evaluate net expectancy, profit factor, max drawdown, fee/funding drag, out-of-sample performance, and walk-forward stability.
