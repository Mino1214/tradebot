# TradeBot 워크플로우

## 1. 전체 흐름 (시각)

```
┌─────────────────┐     Webhook (POST)      ┌──────────────────────────────────────────┐
│  TradingView    │  symbol, tf, time,      │  API 서버 (FastAPI)                       │
│  1H/4H 봉 마감   │  event=CANDLE_CLOSED,  │  POST /webhook/tv                         │
│  알림           │  secret                 │  → Secret 검증                            │
└────────┬────────┘                         │  → dedup(symbol+tf+closeTime)             │
         │                                  │  → events 테이블에 status=pending 적재   │
         │                                  └────────────────────┬─────────────────────┘
         │                                                       │
         │                                                       ▼
         │                                  ┌──────────────────────────────────────────┐
         │                                  │  Worker (폴링 또는 별도 프로세스)           │
         │                                  │  1. pending 이벤트 1건 조회                │
         │                                  │  2. Binance fapi/v1/klines 로 캔들 N개 조회│
         │                                  │  3. 지표 계산 (EMA, Donchian, DMI, ATR)   │
         │                                  │  4. 전략 판단 (진입/청산/유지)             │
         │                                  │  5. signals 테이블 저장 + 텔레그램(선택)   │
         │                                  │  6. trade_enabled 이면 주문 실행          │
         │                                  │     → MARKET 진입 → STOP_MARKET(reduceOnly)│
         │                                  │  7. events.status = processed             │
         │                                  └────────────────────┬─────────────────────┘
         │                                                       │
         │                                                       ▼
         │                                  ┌──────────────────────────────────────────┐
         │                                  │  DB (MariaDB tradebot)                     │
         │                                  │  events, candles, param_sets, signals,     │
         │                                  │  orders, positions, app_settings          │
         │                                  └────────────────────┬─────────────────────┘
         │                                                       │
         │                                                       ▼
         │                                  ┌──────────────────────────────────────────┐
         │                                  │  대시보드 / API                            │
         │                                  │  GET /dashboard, /dashboard/data           │
         │                                  │  GET /params/current, POST /trade/disable  │
         │                                  └──────────────────────────────────────────┘
```

## 2. Mermaid 다이어그램

```mermaid
flowchart TB
  subgraph TV[TradingView]
    A[1H/4H 봉 마감 알림]
  end

  subgraph API[API 서버]
    B["POST /webhook/tv"]
    C[Secret 검증]
    D[dedup: symbol+tf+closeTime]
    E[events에 pending 적재]
  end

  subgraph Worker[Worker]
    F[pending 이벤트 조회]
    G[Binance klines 조회]
    H[지표 계산]
    I[진입/청산 판단]
    J[signals 저장]
    K{trade_enabled?}
    L[MARKET 진입]
    M[STOP_MARKET 스탑]
    N[orders/positions 저장]
  end

  subgraph DB[(MariaDB)]
    T1[events]
    T2[signals]
    T3[orders]
    T4[positions]
    T5[param_sets]
    T6[app_settings]
  end

  subgraph Dashboard[대시보드]
    O["GET /dashboard"]
    P["GET /params/current"]
    Q["POST /trade/enable|disable"]
  end

  A -->|Webhook| B
  B --> C --> D --> E
  E --> T1
  T1 --> F
  F --> G --> H --> I --> J --> T2
  J --> K
  K -->|Yes| L --> M --> N
  N --> T3
  N --> T4
  T5 --> H
  T6 --> K
  T1 --> O
  T2 --> O
  T3 --> O
  T4 --> O
  P --> T5
  Q --> T6
```

## 3. 데이터 흐름 요약

| 단계 | 입력 | 출력 |
|------|------|------|
| Webhook | TV 알림 (symbol, tf, time, secret) | events 1행 (status=pending) |
| Worker | events 1행 (pending) | Binance klines → 지표 → 신호 → signals 1행, (선택) 주문 → orders/positions |
| 킬스위치 | app_settings.trade_enabled | 주문 실행 여부 |

## 4. MariaDB와 병합 시 체크리스트

1. **DB 스키마**  
   - 이미 만든 테이블: `events`, `candles`, `param_sets`, `signals`, `orders`, `positions`  
   - 프로젝트에서 추가로 필요한 것:  
     - `events.status` 컬럼  
     - `app_settings` 테이블  
   - `migrations/001_events_status_and_app_settings.sql` 실행 후 서버/워커 실행.

2. **연결 정보**  
   - `.env`에  
     `DATABASE_URL=mysql+pymysql://mynolab_user:비밀번호@180.230.8.65/tradebot?charset=utf8mb4`  
   - 비밀번호는 환경변수로만 두고 저장소에 올리지 않기.

3. **실행 순서**  
   - 마이그레이션 실행 → API 서버 기동 → Worker 기동 → TradingView 웹훅 설정.
