"""
B봇(평균회귀) 전략: RANGE 구간에서만 진입.
- 진입: ADX < threshold, 가격이 BB 밖, RSI 과매도/과매수, 리엔트리/쿨다운/리스크 OK.
- 청산: TP(mid-band), SL(entry ± k*ATR), 타임아웃.
"""
from dataclasses import dataclass, field
from typing import Any

# Regime (중재봇에서 받을 수 있음; 당장은 ADX로 판단)
REGIME_RANGE = "RANGE"
REGIME_NEUTRAL = "NEUTRAL"
REGIME_TREND = "TREND"


@dataclass
class SignalChecks:
    adx_ok: bool
    price_outside_bb: bool
    rsi_ok: bool
    reentry_confirmed: bool
    cooldown_ok: bool
    risk_ok: bool


def get_regime_from_adx(adx: float | None, adx_range_max: float) -> str:
    """ADX만으로 단순 판단. 중재봇 연동 시 여기서 regime을 외부값으로 대체 가능."""
    if adx is None:
        return REGIME_NEUTRAL
    if adx < adx_range_max:
        return REGIME_RANGE
    if adx < 25:
        return REGIME_NEUTRAL
    return REGIME_TREND


def evaluate_long_checks(
    indicators: dict,
    *,
    adx_range_max: float = 16,
    rsi_long_max: float = 30,
    atr_pct_hot_limit: float = 3.0,
    cooldown_remaining_bars: int = 0,
    trading_allowed: bool = True,
    reentry_confirmed: bool = True,
) -> SignalChecks:
    """롱 진입 조건 체크."""
    adx = indicators.get("adx")
    bb = indicators.get("bb") or {}
    bb_zone = indicators.get("bbZone", "inside")
    rsi_val = indicators.get("rsi")
    atr_pct = indicators.get("atrPct")

    adx_ok = adx is not None and adx < adx_range_max
    price_outside_bb = bb_zone == "below_lower"
    rsi_ok = rsi_val is not None and rsi_val < rsi_long_max
    atr_too_hot = atr_pct is not None and atr_pct >= atr_pct_hot_limit
    risk_ok = trading_allowed and cooldown_remaining_bars <= 0 and not atr_too_hot

    return SignalChecks(
        adx_ok=adx_ok,
        price_outside_bb=price_outside_bb,
        rsi_ok=rsi_ok,
        reentry_confirmed=reentry_confirmed,
        cooldown_ok=cooldown_remaining_bars <= 0,
        risk_ok=risk_ok,
    )


def evaluate_short_checks(
    indicators: dict,
    *,
    adx_range_max: float = 16,
    rsi_short_min: float = 70,
    atr_pct_hot_limit: float = 3.0,
    cooldown_remaining_bars: int = 0,
    trading_allowed: bool = True,
    reentry_confirmed: bool = True,
) -> SignalChecks:
    """숏 진입 조건 체크."""
    adx = indicators.get("adx")
    bb_zone = indicators.get("bbZone", "inside")
    rsi_val = indicators.get("rsi")
    atr_pct = indicators.get("atrPct")

    adx_ok = adx is not None and adx < adx_range_max
    price_outside_bb = bb_zone == "above_upper"
    rsi_ok = rsi_val is not None and rsi_val > rsi_short_min
    atr_too_hot = atr_pct is not None and atr_pct >= atr_pct_hot_limit
    risk_ok = trading_allowed and cooldown_remaining_bars <= 0 and not atr_too_hot

    return SignalChecks(
        adx_ok=adx_ok,
        price_outside_bb=price_outside_bb,
        rsi_ok=rsi_ok,
        reentry_confirmed=reentry_confirmed,
        cooldown_ok=cooldown_remaining_bars <= 0,
        risk_ok=risk_ok,
    )


def signal_ready(checks: SignalChecks) -> bool:
    return (
        checks.adx_ok
        and checks.price_outside_bb
        and checks.rsi_ok
        and checks.reentry_confirmed
        and checks.cooldown_ok
        and checks.risk_ok
    )


def checks_to_dict(c: SignalChecks) -> dict[str, bool]:
    return {
        "adx_ok": c.adx_ok,
        "price_outside_bb": c.price_outside_bb,
        "rsi_ok": c.rsi_ok,
        "reentry_confirmed": c.reentry_confirmed,
        "cooldown_ok": c.cooldown_ok,
        "risk_ok": c.risk_ok,
    }


def signal_score(checks: SignalChecks) -> int:
    """0~100. 조건 충족 개수 기반."""
    d = checks_to_dict(checks)
    n = sum(1 for v in d.values() if v)
    return min(100, int((n / 6) * 100)) if d else 0
