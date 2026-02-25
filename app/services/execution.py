"""
Order execution: MARKET entry, MARKET reduceOnly exit.
Uses trade_enabled; applies Binance filters and risk-based quantity.
"""
import logging
import time
from sqlalchemy.orm import Session
from app.config import get_settings
from app.services.trade_switch import get_trade_enabled
from app.models import Order, Position
from app.services.binance_client import (
    get_account,
    get_position_risk,
    get_mark_price,
    set_leverage,
    set_margin_type,
    create_order,
)
from app.services.risk import compute_quantity, round_price
from app.services.binance_client import get_symbol_filters
from app.services.telegram_notify import notify_order

logger = logging.getLogger(__name__)


def _equity_usdt(account: dict) -> float:
    for b in account.get("assets", []):
        if b.get("asset") == "USDT":
            return float(b.get("totalWalletBalance", 0) or 0)
    return 0.0


def _ensure_margin_and_leverage(symbol: str, leverage: int) -> None:
    try:
        set_margin_type(symbol, "ISOLATED")
    except Exception as e:
        if "No need to change" not in str(e):
            logger.warning("set_margin_type: %s", e)
    try:
        set_leverage(symbol, leverage)
    except Exception as e:
        logger.warning("set_leverage: %s", e)


def execute_entry(
    db: Session,
    symbol: str,
    side: str,
    indicators: dict,
    params: dict,
    *,
    position_multiplier: float = 1.0,
    filter_state: str = "NORMAL",
    filter_reason_ko: str = "정상 진입",
) -> bool:
    """Execute MARKET entry (BUY for LONG, SELL for SHORT). Returns True if order sent.
    position_multiplier: Adaptive Filter 배율 (0.5 / 1.0 / 1.3).
    filter_reason_ko: 진입 사유 한글 (로그/기록용)."""
    if not get_trade_enabled():
        logger.info("Trade disabled; skip entry %s %s", symbol, side)
        return False
    if not get_settings().binance_api_secret:
        logger.warning("No BINANCE_API_SECRET; skip entry")
        return False

    atr_val = indicators.get("ATR")
    if not atr_val:
        logger.warning("No ATR for entry")
        return False
    equity = _equity_usdt(get_account())
    if equity <= 0:
        logger.warning("Zero equity")
        return False
    mark = get_mark_price(symbol)
    loss_pct = params.get("loss_pct", 0.01)
    atr_mult = params.get("atr_mult", 2.0)
    leverage = int(params.get("leverage", 5))

    qty = compute_quantity(symbol, equity, loss_pct, atr_val, atr_mult, mark)
    if not qty or qty <= 0:
        logger.warning("Computed qty invalid: %s", qty)
        return False
    qty = qty * position_multiplier
    if qty <= 0:
        logger.warning("Position multiplier zero or negative; skip entry")
        return False

    _ensure_margin_and_leverage(symbol, leverage)
    order_side = "BUY" if side == "LONG" else "SELL"
    try:
        res = create_order(symbol, order_side, "MARKET", quantity=qty)
    except Exception as e:
        logger.exception("create_order entry failed: %s", e)
        return False

    order_id = res.get("orderId")
    order_id_int = int(order_id) if order_id is not None else None
    status = res.get("status", "")
    avg_price = float(res.get("avgPrice", 0) or res.get("price", 0) or mark)
    executed_qty = float(res.get("executedQty", 0) or qty)

    db.add(Order(order_id=order_id_int, type="MARKET", side=order_side, qty=executed_qty, price=avg_price, status=status, raw=res, symbol=symbol))

    stop_mult = params.get("stop_mult", 2.0)
    atr_val = indicators.get("ATR") or 0
    if side == "LONG":
        stop_price_val = avg_price - stop_mult * atr_val
    else:
        stop_price_val = avg_price + stop_mult * atr_val

    pos = db.query(Position).filter(Position.symbol == symbol).first()
    now_ms = int(time.time() * 1000)
    if pos:
        pos.side = side
        pos.size = executed_qty
        pos.entry_price = avg_price
        pos.stop_price = stop_price_val
        pos.updated_at = now_ms
    else:
        db.add(Position(symbol=symbol, side=side, size=executed_qty, entry_price=avg_price, stop_price=stop_price_val, updated_at=now_ms))
    db.commit()
    notify_order(symbol, side, "MARKET", executed_qty, avg_price, str(order_id or ""))
    _place_stop_order(symbol, side, executed_qty, avg_price, indicators, params)
    logger.info("Entry filled: %s %s qty=%s avg=%s orderId=%s [Filter State: %s] [진입 사유: %s]", symbol, side, executed_qty, avg_price, order_id, filter_state, filter_reason_ko)
    return True


