"""Safety primitives for Binance Futures order management.

These helpers are intentionally side-effect free so they can be unit-tested without
placing real orders. Integrations should fail closed when authoritative Binance
state is unavailable.
"""

from dataclasses import dataclass
import math
import re
import time
from typing import Any, Callable, Iterable, Optional


class TradingStateUnavailable(RuntimeError):
    """Raised when an authoritative trading-state query fails."""


class InvalidOrderRequest(ValueError):
    """Raised when an order request is unsafe or internally inconsistent."""


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay: float
    reason: str


# These are safe to retry only when the caller's operation is idempotent or has
# already reconciled its clientOrderId. In particular, -1015 means the account
# has hit an order-rate limit, so blindly retrying it can make the condition worse.
_RETRYABLE_CODES = {
    -1001,  # DISCONNECTED
    -1003,  # TOO_MANY_REQUESTS / IP ban warning
    -1006,  # UNEXPECTED_RESP
    -1007,  # TIMEOUT
    -1021,  # INVALID_TIMESTAMP
}
_RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,32}$")


def _is_timeout_like(error: Any) -> bool:
    """Recognize timeout exceptions without treating arbitrary text as transient."""
    if isinstance(error, (TimeoutError,)):
        return True
    name = type(error).__name__.lower()
    return "timeout" in name


def classify_binance_error(error: Any, attempt: int, max_attempts: int = 3) -> RetryDecision:
    """Classify an exception/response for bounded retry with exponential backoff.

    Order rejection (-2010) is deliberately *not* blindly retried because the
    original order may have reached the exchange even when the client response
    is ambiguous. Integrations must reconcile by clientOrderId before retrying.
    """
    code = None
    status = None
    message = str(error)
    if isinstance(error, dict):
        code = error.get("code")
        status = error.get("status") or error.get("http_status")
        message = str(error.get("msg", message))
    else:
        code = getattr(error, "code", None)
        status = getattr(error, "http_status", None) or getattr(error, "status_code", None)
    try:
        code = int(code) if code is not None else None
    except (TypeError, ValueError):
        code = None
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None

    retryable = status in _RETRYABLE_HTTP or code in _RETRYABLE_CODES or _is_timeout_like(error)

    if attempt >= max_attempts or not retryable:
        return RetryDecision(False, 0.0, f"non-retryable or retry budget exhausted: {message}")

    delay = min(8.0, 0.5 * (2 ** max(0, attempt - 1)))
    return RetryDecision(True, delay, f"transient Binance/API failure: {message}")


def retry_call(fn: Callable[[], Any], *, max_attempts: int = 3, sleep_fn=time.sleep) -> Any:
    """Run a callable with bounded exponential backoff for retryable failures."""
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            decision = classify_binance_error(exc, attempt, max_attempts)
            if not decision.retry:
                raise
            sleep_fn(decision.delay)
    raise last_error  # pragma: no cover


def require_authoritative_positions(positions: Optional[Iterable[Any]]) -> list:
    """Convert authoritative position results to a list; never turn failure into []."""
    if positions is None:
        raise TradingStateUnavailable("Binance position state unavailable")
    return list(positions)


def validate_order_request(symbol: str, side: str, quantity: float, price: Optional[float] = None,
                           min_qty: float = 0.0, max_qty: Optional[float] = None) -> tuple:
    """Validate an order before it reaches an exchange adapter."""
    symbol = str(symbol or "").upper()
    side = str(side or "").upper()
    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        raise InvalidOrderRequest("quantity must be numeric")
    try:
        min_qty = float(min_qty)
    except (TypeError, ValueError):
        raise InvalidOrderRequest("min_qty must be numeric")
    if max_qty is not None:
        try:
            max_qty = float(max_qty)
        except (TypeError, ValueError):
            raise InvalidOrderRequest("max_qty must be numeric")
    if not _SYMBOL_RE.fullmatch(symbol):
        raise InvalidOrderRequest("invalid symbol")
    if side not in {"BUY", "SELL"}:
        raise InvalidOrderRequest("side must be BUY or SELL")
    if not math.isfinite(quantity) or quantity <= 0:
        raise InvalidOrderRequest("quantity must be finite and greater than zero")
    if not math.isfinite(min_qty) or min_qty < 0:
        raise InvalidOrderRequest("min_qty must be finite and non-negative")
    if max_qty is not None and (not math.isfinite(max_qty) or max_qty <= 0):
        raise InvalidOrderRequest("max_qty must be finite and greater than zero")
    if max_qty is not None and max_qty < min_qty:
        raise InvalidOrderRequest("max_qty must be greater than or equal to min_qty")
    if min_qty > 0 and quantity < min_qty:
        raise InvalidOrderRequest("quantity is below exchange minimum")
    if max_qty is not None and quantity > max_qty:
        raise InvalidOrderRequest("quantity exceeds configured maximum")
    if price is not None:
        try:
            price = float(price)
        except (TypeError, ValueError):
            raise InvalidOrderRequest("price must be numeric")
        if not math.isfinite(price) or price <= 0:
            raise InvalidOrderRequest("price must be finite and greater than zero")
    return symbol, side, quantity, price


