"""
Server-side indicators: Donchian, EMA, DMI (+DI, -DI, ADX), ATR.
Calculated on closed candles only; last value applies to the bar that just closed.
"""
from typing import Sequence


def donchian_high(candles: Sequence[dict], length: int, offset: int = 0) -> float | None:
    """Max of high over last `length` bars, ending at index -1 - offset."""
    n = len(candles)
    start = n - length - offset
    if start < 0:
        return None
    window = candles[start : n - offset]
    if not window:
        return None
    return max(c["h"] for c in window)


def donchian_low(candles: Sequence[dict], length: int, offset: int = 0) -> float | None:
    """Min of low over last `length` bars."""
    n = len(candles)
    start = n - length - offset
    if start < 0:
        return None
    window = candles[start : n - offset]
    if not window:
        return None
    return min(c["l"] for c in window)


def ema(series: list[float], length: int) -> float | None:
    """EMA of series; returns EMA value for the last element. multiplier = 2/(length+1)."""
    if len(series) < length:
        return None
    k = 2.0 / (length + 1)
    ema_val = sum(series[:length]) / length
    for i in range(length, len(series)):
        ema_val = series[i] * k + ema_val * (1 - k)
    return ema_val


def atr(candles: Sequence[dict], length: int = 14, offset: int = 0) -> float | None:
    """ATR(length) at bar -1 - offset. Uses previous closes for first TR."""
    n = len(candles)
    if n < length + 1 + offset:
        return None
    start = n - length - 1 - offset
    tr_list = []
    for i in range(start, n - offset):
        high = candles[i]["h"]
        low = candles[i]["l"]
        if i == 0:
            prev_close = candles[0]["c"]
        else:
            prev_close = candles[i - 1]["c"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    return sum(tr_list) / len(tr_list) if tr_list else None


def dmi_adx(
    candles: Sequence[dict],
    di_length: int = 14,
    adx_smoothing: int = 14,
    offset: int = 0,
) -> tuple[float | None, float | None, float | None]:
    """
    Returns (+DI, -DI, ADX) for the bar at -1 - offset.
    Uses +DM, -DM, TR smoothed with Wilder (RMA); ADX = smoothed DX.
    """
    n = len(candles)
    need = di_length + adx_smoothing + 2 + offset
    if n < need:
        return None, None, None

    def rma(series: list[float], length: int) -> list[float]:
        out = []
        alpha = 1.0 / length
        for i, x in enumerate(series):
            if i == 0:
                out.append(sum(series[:length]) / length if len(series) >= length else x)
            else:
                out.append(alpha * x + (1 - alpha) * out[-1])
        return out

    start = n - need - offset
    end = n - offset
    slice_c = candles[start:end]

    tr_list = []
    plus_dm = []
    minus_dm = []
    for i in range(1, len(slice_c)):
        h = slice_c[i]["h"]
        l = slice_c[i]["l"]
        pc = slice_c[i - 1]["c"]
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
        up = h - slice_c[i - 1]["h"]
        down = slice_c[i - 1]["l"] - l
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)

    tr_smooth = rma(tr_list, di_length)
    plus_smooth = rma(plus_dm, di_length)
    minus_smooth = rma(minus_dm, di_length)

    # Last index
    idx = -1
    tr_val = tr_smooth[idx]
    pdi = 100 * plus_smooth[idx] / tr_val if tr_val else 0
    mdi = 100 * minus_smooth[idx] / tr_val if tr_val else 0

    dx_series = []
    for i in range(len(tr_smooth)):
        pd = 100 * plus_smooth[i] / tr_smooth[i] if tr_smooth[i] else 0
        md = 100 * minus_smooth[i] / tr_smooth[i] if tr_smooth[i] else 0
        di_sum = pd + md
        dx_series.append(100 * abs(pd - md) / di_sum if di_sum else 0)

    adx_series = rma(dx_series, adx_smoothing)
    adx_val = adx_series[-1] if adx_series else None

    return pdi, mdi, adx_val


