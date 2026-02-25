"""
Unified admin state builder for ETH 단일 자동매매(보수형) 관리자페이지.
하나의 API에서 controls / meta(C봇) / botA / botB / position / bot_opinions 구조를 반환한다.
"""
from typing import Any

from sqlalchemy.orm import Session

from app.models import Position, AppSetting
from app.services.trade_switch import get_trade_enabled, set_trade_enabled
from app.services.c_bot import get_snapshot as get_c_bot_snapshot
from app.services.c_bot_indicators import compute_c_bot_indicators
from app.services.binance_client import fetch_klines


ADMIN_MODE_KEY = "admin_mode"
ADMIN_NEW_ENTRY_KEY = "admin_new_entry_enabled"
ADMIN_EMERGENCY_KEY = "admin_emergency_stop"
ADMIN_LEVERAGE_KEY = "admin_leverage"
ADMIN_RISK_KEY = "admin_risk"
ADMIN_LAST_CONTROL_KEY = "admin_last_control_action"
ADMIN_OVERRIDE_REASON_KEY = "admin_manual_override_reason"


def _get_setting(db: Session, key: str) -> str | None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value is not None else None


def _set_setting(db: Session, key: str, value: str | None) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if value is None:
        if row:
            row.value = None
    else:
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
    db.flush()


def _get_bool(db: Session, key: str, default: bool = False) -> bool:
    v = _get_setting(db, key)
    if v is None:
        return default
    return v.lower() in ("true", "1", "yes", "on")


def _get_controls(db: Session) -> dict[str, Any]:
    """controls: mode, run_state, new_entry_enabled, emergency_stop, leverage_setting, risk_setting, last_control_action, manual_override_reason"""
    mode = _get_setting(db, ADMIN_MODE_KEY) or "PAPER"
    run_state = "RUNNING" if get_trade_enabled() else "PAUSED"
    new_entry_enabled = _get_bool(db, ADMIN_NEW_ENTRY_KEY, default=True)
    emergency_stop = _get_bool(db, ADMIN_EMERGENCY_KEY, default=False)
    leverage_setting = _get_setting(db, ADMIN_LEVERAGE_KEY)
    risk_setting = _get_setting(db, ADMIN_RISK_KEY)
    last_control_action = _get_setting(db, ADMIN_LAST_CONTROL_KEY)
    manual_override_reason = _get_setting(db, ADMIN_OVERRIDE_REASON_KEY)
    return {
        "mode": mode,
        "run_state": run_state,
        "new_entry_enabled": new_entry_enabled,
        "emergency_stop": emergency_stop,
        "leverage_setting": leverage_setting,
        "risk_setting": risk_setting,
        "last_control_action": last_control_action,
        "manual_override_reason": manual_override_reason,
    }


def is_new_entry_allowed(db: Session) -> bool:
    """
    관리자 레벨에서 신규 진입 허용 여부.
    - Emergency ON이면 false
    - New Entry OFF이면 false
    - 그 외에는 true
    """
    if _get_bool(db, ADMIN_EMERGENCY_KEY, False):
        return False
    if not _get_bool(db, ADMIN_NEW_ENTRY_KEY, True):
        return False
    return True


def set_run_state(db: Session, running: bool, reason: str | None = None) -> None:
    """RUNNING/PAUSED 제어 (trade_enabled 사용)."""
    set_trade_enabled(running)
    text = f"Run={'RUNNING' if running else 'PAUSED'}"
    if reason:
        text += f" ({reason})"
        _set_setting(db, ADMIN_OVERRIDE_REASON_KEY, reason)
    _set_setting(db, ADMIN_LAST_CONTROL_KEY, text)


def set_new_entry(db: Session, enabled: bool, reason: str | None = None) -> None:
    _set_setting(db, ADMIN_NEW_ENTRY_KEY, "true" if enabled else "false")
    text = f"NewEntry={'ON' if enabled else 'OFF'}"
    if reason:
        text += f" ({reason})"
        _set_setting(db, ADMIN_OVERRIDE_REASON_KEY, reason)
    _set_setting(db, ADMIN_LAST_CONTROL_KEY, text)


def set_emergency(db: Session, active: bool, reason: str | None = None) -> None:
    _set_setting(db, ADMIN_EMERGENCY_KEY, "true" if active else "false")
    text = f"Emergency={'ON' if active else 'OFF'}"
    if reason:
        text += f" ({reason})"
        _set_setting(db, ADMIN_OVERRIDE_REASON_KEY, reason)
    _set_setting(db, ADMIN_LAST_CONTROL_KEY, text)


def set_mode(db: Session, mode: str, reason: str | None = None) -> None:
    _set_setting(db, ADMIN_MODE_KEY, mode)
    text = f"Mode={mode}"
    if reason:
        text += f" ({reason})"
        _set_setting(db, ADMIN_OVERRIDE_REASON_KEY, reason)
    _set_setting(db, ADMIN_LAST_CONTROL_KEY, text)


def set_leverage(db: Session, leverage: str, reason: str | None = None) -> None:
    _set_setting(db, ADMIN_LEVERAGE_KEY, leverage)
    text = f"Leverage={leverage}"
    if reason:
        text += f" ({reason})"
        _set_setting(db, ADMIN_OVERRIDE_REASON_KEY, reason)
    _set_setting(db, ADMIN_LAST_CONTROL_KEY, text)