def make_client_order_id(symbol: str, side: str, intent: str, nonce: Optional[int] = None) -> str:
    """Create a bounded, Binance-compatible client order identifier."""
    symbol, side, _, _ = validate_order_request(symbol, side, 1.0)
    clean_intent = re.sub(r"[^A-Z0-9_-]", "", str(intent or "ENTRY").upper())[:12] or "ENTRY"
    suffix = str(int(time.time_ns() if nonce is None else nonce))[-16:]
    return f"ATLAS_{symbol}_{side}_{clean_intent}_{suffix}"[:36]


def find_order_by_client_id(orders: Iterable[dict], client_order_id: str) -> Optional[dict]:
    """Find an already-accepted order after an ambiguous network response."""
    target = str(client_order_id)
    for order in orders or []:
        if str(order.get("clientOrderId") or order.get("origClientOrderId") or "") == target:
            return order
    return None


def order_response_is_success(response: Any) -> bool:
    """Return True only for an exchange response containing a usable order id."""
    return isinstance(response, dict) and response.get("code") is None and response.get("orderId") is not None


def response_is_ambiguous(response: Any) -> bool:
    """Return True when a submission result cannot prove that an order was rejected."""
    if response is None:
        return True
    if isinstance(response, dict):
        if order_response_is_success(response):
            return False
        code = response.get("code")
        status = response.get("status") or response.get("http_status")
        if code in (-1001, -1006, -1007) or status in _RETRYABLE_HTTP:
            return True
        if "error" in response and _is_timeout_like(Exception(str(response.get("error", "")))):
            return True
    text = str(response).lower()
    return "timeout" in text or "connection" in text or "disconnected" in text


def should_reconcile_before_retry(response: Any) -> bool:
    """Require client-order-ID reconciliation before any retry of an ambiguous submit."""
    return response_is_ambiguous(response)


def protective_stop_key(order: dict) -> tuple:
    """Return the identity key used to enforce one SL per symbol/position side."""
    symbol = str(order.get("symbol", "")).upper()
    position_side = str(order.get("positionSide", "BOTH")).upper()
    return symbol, position_side


def protective_stop_matches(order: dict, symbol: str, position_side: str) -> bool:
    """Return True for an intended close-position STOP_MARKET protective order."""
    return (
        protective_stop_key(order) == (symbol.upper(), position_side.upper())
        and str(order.get("type") or order.get("orderType") or "").upper() == "STOP_MARKET"
        and order.get("closePosition") in (True, "true", "TRUE", 1, "1")
    )


def choose_authoritative_stop(orders: Iterable[dict], symbol: str, position_side: str) -> Optional[dict]:
    """Choose one deterministic protective STOP_MARKET order for a position side."""
    candidates = [o for o in orders if protective_stop_matches(o, symbol, position_side)]
    if not candidates:
        return None
    return max(candidates, key=lambda x: int(x.get("updateTime") or x.get("bookTime") or 0))


def exactly_one_protective_stop(orders: Iterable[dict], symbol: str, position_side: str) -> bool:
    """Return True only when exactly one intended close-position SL exists."""
    return sum(1 for o in orders if protective_stop_matches(o, symbol, position_side)) == 1


def protective_stop_count(orders: Iterable[dict], symbol: str, position_side: str) -> int:
    """Return the authoritative count of intended protective stops."""
    return sum(1 for o in orders if protective_stop_matches(o, symbol, position_side))


def income_event_key(event: dict) -> tuple:
    """Stable identity for a Binance income event to prevent double counting."""
    return (
        str(event.get("tranId") or event.get("id") or ""),
        str(event.get("time") or ""),
        str(event.get("symbol") or ""),
        str(event.get("incomeType") or ""),
        str(event.get("income") or ""),
    )


def is_realized_pnl_event(event: dict) -> bool:
    """Return True only for actual REALIZED_PNL income events."""
    return str(event.get("incomeType") or "").upper() == "REALIZED_PNL"
