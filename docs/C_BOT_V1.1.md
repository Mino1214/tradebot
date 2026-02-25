# C봇 v1.1 (중재봇) — 실거래 1H/4H 설계 반영

C봇은 **주문을 직접 내지 않고** 다음만 수행:
1. regime 판정: TREND / RANGE / NEUTRAL  
2. active_strategy 선택: A / B / NONE  
3. trading_allowed(신규 진입) 게이트  
4. 스위칭 안정화(확정대기/히스테리시스/쿨다운)  
5. API로 상태/사유 제공  

포지션 관리(익절/손절/타임아웃)는 각 봇(A/B)이 수행.

---

## 입력/출력

**입력 (매 캔들 마감마다)**  
- tf (1h/4h), symbol, ohlcv(최근 200+봉), account_state(open_position_exists, daily_pnl_pct, consecutive_losses), bot_states(A/B: enabled, position_open, health)

**출력 (스냅샷)**  
- regime_current, candidate_regime, active_strategy, trading_allowed, blocked_reason  
- emergency_mode, emergency_reason  
- switch_state (confirm_count, cooldown_until)  
- indicators (adx, atr_pct, atr_pct_ma50, atr_hot, ema_slope_pct)

---

## 지표 (고정)

- **ADX(14)**  
- **EMA50 slope 정규화**: `ema_slope_pct = (EMA50_now - EMA50_prev) / Close_now * 100`  
- **ATR%**: `atr_pct = ATR(14)/Close*100`, `atr_pct_ma50 = SMA(atr_pct, 50)`, `atr_hot = atr_pct > atr_pct_ma50 * 1.5`

---

## 임계값 (디폴트, 심볼/TF 오버라이드 가능)

| TF | RANGE_ENTER | RANGE_EXIT | TREND_ENTER | TREND_EXIT | slope_min | slope_max | confirm_N | cooldown_M |
|----|-------------|------------|-------------|------------|-----------|-----------|-----------|------------|
| 1H | 16 | 20 | 25 | 21 | 0.05 | 0.02 | 2 | 1 |
| 4H | 14 | 18 | 23 | 19 | 0.08 | 0.03 | 1 | 1 |

---

## Regime / Strategy

- **후보**: trend_ok = (ADX≥TREND_ENTER) & (abs(ema_slope_pct)≥slope_min) & (!atr_hot)  
  range_ok = (ADX≤RANGE_ENTER) & (abs(ema_slope_pct)≤slope_max) & (!atr_hot)  
- **확정**: 동일 후보가 confirm_N봉 연속이면 regime 전환, 전환 시 cooldown_until = now_candle_time + M봉  
- **Strategy**: TREND→A, RANGE→B, NEUTRAL→NONE  

---

## Risk Gate / blocked_reason 우선순위

1. Emergency  
2. Daily loss limit hit (daily_pnl_pct ≤ -2%)  
3. Consecutive losses limit (≥3)  
4. Position already open (max_positions=1)  
5. ATR too hot  
6. Cooldown  
7. NEUTRAL regime  

---

## API

- `GET /admin/c-bot/` — 관리자 페이지 (필수 6개 + 보강 4개)  
- `GET /admin/c-bot/state` — 저장된 상태만  
- `GET /admin/c-bot/full?symbol=&tf=` — 상태 + 현재 지표 + 임계값  
- `POST /admin/c-bot/evaluate` — Body: `{ tf, symbol, now_candle_time?, account_state?, bot_states? }`. ohlcv는 Binance 조회 후 evaluate 실행  

---

## 구현 위치

- 지표: `app/services/c_bot_indicators.py`  
- 임계값: `app/services/c_bot_thresholds.py`  
- 로직/상태: `app/services/c_bot.py`  
- API/관리자: `app/routers/admin_c_bot.py`  
