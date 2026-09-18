# Atlas Continuous Development

## Principle
Atlas development is continuous; production deployment is gated. No commit may automatically change live trading behavior.

## Loop
1. Observe logs, data quality, rejected orders, execution and performance.
2. Record a GitHub issue with reproduction and impact.
3. Implement a focused change with tests.
4. Run `python backtests/continuous_regression.py` for data/regression smoke validation.
5. Run the canonical institutional audit manually for strategy/release candidates.
6. Run walk-forward and out-of-sample validation for strategy changes.
7. Paper trade the exact release candidate.
8. Review results and approve a release manually.
9. Merge/release and update the research baseline only from verified results.

## Never auto-modify
- live leverage cap
- per-trade risk
- portfolio risk limits
- maximum drawdown halt
- emergency stop
- API permissions
- withdrawal permissions

## Experiment record
Every strategy experiment should record: commit SHA, dataset/version, date range, parameters, fees, slippage, funding coverage, trade count, expectancy, profit factor, max drawdown, and out-of-sample result.

## Required validation
A release candidate must distinguish in-sample, validation, and out-of-sample periods. Synthetic market data must never be presented as historical performance. Missing funding or execution inputs must be reported rather than silently replaced with zero.

## Automation policy
CI may run lightweight tests on pull requests. Direct pushes to `main` must not launch the failing Docker trading/backtest flow. Full backtests remain manually triggered until the pipeline is proven stable.