def sma(series: list[float], length: int) -> float | None:
    """SMA of last `length` values."""
    if len(series) < length:
        return None
    return sum(series[-length:]) / length


def bollinger_bands(
    closes: Sequence[float],
    length: int = 20,
    mult: float = 2.0,
    offset: int = 0,
) -> tuple[float | None, float | None, float | None]:
    """Returns (upper, mid, lower) for the bar at -1 - offset. mid = SMA(close, length)."""
    n = len(closes)
    if n < length + offset:
        return None, None, None
    window = closes[-(length + offset) : n - offset] if offset else closes[-length:]
    mid = sum(window) / len(window)
    variance = sum((x - mid) ** 2 for x in window) / len(window)
    std = variance ** 0.5 if variance else 0
    upper = mid + mult * std
    lower = mid - mult * std
    return upper, mid, lower


def rsi(series: list[float], length: int = 14, offset: int = 0) -> float | None:
    """RSI for the bar at -1 - offset. Uses Wilder smoothing (RMA) for gains/losses."""
    n = len(series)
    if n < length + 1 + offset:
        return None
    start = n - length - 1 - offset
    gains, losses = [], []
    for i in range(start + 1, n - offset):
        ch = series[i] - series[i - 1]
        gains.append(ch if ch > 0 else 0)
        losses.append(-ch if ch < 0 else 0)
    avg_gain = sum(gains) / len(gains)
    avg_loss = sum(losses) / len(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema_series(series: list[float], length: int) -> list[float]:
    """EMA for each index >= length-1. Returns list, last element = current EMA."""
    if len(series) < length:
        return []
    k = 2.0 / (length + 1)
    out = []
    ema_val = sum(series[:length]) / length
    out.append(ema_val)
    for i in range(length, len(series)):
        ema_val = series[i] * k + ema_val * (1 - k)
        out.append(ema_val)
    return out


def compute_all(
    candles: list[dict],
    *,
    ema_len: int = 200,
    entry_len: int = 20,
    exit_len: int = 20,
    dmi_len: int = 14,
    atr_len: int = 14,
) -> dict:
    """
    Compute all indicators for the *last closed bar*.
    Donchian: offset=1 = "직전 N봉" (방금 닫힌 봉 제외) so breakout condition is clear.
    """
    if not candles:
        return {}
    closes = [c["c"] for c in candles]
    last = candles[-1]

    # EMA current and previous (for slope filter)
    ema200 = ema(closes, ema_len)
    ema_series = _ema_series(closes, ema_len)
    ema200_prev = ema_series[-2] if len(ema_series) >= 2 else None

    # Donchian: 직전 20봉만 (현재 막 닫힌 봉 제외) → offset=1
    hi_entry = donchian_high(candles, entry_len, offset=1)
    lo_entry = donchian_low(candles, entry_len, offset=1)
    hi_exit = donchian_high(candles, exit_len, offset=1)
    lo_exit = donchian_low(candles, exit_len, offset=1)

    plus_di, minus_di, adx = dmi_adx(candles, di_length=dmi_len, adx_smoothing=dmi_len, offset=0)
    _, _, adx_prev = dmi_adx(candles, di_length=dmi_len, adx_smoothing=dmi_len, offset=1)
    atr_val = atr(candles, length=atr_len, offset=0)
    atr_30 = atr(candles, length=30, offset=0)  # Adaptive Filter: 변동성 필터용

    return {
        "ema200": ema200,
        "ema200_prev": ema200_prev,
        "hiEntry": hi_entry,
        "loEntry": lo_entry,
        "hiExit": hi_exit,
        "loExit": lo_exit,
        "plusDI": plus_di,
        "minusDI": minus_di,
        "ADX": adx,
        "ADX_prev": adx_prev,
        "ATR": atr_val,
        "ATR_30": atr_30,
        "close": last["c"],
        "high": last["h"],
        "low": last["l"],
    }