def set_risk_text(db: Session, risk_text: str, reason: str | None = None) -> None:
    _set_setting(db, ADMIN_RISK_KEY, risk_text)
    text = f"RiskSetting={risk_text}"
    if reason:
        text += f" ({reason})"
        _set_setting(db, ADMIN_OVERRIDE_REASON_KEY, reason)
    _set_setting(db, ADMIN_LAST_CONTROL_KEY, text)


def _get_meta(db: Session) -> dict[str, Any]:
    """meta(C봇): regime, candidate_regime, active_strategy, trading_allowed, blocked_reason, confirm_count, cooldown_until, emergency_mode/reason, indicators, risk"""
    snapshot = get_c_bot_snapshot(db)
    regime = snapshot.get("regime_current")
    candidate_regime = snapshot.get("candidate_regime")
    active_strategy = snapshot.get("active_strategy")
    trading_allowed = snapshot.get("trading_allowed", False)
    blocked_reason = snapshot.get("blocked_reason")
    switch_state = snapshot.get("switch_state") or {}
    confirm_count = switch_state.get("confirm_count", 0)
    cooldown_until = switch_state.get("cooldown_until")
    emergency_mode = snapshot.get("emergency_mode", False)
    emergency_reason = snapshot.get("emergency_reason")

    # indicators: 4H 기준 최신 캔들에서 계산 (데이터 부족/오류 시 None)
    indicators: dict[str, Any] = {
        "adx": None,
        "atr_pct": None,
        "ema_slope_pct": None,
        "atr_hot": None,
    }
    try:
        klines = fetch_klines("ETHUSDT", "4h", limit=200)
        if klines:
            c_inds = compute_c_bot_indicators(klines)
            indicators = {
                "adx": c_inds.get("adx"),
                "atr_pct": c_inds.get("atr_pct"),
                "ema_slope_pct": c_inds.get("ema_slope_pct"),
                "atr_hot": c_inds.get("atr_hot"),
            }
    except Exception:
        # 지표 계산 실패 시 indicators는 None 필드 유지
        pass

    # risk: 아직 별도 집계가 없으므로 기본값 + 포지션 존재 여부만 반영
    open_position_exists = (
        db.query(Position)
        .filter(Position.symbol == "ETHUSDT", Position.size > 0)
        .first()
        is not None
    )
    risk = {
        "daily_pnl_pct": 0.0,
        "consecutive_losses": 0,
        "open_position_exists": open_position_exists,
    }

    return {
        "regime": regime,
        "candidate_regime": candidate_regime,
        "active_strategy": active_strategy,
        "trading_allowed": trading_allowed,
        "blocked_reason": blocked_reason,
        "confirm_count": confirm_count,
        "cooldown_until": cooldown_until,
        "emergency_mode": emergency_mode,
        "emergency_reason": emergency_reason,
        "indicators": indicators,
        "risk": risk,
    }


def _get_bot_a_state() -> dict[str, Any]:
    """botA 상태는 아직 구조화된 런타임 정보가 없으므로 최소 필드만 채우고 나머지는 정보 없음."""
    return {
        "enabled": True,
        "allow_entry": None,
        "signal": None,
        "signal_ready": None,
        "signal_reason": None,
        "indicators": None,
        "health": "unknown",
        "error_message": None,
        "last_action": None,
    }


def _get_bot_b_state() -> dict[str, Any]:
    """botB 상태도 최소 필드만. 상세 checks/indicators는 B봇 대시보드에서 별도 확인."""
    return {
        "enabled": True,
        "allow_entry": None,
        "signal": None,
        "signal_ready": None,
        "blocked_reason": None,
        "checks": None,
        "indicators": None,
        "last_action": None,
    }


def _get_position(db: Session) -> dict[str, Any] | None:
    pos = (
        db.query(Position)
        .filter(Position.symbol == "ETHUSDT", Position.size > 0)
        .first()
    )
    if not pos:
        return None
    # owner_bot/entry_context/management_policy 등은 아직 별도 저장이 없으므로 정보 없음 처리
    return {
        "side": pos.side,
        "size": float(pos.size),
        "leverage": None,
        "entry": float(pos.entry_price),
        "mark": None,
        "upnl": None,
        "sl": float(pos.stop_price) if pos.stop_price is not None else None,
        "tp": None,
        "owner_bot": None,
        "entry_context": None,
        "management_policy": None,
        "bars_in_trade": None,
        "timeout_bars_left": None,
    }


def get_unified_admin_state(db: Session) -> dict[str, Any]:
    """controls / meta / botA / botB / position / bot_opinions 구조 반환."""
    controls = _get_controls(db)
    meta = _get_meta(db)
    bot_a = _get_bot_a_state()
    bot_b = _get_bot_b_state()
    position = _get_position(db)
    bot_opinions = None
    return {
        "controls": controls,
        "meta": meta,
        "botA": bot_a,
        "botB": bot_b,
        "position": position,
        "bot_opinions": bot_opinions,
    }