def execute_exit(db: Session, symbol: str, side: str) -> tuple[bool, float | None]:
    """Execute MARKET reduceOnly exit. Position size from Binance. Returns (success, pnl_pct for adaptive filter)."""
    if not get_trade_enabled():
        logger.info("Trade disabled; skip exit %s %s", symbol, side)
        return False, None
    if not get_settings().binance_api_secret:
        return False, None

    positions = get_position_risk(symbol)
    pos_amt = 0.0
    entry_price_from_binance = None
    for p in positions:
        if p.get("symbol") != symbol:
            continue
        amt = float(p.get("positionAmt", 0) or 0)
        if side == "LONG" and amt > 0:
            pos_amt = amt
            entry_price_from_binance = float(p.get("entryPrice", 0) or 0)
            break
        if side == "SHORT" and amt < 0:
            pos_amt = abs(amt)
            entry_price_from_binance = float(p.get("entryPrice", 0) or 0)
            break
    if pos_amt <= 0:
        logger.info("No position to exit %s %s", symbol, side)
        _clear_position_db(db, symbol)
        return True, None

    pos_row = db.query(Position).filter(Position.symbol == symbol).first()
    entry_price = float(pos_row.entry_price) if pos_row and pos_row.entry_price is not None else entry_price_from_binance or 0.0

    order_side = "SELL" if side == "LONG" else "BUY"
    try:
        res = create_order(symbol, order_side, "MARKET", quantity=pos_amt, reduce_only=True)
    except Exception as e:
        logger.exception("create_order exit failed: %s", e)
        return False, None

    order_id = res.get("orderId")
    order_id_int = int(order_id) if order_id is not None else None
    status = res.get("status", "")
    exit_avg = float(res.get("avgPrice", 0) or res.get("price", 0) or 0)
    db.add(Order(order_id=order_id_int, type="MARKET", side=order_side, qty=pos_amt, price=None, status=status, raw=res, symbol=symbol))
    _clear_position_db(db, symbol)
    db.commit()
    notify_order(symbol, side, "MARKET", pos_amt, 0, str(order_id or ""))
    pnl_pct = None
    if entry_price and exit_avg:
        if side == "LONG":
            pnl_pct = (exit_avg - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_avg) / entry_price * 100
    logger.info("Exit filled: %s %s qty=%s orderId=%s [Filter State: logged at entry]", symbol, side, pos_amt, order_id)
    return True, pnl_pct


def _place_stop_order(
    symbol: str,
    side: str,
    quantity: float,
    entry_avg: float,
    indicators: dict,
    params: dict,
) -> None:
    """Place STOP_MARKET reduceOnly stop-loss after entry."""
    atr_val = indicators.get("ATR")
    stop_mult = params.get("stop_mult", 2.0)
    if not atr_val or atr_val <= 0:
        logger.warning("No ATR for stop order")
        return
    if side == "LONG":
        stop_price = entry_avg - stop_mult * atr_val
    else:
        stop_price = entry_avg + stop_mult * atr_val
    filters = get_symbol_filters(symbol)
    stop_price = round_price(stop_price, filters["tickSize"])
    order_side = "SELL" if side == "LONG" else "BUY"
    try:
        res = create_order(
            symbol,
            order_side,
            "STOP_MARKET",
            quantity=quantity,
            stop_price=stop_price,
            reduce_only=True,
        )
        logger.info("Stop order placed: %s %s stopPrice=%s orderId=%s", symbol, side, stop_price, res.get("orderId"))
    except Exception as e:
        logger.exception("Stop order failed: %s", e)


def _clear_position_db(db: Session, symbol: str) -> None:
    row = db.query(Position).filter(Position.symbol == symbol).first()
    if row:
        row.size = 0
        row.entry_price = 0
        row.stop_price = None
        row.updated_at = int(time.time() * 1000)
