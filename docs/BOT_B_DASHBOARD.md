# B봇 (평균회귀) 대시보드

- **A봇**: 추세/트렌드 봇 (기존)
- **B봇**: 평균회귀 봇 (BB, RSI, ADX RANGE 구간)
- **C봇**: 중재봇 (추후) — Regime 판단 후 A/B 매매 결정

## URL

- **뷰**: `GET /dashboard/b/` → B봇 대시보드 단일 페이지
- **데이터 API**: `GET /dashboard/b/data?symbol=BTCUSDT&tf=4h` → 설계서 JSON

## 데이터 모델 (API 응답)

뷰는 아래 구조만 받으면 됨.

| 필드 | 설명 |
|------|------|
| `status` | RUNNING / PAUSED / NO-TRADE |
| `regime` | RANGE / NEUTRAL / TREND (중재봇 연동 전에는 ADX로 판단) |
| `tf`, `symbol`, `candleTime` | 타임프레임, 종목, 마지막 캔들 시간 |
| `indicators` | close, bb, rsi, adx, atr, atrPct, bbWidth, bbZone, rsiStatus |
| `rules` | adxRangeMax, rsiLongMax, rsiShortMin, atrPctHotLimit, cooldownRemainingBars |
| `signal` | long.ready, short.ready, long/short.checks, blockedReason |
| `position` | null 또는 side, entry, size, sl, tp, upnl, barsInTrade, timeoutBarsLeft |
| `risk` | dailyPnl, dailyLossLimit, consecutiveLosses, tradingAllowed, tradeDisabledReason |
| `logs` | [{ time, type, msg }] 최근 20개 |

## B봇 활성 조건

- **Regime = RANGE** 일 때만 "B봇 활성" (초록). NEUTRAL/TREND면 비활성(회색).
- Regime은 현재 ADX < adxRangeMax(기본 16) 이면 RANGE.

## 구현 위치

- 지표: `app/services/bot_b_indicators.py` (BB 20,2 / RSI 14 / ADX / ATR)
- 전략: `app/services/bot_b_strategy.py` (진입 체크리스트, regime)
- 상태: `app/services/bot_b_state.py` (포지션/로그 인메모리, 리스크/상태 DB)
- API·뷰: `app/routers/dashboard_b.py`
