# 백테스트 실행 방법 (A봇 추세 전략)

백테스트는 **실전(worker)과 동일한 로직**으로 동작합니다.

- **전략**: Donchian 돌파, EMA/ADX 필터, 처리 순서 스탑→청산→진입 (동일)
- **Adaptive Filter**: ADX 상태(OFF/WEAK/NORMAL/STRONG), ATR 횡보 필터, 연속 손실 보호 (동일)
- **청산 후 N봉 대기**: `cooldown_bars` 적용 (실전 worker의 `_in_cooldown`과 동일)

실행은 **터미널(CLI)** 에서 합니다. 웹의 "BACKTEST 모드"는 설정 표시용이며, 실제 백테스트 실행은 아래 명령으로 합니다.

---

## 1. 기본 명령 (복사해서 실행)

프로젝트 루트에서:

```bash
cd /Users/myno/Desktop/tradebot
```

### Binance API로 캔들 가져와서 실행 (인터넷 필요)

```bash
python -m app.backtest BTCUSDT 4h --source binance --capital 1000 -o trades.json
```

- 심볼: `BTCUSDT` 또는 `ETHUSDT`
- 타임프레임: `4h` 또는 `1h`
- `--source binance`: Binance에서 최근 500봉 조회
- `--capital 1000`: 시작 자금 1000 USDT
- `-o trades.json`: 매매 기록을 `trades.json`에 저장 (생략 가능)

### DB 테이블(btc4h, eth4h 등)에서 캔들 사용

DB에 이미 캔들 테이블이 있을 때 (MariaDB 연결 필요):

```bash
python -m app.backtest BTCUSDT 4h --source db --capital 1000 -o trades.json
```

```bash
python -m app.backtest ETHUSDT 4h --source db --capital 1000 -o trades.json
```

- `--source db`: DB 테이블 `btc4h` / `eth4h` / `btc1h` / `eth1h` 에서 로드
- `--limit` 을 안 주면 **테이블 전체** 사용 (예: 1.4만 봉)

---

## 2. 자주 쓰는 옵션

| 옵션 | 설명 | 예시 |
|------|------|------|
| `--capital` | 시작 자금 (USDT) | `--capital 1000` |
| `--source` | `binance` 또는 `db` | `--source db` |
| `--limit` | 캔들 개수 (db일 때 생략 가능) | `--limit 5000` |
| `--cooldown-bars` | 청산 후 N봉 대기 (실전과 동일, 기본은 params) | `--cooldown-bars 1` |
| `-o` / `--output` | 매매 기록 JSON 파일 경로 | `-o trades.json` |
| `--slippage-bps` | 슬리피지 (1만분율) | `--slippage-bps 10` |
| `--fee-bps` | 왕복 수수료 (1만분율) | `--fee-bps 5` |

---

## 3. 실행 예시 (ETH 4h, DB, 전체 데이터)

```bash
cd /Users/myno/Desktop/tradebot
python -m app.backtest ETHUSDT 4h --source db --capital 1000 -o eth4h_trades.json
```

결과는 터미널에 요약이 출력되고, `eth4h_trades.json`(전체 매매), `eth4h_trades_result.json`(요약) 이 생성됩니다.

---

## 4. "BACKTEST 모드"와의 관계

- **관리자 페이지**에서 모드를 "BACKTEST"로 바꿔도 **실제 백테스트가 자동으로 실행되지는 않습니다.**
- **백테스트 실행** = 위의 `python -m app.backtest ...` 명령을 터미널에서 직접 실행하는 것.
- 모드 "BACKTEST"는 "지금 실거래/페이퍼가 아니라 백테스트용 설정을 쓰는 구간" 정도의 표시용입니다.

---

## 5. 실전과 동일하게 돌리기

- **파라미터**: 실전에서 쓰는 `param_sets`(DB)와 동일한 값을 쓰려면 `--adx-min`, `--entry-len`, `--exit-len`, `--cooldown-bars` 등으로 CLI에서 맞춰 주면 됩니다.
- **청산 후 1봉 대기**: 실전에서 `cooldown_bars=1` 쓰면 백테스트도 `--cooldown-bars 1` 로 실행하면 동일합니다.

## 6. 요약

| 하고 싶은 것 | 하는 방법 |
|-------------|-----------|
| **백테스트 실행** | 터미널에서 `python -m app.backtest ETHUSDT 4h --source db --capital 1000 -o out.json` |
| **실전과 동일(청산 후 1봉 대기)** | `--cooldown-bars 1` 추가 |
| **Binance로 테스트** | `--source binance` (최근 500봉) |
| **DB 전체 봉으로 테스트** | `--source db` (--limit 생략) |
| **결과 파일로 저장** | `-o 파일경로` |
