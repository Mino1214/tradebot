"""
Worker: process pending webhook events.
1. Fetch latest closed kline / klines from Binance
2. Update candle store (optional; we use Binance as source of truth per run)
3. Compute indicators, evaluate strategy
4. Save signal to DB (and later: execute order if trade_enabled)
"""
import json
import logging
from sqlalchemy.orm import Session
from app.database import SessionLocal, init_db
from app.models import Event, Signal, Position
from app.services.binance_client import fetch_klines, fetch_latest_closed_kline
from app.services.indicators import compute_all
from app.services.strategy import evaluate, LONG_ENTRY, SHORT_ENTRY, LONG_EXIT, SHORT_EXIT
from app.services.params import get_active_params, DEFAULT_PARAMS
from app.services.execution import execute_entry, execute_exit
from app.services.telegram_notify import notify_signal
from app.services.adaptive_filter import (
    evaluate as filter_evaluate,
    get_adaptive_filter_state_from_db,
    update_adaptive_filter_state_after_exit,
    update_adaptive_filter_state_after_skip,
)
from app.services.admin_state import is_new_entry_allowed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_position_info(db: Session, symbol: str) -> tuple[str | None, float | None, float | None]:
    """(side, entry_price, stop_price) for symbol. (None, None, None) if flat."""
    row = db.query(Position).filter(Position.symbol == symbol).first()
    if not row or not row.size or float(row.size or 0) == 0:
        return None, None, None
    entry = float(row.entry_price) if row.entry_price is not None else None
    stop = float(row.stop_price) if row.stop_price is not None else None
    return row.side, entry, stop


def _bar_duration_ms(tf: str) -> int:
    """tf '4h' -> ms for one bar."""
    tf = (tf or "4h").lower()
    if tf.endswith("h"):
        h = int(tf.replace("h", "") or "1")
        return h * 3600 * 1000
    if tf.endswith("m"):
        m = int(tf.replace("m", "") or "1")
        return m * 60 * 1000
    return 4 * 3600 * 1000


def _in_cooldown(db: Session, symbol: str, current_close_time: int, tf: str, cooldown_bars: int) -> bool:
    """청산 후 cooldown_bars 이내면 True (진입 스킵)."""
    if cooldown_bars <= 0:
        return False
    last_exit = (
        db.query(Signal)
        .filter(Signal.symbol == symbol, Signal.action.in_([LONG_EXIT, SHORT_EXIT]))
        .order_by(Signal.close_time.desc())
        .first()
    )
    if not last_exit or last_exit.close_time is None:
        return False
    bar_ms = _bar_duration_ms(tf)
    # 현재 봉이 마지막 청산 봉으로부터 (1 + cooldown_bars) 봉 이내면 스킵
    return (current_close_time - int(last_exit.close_time)) < (1 + cooldown_bars) * bar_ms


