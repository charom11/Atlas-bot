# Atlas Bot Audit & Remediation Report

Date: 2026-09-18
Branch audited: `main`

## Scope

Read-only review of the production trading path, runtime configuration, Docker deployment, dependency configuration, CI, and existing tests. This remediation commit focuses on preventing accidental live execution and improving reproducibility. Strategy behavior is intentionally unchanged.

## Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| ATLAS-001 | Critical | Docker previously started `main.py --trade-live` unconditionally. | Fixed |
| ATLAS-002 | Critical | Realized-PnL events are treated as trades, which can over-count partial closes. | Requires execution-ledger refactor |
| ATLAS-003 | Critical | Market-data cache can retain stale data after REST failures. | Requires data-freshness gate |
| ATLAS-004 | High | Circuit-breaker state is primarily in memory and restart reconstruction is incomplete. | Requires persistent/reconciliation state |
| ATLAS-005 | High | Production Docker command hard-coded 50x leverage and 3% margin allocation. | Fixed at deployment layer |
| ATLAS-006 | High | Live/testnet/paper environments lacked a strong startup separation. | Fixed at deployment layer |
| ATLAS-007 | Medium | Production dependencies use broad minimum-version ranges. | Follow-up: lock/pin dependencies |
| ATLAS-008 | Medium | Docker installed `rich`, `websocket-client`, and `ccxt` twice. | Fixed |
| ATLAS-009 | Medium | CI lacked dedicated runtime-safety and failure-mode tests. | Safety tests added |
| ATLAS-010 | Medium | Experimental/archive implementations increase production-path maintenance risk. | Follow-up cleanup |

## Remediation in this commit

### 1. Explicit runtime safety guard

`runtime_guard.py` now defaults to non-live operation. Live trading requires both:

- `ATLAS_LIVE_TRADING=true`
- `ATLAS_LIVE_CONFIRM=true`

Live mode also requires Binance credentials. Risk parameters are read from environment variables and validated before `main.py` starts.

### 2. Docker safety

The Docker image now starts through `runtime_guard.py` instead of hard-coding `--trade-live`, 50x leverage, and 3% margin. This prevents a normal container restart from silently enabling live orders.

### 3. Compose safety

`docker-compose.yml` supplies safe non-live defaults and makes the `.env` mount read-only.

### 4. Dependency/build cleanup

Duplicate package installation in the Dockerfile was removed.

### 5. Automated tests

Tests cover the default non-live command, explicit live confirmation, credential checks, and invalid risk configuration.

## Important remaining work

This commit does **not** claim the strategy or execution engine is production-safe. Before live deployment, the remaining high-risk work should include:

1. Reconstruct circuit-breaker state from Binance after restart.
2. Aggregate fills/income into logical trades instead of counting every income event as a trade.
3. Add hard data-freshness gates for REST/WebSocket market data.
4. Reconcile open positions and orders before accepting new entries.
5. Add mocked exchange integration tests for partial fills, rejected orders, duplicate submissions, timeouts, and reconnects.
6. Pin/lock production dependencies.
7. Run the full suite and Binance testnet validation before enabling live mode.

## Validation note

The repository's existing CI runs Docker build, pytest, and Python compilation. The new safety tests are designed to run without exchange credentials or live network access.

## Change policy

No strategy thresholds, signal models, or trading logic were intentionally changed in this remediation pass. The objective is to reduce accidental live execution and deployment risk first.
