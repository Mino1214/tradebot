"""
Adaptive Filter Module — Test Mode
- 기존 진입/청산 규칙은 변경하지 않음.
- 거래 활성 여부와 포지션 크기(배율)만 조절.
- 모든 거래 로그에 [Filter State: OFF|WEAK|NORMAL|STRONG] 기록.
"""
import json
from dataclasses import dataclass
from typing import List

from sqlalchemy.orm import Session

# 4시간봉 기준 ADX 구간
STATE_OFF = "OFF"      # ADX < 18 → 진입 금지
STATE_WEAK = "WEAK"    # 18 ≤ ADX < 25 → 0.5배
STATE_NORMAL = "NORMAL"  # 25 ≤ ADX < 35 → 1.0배
STATE_STRONG = "STRONG"  # ADX ≥ 35 → 1.3배

# reason 코드 → 한글 (진입 시 로그/저장용)
REASON_KO = {
    "ok": "정상 진입",
    "adx_low": "ADX 낮음(18 미만, 진입 금지)",
    "atr_sideways": "변동성 축소(횡보, 진입 금지)",
    "consecutive_loss_cooldown": "연속 손실 보호(쿨다운 중)",
}


def reason_to_ko(reason: str) -> str:
    """필터 사유를 한글로 반환."""
    return REASON_KO.get(reason, reason)


@dataclass
class FilterResult:
    allowed: bool
    multiplier: float
    state: str
    reason: str

    @property
    def reason_ko(self) -> str:
        return reason_to_ko(self.reason)


def get_state_and_multiplier(adx: float | None) -> tuple[str, float]:
    """ADX만으로 상태와 포지션 배율 반환. 진입 허용 여부는 별도(변동성/연속손실)에서 판단."""
    if adx is None or adx < 18:
        return STATE_OFF, 0.0
    if adx < 25:
        return STATE_WEAK, 0.5
    if adx < 35:
        return STATE_NORMAL, 1.0
    return STATE_STRONG, 1.3


def evaluate(
    adx: float | None,
    atr_current: float | None,
    atr_30_avg: float | None,
    last_3_exit_pnl_pcts: List[float],
    skip_entries_remaining: int,
) -> FilterResult:
    """
    - 시장 상태: ADX 구간 → state, multiplier
    - 변동성: ATR < ATR30×0.7 → 신규 진입 금지
    - 연속 손실: 최근 3회 연속 손실 → 다음 2개 신호 동안 진입 금지
    """
    state, mult = get_state_and_multiplier(adx)

    # 1) ADX < 18 → 거래 비활성
    if state == STATE_OFF:
        return FilterResult(allowed=False, multiplier=0.0, state=STATE_OFF, reason="adx_low")

    # 2) 연속 손실 보호: 다음 2개 신호 스킵
    if skip_entries_remaining > 0:
        return FilterResult(allowed=False, multiplier=mult, state=state, reason="consecutive_loss_cooldown")

    # 3) 변동성 필터: 횡보 시 신규 진입 금지
    if atr_current is not None and atr_30_avg is not None and atr_30_avg > 0:
        if atr_current < atr_30_avg * 0.7:
            return FilterResult(allowed=False, multiplier=mult, state=state, reason="atr_sideways")

    return FilterResult(allowed=True, multiplier=mult, state=state, reason="ok")


def check_consecutive_losses(last_3_pnls: List[float]) -> bool:
    """최근 3회가 모두 손실이면 True."""
    if len(last_3_pnls) < 3:
        return False
    return all(p < 0 for p in last_3_pnls[-3:])


# ---------- DB-backed state for live worker (연속 손실 / 쿨다운) ----------
ADAPTIVE_FILTER_KEY = "adaptive_filter"


def get_adaptive_filter_state_from_db(db: Session) -> tuple[List[float], int]:
    """(last_3_exit_pnl_pcts, skip_entries_remaining)."""
    from app.models import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == ADAPTIVE_FILTER_KEY).first()
    if not row or not row.value:
        return [], 0
    try:
        data = json.loads(row.value)
        p = data.get("p") or []
        s = int(data.get("s") or 0)
        return (p[-3:] if isinstance(p, list) else [], max(0, s))
    except (json.JSONDecodeError, TypeError):
        return [], 0


def update_adaptive_filter_state_after_exit(db: Session, pnl_pct: float) -> None:
    """청산 후 PnL 반영, 연속 3회 손실이면 skip_remaining=2 설정."""
    from app.models import AppSetting
    pnls, skip = get_adaptive_filter_state_from_db(db)
    pnls = (pnls + [pnl_pct])[-3:]
    if check_consecutive_losses(pnls):
        skip = 2
    row = db.query(AppSetting).filter(AppSetting.key == ADAPTIVE_FILTER_KEY).first()
    val = json.dumps({"p": pnls, "s": skip})
    if row:
        row.value = val
    else:
        db.add(AppSetting(key=ADAPTIVE_FILTER_KEY, value=val))
    db.flush()


def update_adaptive_filter_state_after_skip(db: Session) -> None:
    """진입 스킵 시(연속손실 쿨다운) skip 카운트 1 감소."""
    from app.models import AppSetting
    pnls, skip = get_adaptive_filter_state_from_db(db)
    skip = max(0, skip - 1)
    row = db.query(AppSetting).filter(AppSetting.key == ADAPTIVE_FILTER_KEY).first()
    val = json.dumps({"p": pnls, "s": skip})
    if row:
        row.value = val
    else:
        db.add(AppSetting(key=ADAPTIVE_FILTER_KEY, value=val))
    db.flush()
