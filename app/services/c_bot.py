"""
C봇 v1.1 (중재봇). 주문 직접 하지 않음.
- regime 판정 (TREND/RANGE/NEUTRAL)
- active_strategy 선택 (A/B/NONE)
- trading_allowed 게이트, 스위칭 안정화(확정대기/히스테리시스/쿨다운)
- API로 상태/사유 제공
"""
import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.services.c_bot_indicators import compute_c_bot_indicators
from app.services.c_bot_thresholds import get_thresholds

REGIME_TREND = "TREND"
REGIME_RANGE = "RANGE"
REGIME_NEUTRAL = "NEUTRAL"
STRATEGY_A = "A"
STRATEGY_B = "B"
STRATEGY_NONE = "NONE"

# Risk gate 상수
DAILY_LOSS_LIMIT_PCT = -2.0
CONSECUTIVE_LOSS_LIMIT = 3
MAX_POSITIONS = 1

# blocked_reason 우선순위 (1이 최상)
BLOCK_REASONS = [
    "Emergency",
    "Daily loss limit hit",
    "Consecutive losses limit",
    "Position already open",
    "ATR too hot",
    "Cooldown",
    "NEUTRAL regime",
]

C_BOT_STATE_KEY = "c_bot_state"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _load_state(db: Session) -> dict:
    from app.models import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == C_BOT_STATE_KEY).first()
    if not row or not row.value:
        return {}
    try:
        raw = json.loads(row.value)
        return {
            "regime_current": raw.get("r"),
            "candidate_regime": raw.get("c"),
            "confirm_count": raw.get("n", 0),
            "cooldown_until": raw.get("u"),
            "active_strategy": raw.get("s"),
            "trading_allowed": raw.get("t", False),
            "blocked_reason": raw.get("b"),
            "emergency_mode": raw.get("e", False),
            "emergency_reason": raw.get("er"),
            "last_decision_time": raw.get("lt"),
        }
    except (json.JSONDecodeError, TypeError):
        return {}


def _save_state(db: Session, state: dict) -> None:
    from app.models import AppSetting
    b = (state.get("blocked_reason") or "")[:60]
    er = (state.get("emergency_reason") or "")[:60]
    raw = {
        "r": state.get("regime_current"),
        "c": state.get("candidate_regime"),
        "n": state.get("confirm_count", 0),
        "u": state.get("cooldown_until"),
        "s": state.get("active_strategy"),
        "t": state.get("trading_allowed", False),
        "b": b or None,
        "e": state.get("emergency_mode", False),
        "er": er or None,
        "lt": state.get("last_decision_time"),
    }
    val = json.dumps(raw)
    if len(val) > 256:
        val = val[:253] + "..."
    row = db.query(AppSetting).filter(AppSetting.key == C_BOT_STATE_KEY).first()
    if row:
        row.value = val
    else:
        db.add(AppSetting(key=C_BOT_STATE_KEY, value=val))
    db.flush()


def get_candidate_regime(indicators: dict, th: dict) -> str:
    """trend_ok / range_ok 판단 후 후보 반환."""
    adx = indicators.get("adx")
    ema_slope_pct = indicators.get("ema_slope_pct")
    atr_hot = indicators.get("atr_hot", False)

    if adx is None:
        return REGIME_NEUTRAL

    trend_enter = th.get("TREND_ENTER", 25)
    range_enter = th.get("RANGE_ENTER", 16)
    slope_min = th.get("slope_min", 0.05)
    slope_max = th.get("slope_max", 0.02)

    abs_slope = abs(ema_slope_pct) if ema_slope_pct is not None else 0

    trend_ok = (adx >= trend_enter) and (abs_slope >= slope_min) and (not atr_hot)
    range_ok = (adx <= range_enter) and (abs_slope <= slope_max) and (not atr_hot)

    if trend_ok:
        return REGIME_TREND
    if range_ok:
        return REGIME_RANGE
    return REGIME_NEUTRAL


def _bar_duration_ms(tf: str) -> int:
    tf = (tf or "4h").lower()
    if tf == "1h":
        return 3600 * 1000
    return 4 * 3600 * 1000


