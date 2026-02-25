# TradeBot (Binance USDT-M + TradingView 봉마감)

TradingView 1H/4H 봉 마감 알림만 받고, 서버에서 Binance Kline 확정 조회·지표 계산·주문·로그를 처리하는 봇입니다.

## 구성

- **API 서버**: `POST /webhook/tv` (Secret 인증, dedup), `GET/POST /params/current|update`, `POST /trade/enable|disable`, `GET /dashboard`, `GET /dashboard/data`
- **Worker**: pending 이벤트 폴링 → Binance klines → EMA/Donchian/DMI/ATR → 전략 신호 → (trade_enabled 시) 주문 실행 + reduceOnly 스탑
- **DB**: MariaDB — events, candles, signals, orders, positions, param_sets, app_settings

## MariaDB(180.230.8.65 tradebot)와 병합

이미 만들어 둔 MariaDB 스키마와 맞추려면:

1. **마이그레이션 1회 실행** (events.status, app_settings 추가)
   ```bash
   mysql -h 180.230.8.65 -u mynolab_user -p tradebot < migrations/001_events_status_and_app_settings.sql
   ```

2. **.env에 DB URL 설정**
   ```
   DATABASE_URL=mysql+pymysql://mynolab_user:비밀번호@180.230.8.65/tradebot?charset=utf8mb4
   ```

3. **의존성**  
   `pip install pymysql cryptography` (requirements.txt 포함됨)

프로젝트 ORM은 DB 컬럼명(closeTime, receivedAt, dedupKey 등)에 맞춰 매핑돼 있습니다. 워크플로우 시각화는 [docs/WORKFLOW.md](docs/WORKFLOW.md) 참고.

## 실행

```bash
# 의존성
pip install -r requirements.txt

# .env 설정 (WEBHOOK_SECRET, BINANCE_API_KEY, BINANCE_API_SECRET, ADMIN_SECRET 등)
cp .env.example .env

# API 서버
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Worker (별도 터미널)
PYTHONPATH=. python3 -c "from app.worker import run_worker; run_worker(5.0)"
```

## Webhook (TradingView)

`POST /webhook/tv` body 예시:

```json
{"symbol": "BTCUSDT", "tf": "4h", "event": "CANDLE_CLOSED", "time": 1771977599999, "secret": "your-webhook-secret"}
```

- `time`: 봉 마감 시간(ms). dedupKey = symbol + tf + time.

## 파라미터 / 킬스위치

- `GET /params/current` — 현재 활성 파라미터 + trade_enabled
- `POST /params/update` — body: `{"secret": "admin-secret", "params": {"adx_min": 18}}`
- `POST /trade/enable` — body: `{"secret": "admin-secret"}`
- `POST /trade/disable` — 킬스위치

## 대시보드

- `GET /dashboard` — HTML 대시보드 (포지션, 이벤트, 주문, 신호, 파라미터)
- `GET /dashboard/data` — JSON

## 백테스트

**Binance API** (캔들 수 제한):
```bash
PYTHONPATH=. python3 -m app.backtest BTCUSDT 4h --limit 500
PYTHONPATH=. python3 -m app.backtest ETHUSDT 1h --limit 300 --adx-min 18
```

**DB 테이블(btc4h 등)** 에서 1.4만 봉 전체 백테스트 + 매매 기록 JSON 저장:
```bash
# .env에 DATABASE_URL=mysql+pymysql://.../tradebot 설정 후
PYTHONPATH=. python3 -m app.backtest BTCUSDT 4h --source db -o trades.json
# limit 없으면 전체 로드. 특정 개수만: --source db --limit 5000 -o trades.json
```
- `btc4h` 테이블은 `app/services/db_klines.py`의 `TABLE_MAP`에 (BTCUSDT, 4h)로 등록돼 있음.
- `-o trades.json` 에 요약(승/패, 총 PnL, 파라미터)과 **전체 매매 기록(trades)** 이 저장됨.

## 테스트넷

`.env`에서:

- `BINANCE_BASE_URL=https://testnet.binancefuture.com`
- `TRADE_ENABLED=false` 또는 DB 킬스위치로 먼저 신호만 확인 후 `POST /trade/enable`로 활성화
