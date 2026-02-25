"""
C봇 v1.1 전용 지표 (고정 정의).
- ADX(14)
- EMA50 slope 정규화: ema_slope_pct = (EMA50_now - EMA50_prev) / Close_now * 100
- ATR%: atr_pct, atr_pct_ma50, atr_hot = atr_pct > atr_pct_ma50 * 1.5
"""
from app.services.indicators import (
    dmi_adx,
    atr,
    _ema_series,
    sma,
)


def compute_c_bot_indicators(candles: list[dict], *, adx_len: int = 14, ema_len: int = 50, atr_len: int = 14, atr_pct_ma_len: int = 50, atr_hot_mult: float = 1.5) -> dict:
    """
    마지막 종료된 봉 기준.
    Returns: adx, close, ema50_now, ema50_prev, ema_slope_pct,
             atr, atr_pct, atr_pct_ma50, atr_hot.
    """
    if not candles or len(candles) < max(ema_len, adx_len + 14, atr_len + 1, atr_pct_ma_len + atr_len):
        return {}

    closes = [float(c["c"]) for c in candles]
    last_close = closes[-1]

    _, _, adx_val = dmi_adx(candles, di_length=adx_len, adx_smoothing=adx_len, offset=0)
    ema_series = _ema_series(closes, ema_len)
    ema50_now = ema_series[-1] if ema_series else None
    ema50_prev = ema_series[-2] if len(ema_series) >= 2 else None

    ema_slope_pct = None
    if ema50_now is not None and ema50_prev is not None and last_close and last_close != 0:
        ema_slope_pct = (ema50_now - ema50_prev) / last_close * 100

    atr_val = atr(candles, length=atr_len, offset=0)
    atr_pct = (atr_val / last_close * 100) if (atr_val and last_close) else None

    # atr_pct_ma50: 과거 50봉의 atr_pct 시리즈 SMA
    atr_pct_list = []
    for i in range(atr_pct_ma_len):
        if len(candles) < atr_len + 1 + i:
            break
        a = atr(candles, length=atr_len, offset=i)
        c = float(candles[-1 - i]["c"])
        if a and c:
            atr_pct_list.append(a / c * 100)
    atr_pct_ma50 = (sum(atr_pct_list) / len(atr_pct_list)) if len(atr_pct_list) >= atr_pct_ma_len else None

    atr_hot = False
    if atr_pct is not None and atr_pct_ma50 is not None and atr_pct_ma50 > 0:
        atr_hot = atr_pct > atr_pct_ma50 * atr_hot_mult

    return {
        "adx": adx_val,
        "close": last_close,
        "ema50_now": ema50_now,
        "ema50_prev": ema50_prev,
        "ema_slope_pct": ema_slope_pct,
        "atr": atr_val,
        "atr_pct": atr_pct,
        "atr_pct_ma50": atr_pct_ma50,
        "atr_hot": atr_hot,
    }
