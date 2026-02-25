"""
B봇 상태: 포지션, 로그, 리스크.
- 포지션/로그: 인메모리 (재시작 시 초기화). 추후 DB/테이블 연동 가능.
- 리스크: app_settings에 저장 가능.
"""
import json
import time
from typing import Any

from sqlalchemy.orm import Session

BOT_B_RISK_KEY = "bot_b_risk"
BOT_B_STATUS_KEY = "bot_b_status"  # RUNNING / PAUSED / NO-TRADE

# 인메모리 (단일 프로세스 기준)
_bot_b_position: dict | None = None
_bot_b_logs: list[dict] = []
_MAX_LOGS = 20


def _now_ms() -> int:
    return int(time.time() * 1000)


def append_log(log_type: str, msg: str) -> None:
    """Decision log 추가 (최근 20개 유지)."""
    global _bot_b_logs
    _bot_b_logs.append({"time": _now_ms(), "type": log_type, "msg": msg})
    _bot_b_logs = _bot_b_logs[-_MAX_LOGS:]


def get_logs() -> list[dict]:
    return list(_bot_b_logs)


def set_position(pos: dict | None) -> None:
    global _bot_b_position
    _bot_b_position = pos


def get_position() -> dict | None:
    return _bot_b_position


def get_risk_from_db(db: Session) -> dict:
    """app_settings에서 bot_b_risk 읽기. 없으면 기본값."""
    from app.models import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == BOT_B_RISK_KEY).first()
    if not row or not row.value:
        return {
            "dailyPnl": 0.0,
            "dailyLossLimit": -500.0,
            "consecutiveLosses": 0,
            "tradingAllowed": True,
            "tradeDisabledReason": None,
        }
    try:
        data = json.loads(row.value)
        return {
            "dailyPnl": float(data.get("d", 0)),
            "dailyLossLimit": float(data.get("l", -500)),
            "consecutiveLosses": int(data.get("c", 0)),
            "tradingAllowed": bool(data.get("a", True)),
            "tradeDisabledReason": data.get("r"),
        }
    except (json.JSONDecodeError, TypeError):
        return {
            "dailyPnl": 0.0,
            "dailyLossLimit": -500.0,
            "consecutiveLosses": 0,
            "tradingAllowed": True,
            "tradeDisabledReason": None,
        }


def get_status_from_db(db: Session) -> str:
    """RUNNING / PAUSED / NO-TRADE."""
    from app.models import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == BOT_B_STATUS_KEY).first()
    if not row or not row.value:
        return "RUNNING"
    v = (row.value or "").strip().upper()
    if v in ("RUNNING", "PAUSED", "NO-TRADE"):
        return v
    return "RUNNING"