def process_one_event(db: Session, event: Event) -> bool:
    """Process a single event: fetch klines, indicators, strategy, save signal. No order."""
    symbol = event.symbol
    tf = event.tf
    close_time = event.close_time
    params = get_active_params(db)
    ema_len = params.get("ema_len", DEFAULT_PARAMS["ema_len"])
    entry_len = params.get("entry_len", DEFAULT_PARAMS["entry_len"])
    exit_len = params.get("exit_len", DEFAULT_PARAMS["exit_len"])
    dmi_len = params.get("dmi_len", DEFAULT_PARAMS["dmi_len"])
    atr_len = params.get("atr_len", DEFAULT_PARAMS["atr_len"])
    adx_min = params.get("adx_min", DEFAULT_PARAMS["adx_min"])

    limit = max(200, ema_len, entry_len, exit_len, dmi_len, atr_len) + 10
    try:
        klines = fetch_klines(symbol, tf, limit=limit)
    except Exception as e:
        logger.exception("fetch_klines failed: %s", e)
        event.status = "failed"
        db.commit()
        return False

    if len(klines) < limit - 5:
        logger.warning("Not enough klines for %s %s: %d", symbol, tf, len(klines))
        event.status = "failed"
        db.commit()
        return False

    indicators = compute_all(
        klines,
        ema_len=ema_len,
        entry_len=entry_len,
        exit_len=exit_len,
        dmi_len=dmi_len,
        atr_len=atr_len,
    )
    position_side, entry_price, stop_price = get_position_info(db, symbol)
    adx_min = params.get("adx_min", DEFAULT_PARAMS["adx_min"])
    breakout_atr_margin = params.get("breakout_atr_margin", DEFAULT_PARAMS["breakout_atr_margin"])
    use_ema_slope = params.get("use_ema_slope", DEFAULT_PARAMS["use_ema_slope"])
    use_adx_rising = params.get("use_adx_rising", DEFAULT_PARAMS["use_adx_rising"])

    action = evaluate(
        indicators,
        position_side,
        entry_price=entry_price,
        stop_price=stop_price,
        adx_min=adx_min,
        breakout_atr_margin=breakout_atr_margin,
        use_ema_slope=use_ema_slope,
        use_adx_rising=use_adx_rising,
    )

    # 청산 후 cooldown_bars 이내면 같은 봉에서 진입 스킵은 이미 evaluate 순서로 처리됨; 다음 봉 진입 시 cooldown 체크
    cooldown_bars = params.get("cooldown_bars", DEFAULT_PARAMS["cooldown_bars"])
    skip_entry_cooldown = _in_cooldown(db, symbol, close_time, tf, cooldown_bars)

    # 관리자 레벨 신규 진입 게이트 (Emergency / New Entry OFF)
    admin_allow_entry = is_new_entry_allowed(db)

    # Adaptive Filter: 거래 여부·규모만 조절 (진입/청산 규칙은 그대로)
    last_3_pnls, skip_remaining = get_adaptive_filter_state_from_db(db)
    adx = indicators.get("ADX")
    atr_cur = indicators.get("ATR")
    atr_30 = indicators.get("ATR_30")
    filt = filter_evaluate(adx, atr_cur, atr_30, last_3_pnls, skip_remaining)

    params_with_filter = {**params, "filter_state": filt.state, "filter_reason_ko": filt.reason_ko}
    signal = Signal(
        close_time=close_time,
        action=action,
        indicators_snapshot=indicators,
        params_snapshot=params_with_filter,
        symbol=symbol,
        tf=tf,
    )
    db.add(signal)
    db.flush()
    event.status = "processed"
    db.commit()

    notify_signal(symbol, tf, action, close_time)

    if action == LONG_ENTRY and position_side is None and not skip_entry_cooldown and admin_allow_entry:
        if not filt.allowed:
            if filt.reason == "consecutive_loss_cooldown":
                update_adaptive_filter_state_after_skip(db)
                db.commit()
            logger.info("Adaptive filter: skip LONG entry [Filter State: %s] [사유: %s]", filt.state, filt.reason_ko)
        else:
            execute_entry(db, symbol, "LONG", indicators, params, position_multiplier=filt.multiplier, filter_state=filt.state, filter_reason_ko=filt.reason_ko)
    elif action == SHORT_ENTRY and position_side is None and not skip_entry_cooldown and admin_allow_entry:
        if not filt.allowed:
            if filt.reason == "consecutive_loss_cooldown":
                update_adaptive_filter_state_after_skip(db)
                db.commit()
            logger.info("Adaptive filter: skip SHORT entry [Filter State: %s] [사유: %s]", filt.state, filt.reason_ko)
        else:
            execute_entry(db, symbol, "SHORT", indicators, params, position_multiplier=filt.multiplier, filter_state=filt.state, filter_reason_ko=filt.reason_ko)
    elif action == LONG_EXIT:
        ok, pnl_pct = execute_exit(db, symbol, "LONG")
        if ok and pnl_pct is not None:
            update_adaptive_filter_state_after_exit(db, pnl_pct)
            db.commit()
    elif action == SHORT_EXIT:
        ok, pnl_pct = execute_exit(db, symbol, "SHORT")
        if ok and pnl_pct is not None:
            update_adaptive_filter_state_after_exit(db, pnl_pct)
            db.commit()

    logger.info("Event %s processed: symbol=%s tf=%s action=%s [Filter State: %s]", event.id, symbol, tf, action, filt.state)
    return True


def run_once():
    """Process one pending event from the queue."""
    init_db()
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.status == "pending").order_by(Event.id).first()
        if not event:
            return False
        return process_one_event(db, event)
    finally:
        db.close()


def run_worker(interval_seconds: float = 5.0):
    """Poll for pending events and process them."""
    import time
    while True:
        if run_once():
            continue
        time.sleep(interval_seconds)
