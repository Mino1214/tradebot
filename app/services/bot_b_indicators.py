"""
B봇(평균회귀) 전용 지표: BB(20,2), RSI(14), ADX(14), ATR(14).
"""
from app.services.indicators import (
    bollinger_bands,
    rsi,
    dmi_adx,
    atr,
)


def compute_bot_b_indicators(candles: list[dict], *, bb_len: int = 20, bb_mult: float = 2.0, rsi_len: int = 14, adx_len: int = 14, atr_len: int = 14) -> dict:
    """
    마지막 종료된 봉 기준으로 B봇용 지표 계산.
    Returns: close, bb (upper, mid, lower), rsi, adx, atr, atrPct, bbWidth(선택).
    """
    if not candles:
        return {}
    closes = [c["c"] for c in candles]
    last = candles[-1]
    close = float(last["c"])

    bb_u, bb_m, bb_l = bollinger_bands(closes, length=bb_len, mult=bb_mult, offset=0)
    rsi_val = rsi(closes, length=rsi_len, offset=0)
    _, _, adx_val = dmi_adx(candles, di_length=adx_len, adx_smoothing=adx_len, offset=0)
    atr_val = atr(candles, length=atr_len, offset=0)

    atr_pct = (atr_val / close * 100) if (atr_val and close) else None
    bb_width = ((bb_u - bb_l) / bb_m * 100) if (bb_u is not None and bb_m and bb_l is not None) else None

    # Close가 밴드 어디인지
    bb_zone = "inside"
    if bb_u is not None and close > bb_u:
        bb_zone = "above_upper"
    elif bb_l is not None and close < bb_l:
        bb_zone = "below_lower"

    # RSI 상태
    rsi_status = "neutral"
    if rsi_val is not None:
        if rsi_val <= 30:
            rsi_status = "oversold"
        elif rsi_val >= 70:
            rsi_status = "overbought"

    return {
        "close": close,
        "bb": {"upper": bb_u, "mid": bb_m, "lower": bb_l},
        "bbZone": bb_zone,
        "rsi": rsi_val,
        "rsiStatus": rsi_status,
        "adx": adx_val,
        "atr": atr_val,
        "atrPct": atr_pct,
        "bbWidth": bb_width,
    }
