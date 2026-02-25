"""
Strategy: bar-close breakout.
- 처리 순서 고정: 1) 스탑 체결 2) 청산 신호 3) 진입 신호
- Donchian은 직전 N봉(현재봉 제외), 진입 품질 필터 3개 적용.
"""
from typing import Any

# Action constants
LONG_ENTRY = "LONG_ENTRY"
SHORT_ENTRY = "SHORT_ENTRY"
LONG_EXIT = "LONG_EXIT"
SHORT_EXIT = "SHORT_EXIT"
NONE = "NONE"


def evaluate(
    indicators: dict,
    position_side: str | None,
    entry_price: float | None = None,
    stop_price: float | None = None,
    *,
    adx_min: float = 20,
    breakout_atr_margin: float = 0.2,
    use_ema_slope: bool = True,
    use_adx_rising: bool = True,
) -> str:
    """
    봉 마감 시점 처리 순서: 1) 스탑 2) 청산 3) 진입.
    - 스탑: 봉 중 low/high로 체결 여부 판단 (롱: low <= stopPrice, 숏: high >= stopPrice).
    - 청산: 직전 N봉 기준 loExit/hiExit (현재봉 제외).
    - 진입: 직전 N봉 기준 hiEntry/loEntry + 돌파폭 + EMA기울기 + ADX상승.
    """
    close = indicators.get("close")
    high = indicators.get("high")
    low = indicators.get("low")
    ema200 = indicators.get("ema200")
    ema200_prev = indicators.get("ema200_prev")
    hi_entry = indicators.get("hiEntry")
    lo_entry = indicators.get("loEntry")
    hi_exit = indicators.get("hiExit")
    lo_exit = indicators.get("loExit")
    adx = indicators.get("ADX")
    adx_prev = indicators.get("ADX_prev")
    plus_di = indicators.get("plusDI")
    minus_di = indicators.get("minusDI")
    atr_val = indicators.get("ATR")

    if close is None or ema200 is None or hi_entry is None or lo_exit is None:
        return NONE
    if adx is None or plus_di is None or minus_di is None:
        return NONE
    if high is None or low is None:
        high, low = close, close

    # ---------- 1) 스탑 체결 여부 (봉 중 저가/고가로 판단) ----------
    if position_side == "LONG" and stop_price is not None and low <= stop_price:
        return LONG_EXIT  # 스탑 체결 → 청산 처리와 동일
    if position_side == "SHORT" and stop_price is not None and high >= stop_price:
        return SHORT_EXIT

    # ---------- 2) 청산 신호 (직전 N봉 채널, 현재봉 제외) ----------
    if position_side == "LONG":
        if close < (lo_exit or 0):
            return LONG_EXIT
        return NONE
    if position_side == "SHORT":
        if close > (hi_exit or float("inf")):
            return SHORT_EXIT
        return NONE

    # ---------- 3) 진입 신호 (포지션 없을 때만) ----------
    if adx < adx_min:
        return NONE
    if atr_val is None or atr_val <= 0:
        return NONE

    # A) 돌파 후 확인: 종가 > hiEntry + margin*ATR (롱), 종가 < loEntry - margin*ATR (숏)
    margin = breakout_atr_margin * atr_val
    if use_adx_rising and adx_prev is not None and adx <= adx_prev:
        return NONE  # ADX 상승 중일 때만

    # LONG: close > hiEntry + margin, close > EMA200, +DI > -DI, EMA200 기울기 상승
    ema_slope_ok_long = (not use_ema_slope) or (ema200_prev is not None and ema200 > ema200_prev)
    if (
        close > hi_entry + margin
        and close > ema200
        and plus_di > minus_di
        and ema_slope_ok_long
    ):
        return LONG_ENTRY

    # SHORT: close < loEntry - margin, close < EMA200, -DI > +DI, EMA200 기울기 하락
    ema_slope_ok_short = (not use_ema_slope) or (ema200_prev is not None and ema200 < ema200_prev)
    if (
        lo_entry is not None
        and close < lo_entry - margin
        and close < ema200
        and minus_di > plus_di
        and ema_slope_ok_short
    ):
        return SHORT_ENTRY

    return NONE