def evaluate(
    db: Session,
    tf: str,
    symbol: str,
    ohlcv: list[dict],
    now_candle_time: int,
    *,
    account_state: dict | None = None,
    bot_states: dict | None = None,
) -> dict:
    """
    on_candle_close 호출 시 실행.
    account_state: open_position_exists(bool), daily_pnl_pct(float), consecutive_losses(int)
    bot_states: A: { enabled, position_open, health }, B: { enabled, position_open, health }
    Returns: 스냅샷(regime_current, active_strategy, trading_allowed, blocked_reason, indicators, switch_state, risk, ...)
    """
    account_state = account_state or {}
    bot_states = bot_states or {}

    open_position_exists = account_state.get("open_position_exists", False)
    daily_pnl_pct = float(account_state.get("daily_pnl_pct", 0))
    consecutive_losses = int(account_state.get("consecutive_losses", 0))

    th = get_thresholds(symbol, tf)
    indicators = compute_c_bot_indicators(ohlcv)
    candidate = get_candidate_regime(indicators, th)
    atr_hot = indicators.get("atr_hot", False)

    state = _load_state(db)
    regime_current = state.get("regime_current", REGIME_NEUTRAL)
    prev_candidate = state.get("candidate_regime")
    confirm_count = state.get("confirm_count", 0)
    cooldown_until = state.get("cooldown_until")

    # 확정 대기: 동일 후보가 confirm_N번 연속이면 regime 전환
    if candidate == prev_candidate:
        confirm_count = confirm_count + 1
    else:
        confirm_count = 1

    confirm_N = th.get("confirm_N", 1)
    if confirm_count >= confirm_N and candidate != regime_current:
        regime_current = candidate
        bar_ms = _bar_duration_ms(tf)
        cooldown_M = th.get("cooldown_M_bars", 1)
        cooldown_until = now_candle_time + bar_ms * cooldown_M

    state["candidate_regime"] = candidate
    state["regime_current"] = regime_current
    state["confirm_count"] = confirm_count
    state["cooldown_until"] = cooldown_until

    # Strategy selector
    if regime_current == REGIME_TREND:
        active_strategy = STRATEGY_A
    elif regime_current == REGIME_RANGE:
        active_strategy = STRATEGY_B
    else:
        active_strategy = STRATEGY_NONE

    state["active_strategy"] = active_strategy

    # Emergency detection
    emergency_mode = False
    emergency_reason = ""
    bot_a = bot_states.get("A") or {}
    bot_b = bot_states.get("B") or {}
    if bot_a.get("health") == "error" or bot_b.get("health") == "error":
        emergency_mode = True
        emergency_reason = "Bot health error"

    # Risk Gate (우선순위대로 대표 1개)
    trading_allowed = True
    blocked_reason = ""

    if emergency_mode:
        trading_allowed = False
        blocked_reason = f"Emergency: {emergency_reason}"
    elif daily_pnl_pct <= DAILY_LOSS_LIMIT_PCT:
        trading_allowed = False
        blocked_reason = "Daily loss limit hit"
    elif consecutive_losses >= CONSECUTIVE_LOSS_LIMIT:
        trading_allowed = False
        blocked_reason = "Consecutive losses limit"
    elif open_position_exists and MAX_POSITIONS == 1:
        trading_allowed = False
        blocked_reason = "Position already open"
    elif atr_hot:
        trading_allowed = False
        blocked_reason = "ATR too hot"
    elif cooldown_until is not None and now_candle_time < cooldown_until:
        trading_allowed = False
        blocked_reason = "Cooldown"
    elif active_strategy == STRATEGY_NONE:
        trading_allowed = False
        blocked_reason = "NEUTRAL regime"

    state["trading_allowed"] = trading_allowed
    state["blocked_reason"] = blocked_reason
    state["emergency_mode"] = emergency_mode
    state["emergency_reason"] = emergency_reason
    state["last_decision_time"] = _now_ms()

    _save_state(db, state)

    return {
        "regime_current": regime_current,
        "candidate_regime": candidate,
        "active_strategy": active_strategy,
        "trading_allowed": trading_allowed,
        "blocked_reason": blocked_reason,
        "emergency_mode": emergency_mode,
        "emergency_reason": emergency_reason or None,
        "switch_state": {
            "confirm_count": confirm_count,
            "cooldown_until": cooldown_until,
        },
        "indicators": {
            "adx": indicators.get("adx"),
            "atr_pct": indicators.get("atr_pct"),
            "atr_pct_ma50": indicators.get("atr_pct_ma50"),
            "atr_hot": atr_hot,
            "ema_slope_pct": indicators.get("ema_slope_pct"),
        },
        "last_decision_time": state["last_decision_time"],
        "threshold_profile": th,
    }


def get_snapshot(db: Session) -> dict:
    """현재 C봇 상태 스냅샷 (API/관리자용). 저장된 state + 마지막 판정 결과."""
    state = _load_state(db)
    return {
        "regime_current": state.get("regime_current", REGIME_NEUTRAL),
        "candidate_regime": state.get("candidate_regime", REGIME_NEUTRAL),
        "active_strategy": state.get("active_strategy", STRATEGY_NONE),
        "trading_allowed": state.get("trading_allowed", False),
        "blocked_reason": state.get("blocked_reason") or "",
        "emergency_mode": state.get("emergency_mode", False),
        "emergency_reason": state.get("emergency_reason") or "",
        "switch_state": {
            "confirm_count": state.get("confirm_count", 0),
            "cooldown_until": state.get("cooldown_until"),
        },
        "last_decision_time": state.get("last_decision_time"),
    }
