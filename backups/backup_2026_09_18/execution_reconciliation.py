"""Idempotent Binance order-submission guard.

This module contains the side-effect-free decision layer used by the execution
adapter. It validates an entry, assigns a deterministic client order id, and
requires reconciliation by that id before an ambiguous submission can be
retried. The exchange-specific HTTP adapter is injected by the caller.
"""

import math
import time
from typing import Any, Callable, Optional

from trading_safety import (
    InvalidOrderRequest,
    find_order_by_client_id,
    make_client_order_id,
    response_is_ambiguous,
    validate_order_request,
)


class AmbiguousOrderSubmission(RuntimeError):
    """Raised when Binance cannot prove whether an order was accepted."""


def _reconciled_order(result: Any, client_order_id: str) -> Optional[dict]:
    """Extract only the order whose client ID matches the pending submission."""
    if isinstance(result, dict):
        if str(result.get("clientOrderId") or result.get("origClientOrderId") or "") == client_order_id:
            return result if result.get("orderId") is not None else None
        return None
    if result:
        return find_order_by_client_id(result, client_order_id)
    return None


def _poll_reconciliation(
    reconcile: Callable[[str], Any],
    client_order_id: str,
    *,
    attempts: int,
    delay: float,
    sleep_fn: Callable[[float], None],
) -> Optional[dict]:
    """Give Binance a short eventual-consistency window before retrying a submit."""
    for attempt in range(1, max(1, attempts) + 1):
        existing = _reconciled_order(reconcile(client_order_id), client_order_id)
        if existing is not None:
            return existing
        if attempt < attempts and delay > 0:
            sleep_fn(delay)
    return None


def submit_market_order_idempotent(
    *,
    symbol: str,
    side: str,
    quantity: float,
    submit: Callable[[dict], Any],
    reconcile: Callable[[str], Any],
    min_qty: float = 0.0,
    max_qty: Optional[float] = None,
    nonce: Optional[int] = None,
    intent: str = "ENTRY",
    reconcile_attempts: int = 3,
    reconcile_delay: float = 0.25,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Any:
    """Submit one market order without blind duplication.

    ``submit`` receives the complete order params, including ``newClientOrderId``.
    ``reconcile`` must query authoritative Binance order state using that client
    id and return either an order/list of orders or ``None`` when no matching
    order exists.

    A successful response is returned immediately. An ambiguous response is
    reconciled with a short bounded polling window first. Only when Binance
    repeatedly proves no matching order exists is the submission retried once
    with the same client id. A second ambiguous response is reconciled again and
    then fails closed instead of submitting a third order.
    """
    if reconcile_attempts < 1:
        raise InvalidOrderRequest("reconcile_attempts must be at least 1")
    if not math.isfinite(float(reconcile_delay)) or reconcile_delay < 0:
        raise InvalidOrderRequest("reconcile_delay must be finite and non-negative")

    symbol, side, quantity, _ = validate_order_request(
        symbol, side, quantity, min_qty=min_qty, max_qty=max_qty
    )
    client_order_id = make_client_order_id(symbol, side, intent, nonce=nonce)
    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": quantity,
        "newClientOrderId": client_order_id,
    }

    response = submit(dict(params))
    if not response_is_ambiguous(response):
        return response

    existing = _poll_reconciliation(
        reconcile,
        client_order_id,
        attempts=reconcile_attempts,
        delay=reconcile_delay,
        sleep_fn=sleep_fn,
    )
    if existing is not None:
        return existing

    # Binance has repeatedly shown no matching order. Retry exactly once with
    # the same client id. Never issue a third blind submission.
    retry_response = submit(dict(params))
    if response_is_ambiguous(retry_response):
        existing = _poll_reconciliation(
            reconcile,
            client_order_id,
            attempts=reconcile_attempts,
            delay=reconcile_delay,
            sleep_fn=sleep_fn,
        )
        if existing is not None:
            return existing
        raise AmbiguousOrderSubmission(
            f"Unable to prove Binance accepted or rejected {client_order_id}"
        )
    return retry_response
