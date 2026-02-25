# 전략 규칙 정리 (고정 정의 + 최소 수정 세트)

## 0) 고정 정의 3개

### A. Donchian 계산: “방금 닫힌 봉” 제외
- **진입 채널(hiEntry/loEntry)**: 직전 20봉만 사용 (현재 막 닫힌 봉 제외).  
  → `hiEntry = highest(high, 20)[1]` 느낌.
- **청산 채널(hiExit/loExit)**: 동일하게 직전 20봉(또는 exit_len)만 사용, offset=1.

### B. 청산 채널도 직전 N봉
- exit_len 기본 10 (진입 20 / 청산 10 변형 가능).
- “다음 봉에서 평가”가 아니라 “마감된 봉에서 평가”가 되도록 직전 N봉 기준으로 통일.

### C. 한 봉 마감 시 처리 순서
1. **스탑 체결 여부** (봉 중 low/high로 판단)
2. **청산 신호** (loExit/hiExit)
3. **진입 신호** (hiEntry/loEntry + 필터)

---

## 1) 스탑

- **옵션**: 고정 스탑 (진입 시 1회 계산 후 변경 없음).
- **계산**: 롱 `stopPrice = entryAvg - stop_mult × ATR`, 숏 `stopPrice = entryAvg + stop_mult × ATR`.
- **체결 판단**:  
  - 롱: 봉 중 `low <= stopPrice` → 스탑 체결.  
  - 숏: 봉 중 `high >= stopPrice` → 스탑 체결.  
- 실거래는 거래소 STOP_MARKET(reduceOnly)로 동일하게 처리.

---

## 2) 진입 품질 필터 3개

| 필터 | 내용 |
|------|------|
| **돌파 후 확인** | 롱: `close > hiEntry + breakout_atr_margin × ATR`, 숏: `close < loEntry - margin × ATR` (기본 0.2×ATR). |
| **EMA200 기울기** | 롱: `EMA200 > EMA200[1]`, 숏: `EMA200 < EMA200[1]`. |
| **ADX 상승** | `ADX > ADX[1]` (ADX >= adx_min에 더해). |

---

## 3) 같은 4시간봉 안 방향 전환 금지

- 한 봉 마감에서 **청산(또는 스탑) 발생 시**, 그 봉에서는 **진입 로직 스킵**.
- **cooldown_bars**: 청산 후 N봉 대기 후 재진입 (0=없음, 1 추천).

---

## 4) 포지션 사이징 (R%)

- `riskUSDT = equity × loss_pct`
- `stopDist = |entryPrice - stopPrice|`
- `qty = riskUSDT / stopDist` → stepSize 내림, minNotional 확인.

---

## 5) 파라미터 기본값 요약

| 이름 | 기본 | 비고 |
|------|------|------|
| entry_len | 20 | Donchian 진입 |
| exit_len | 10 | Donchian 청산 |
| adx_min | 20 | ADX 최소 |
| breakout_atr_margin | 0.2 | 돌파 확인 |
| use_ema_slope | true | EMA 기울기 필터 |
| use_adx_rising | true | ADX 상승 필터 |
| cooldown_bars | 0 | 청산 후 대기 봉 수 |
| stop_mult | 2.0 | 고정 스탑 배수 |
| loss_pct | 0.01 | 계좌 대비 손실 허용 비율 |

---

## 6) 백테스트 반영 사항

- 거래소 4시간봉 마감 시각(UTC 등) 정합성.
- 슬리피지/수수료: `--slippage-bps`, `--fee-bps` 옵션.
- 포지션 상태: flat / long / short + entryPrice + stopPrice 유지.
- 신호는 **종가 기준**, 스탑은 **봉 중 low/high 기준** 이원화.
