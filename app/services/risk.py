"""
Risk-based quantity and Binance filter compliance.
qty = riskCash / stopDistance, then floor to stepSize; ensure qty * markPrice >= minNotional.
"""
import math
from app.services.binance_client import get_symbol_filters


def round_down_step(value: float, step: float) -> float:
    """Round value down to step (e.g. stepSize)."""
    if step <= 0:
        return value
    precision = 0
    s = str(step)
    if "." in s:
        precision = len(s.rstrip("0").split(".")[1])
    factor = 1.0 / step
    return math.floor(value * factor) / factor


def round_price(value: float, tick: float) -> float:
    """Round price to tick size."""
    if tick <= 0:
        return value
    precision = 0
    s = str(tick)
    if "." in s:
        precision = len(s.rstrip("0").split(".")[1])
    factor = 1.0 / tick
    return round(value * factor) / factor


def compute_quantity(
    symbol: str,
    equity_usdt: float,
    loss_pct: float,
    atr: float,
    atr_mult: float,
    mark_price: float,
) -> float | None:
    """
    riskCash = equity_usdt * loss_pct
    stopDistance = atr_mult * atr
    qty = riskCash / stopDistance
    Then apply stepSize floor and minNotional check.
    """
    if atr <= 0 or mark_price <= 0:
        return None
    risk_cash = equity_usdt * loss_pct
    stop_distance = atr_mult * atr
    if stop_distance <= 0:
        return None
    qty = risk_cash / stop_distance
    filters = get_symbol_filters(symbol)
    step = filters["stepSize"]
    min_notional = filters["minNotional"]
    qty = round_down_step(qty, step)
    if qty <= 0:
        return None
    notional = qty * mark_price
    if min_notional and notional < min_notional:
        return None
    return qty
