"""Default and active params from DB."""
from typing import Any

DEFAULT_PARAMS = {
    "ema_len": 200,
    "entry_len": 20,
    "exit_len": 10,  # 청산 채널 짧게 (이익 반납 감소)
    "dmi_len": 14,
    "atr_len": 14,
    "adx_min": 20,
    "loss_pct": 0.01,
    "atr_mult": 2.0,
    "stop_mult": 2.0,
    "leverage": 5,
    "breakout_atr_margin": 0.2,  # 돌파 확인: hiEntry + margin*ATR
    "use_ema_slope": True,
    "use_adx_rising": True,
    "cooldown_bars": 0,  # 청산 후 N봉 대기 후 재진입 (0=없음, 1 추천)
}


def get_active_params(db) -> dict[str, Any]:
    """Return active param set from DB, or DEFAULT_PARAMS if none."""
    from app.models import ParamSet
    row = db.query(ParamSet).filter(ParamSet.active == True).first()
    if row and row.json:
        return {**DEFAULT_PARAMS, **row.json}
    return dict(DEFAULT_PARAMS)
