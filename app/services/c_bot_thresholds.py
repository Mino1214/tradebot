"""
C봇 v1.1 임계값. TF별(1h/4h) 디폴트, 심볼별 오버라이드 가능.
"""
from typing import TypedDict


class ThresholdProfile(TypedDict):
    RANGE_ENTER: float
    RANGE_EXIT: float
    TREND_ENTER: float
    TREND_EXIT: float
    slope_min: float
    slope_max: float
    confirm_N: int
    cooldown_M_bars: int


# 1H 디폴트
THRESHOLDS_1H: ThresholdProfile = {
    "RANGE_ENTER": 16,
    "RANGE_EXIT": 20,
    "TREND_ENTER": 25,
    "TREND_EXIT": 21,
    "slope_min": 0.05,
    "slope_max": 0.02,
    "confirm_N": 2,
    "cooldown_M_bars": 1,
}

# 4H 디폴트
THRESHOLDS_4H: ThresholdProfile = {
    "RANGE_ENTER": 14,
    "RANGE_EXIT": 18,
    "TREND_ENTER": 23,
    "TREND_EXIT": 19,
    "slope_min": 0.08,
    "slope_max": 0.03,
    "confirm_N": 1,
    "cooldown_M_bars": 1,
}

DEFAULT_THRESHOLDS: dict[str, ThresholdProfile] = {
    "1h": THRESHOLDS_1H,
    "4h": THRESHOLDS_4H,
}

# 심볼/TF별 오버라이드 (비어 있으면 디폴트 사용)
_threshold_overrides: dict[str, dict[str, ThresholdProfile]] = {}


def get_thresholds(symbol: str, tf: str) -> ThresholdProfile:
    """symbol/tf에 맞는 임계값. override 없으면 디폴트 TF 프로필."""
    tf = (tf or "4h").lower()
    if symbol in _threshold_overrides and tf in _threshold_overrides[symbol]:
        return _threshold_overrides[symbol][tf]
    return DEFAULT_THRESHOLDS.get(tf, THRESHOLDS_4H)


def set_threshold_override(symbol: str, tf: str, profile: ThresholdProfile) -> None:
    _threshold_overrides.setdefault(symbol, {})[tf.lower()] = profile
