# TradingView → 서버 Webhook (봉 마감 데이터) 형식

봇은 **POST `/webhook/tv`** 로 JSON을 받습니다. 봉이 마감될 때마다 이 형식으로 한 번만 보내면 됩니다.

## 1. 필수 필드

| 필드   | 타입   | 설명 |
|--------|--------|------|
| `symbol` | string | 심볼 (예: `BTCUSDT`, `ETHUSDT`) |
| `tf`     | string | 타임프레임 (예: `1h`, `4h`) |
| `time`   | number | **봉 마감 시각 (epoch 밀리초)** |
| `secret` | string | 웹훅 인증용 시크릿 (`.env`의 `WEBHOOK_SECRET`과 일치) |

## 2. 선택 필드

| 필드   | 타입   | 기본값 | 설명 |
|--------|--------|--------|------|
| `event` | string | `"CANDLE_CLOSED"` | 이벤트 종류. 현재는 `CANDLE_CLOSED`만 지원 |

## 3. 예시 JSON (4시간봉 마감)

```json
{
  "symbol": "BTCUSDT",
  "tf": "4h",
  "event": "CANDLE_CLOSED",
  "time": 1730001600000,
  "secret": "your-webhook-secret"
}
```

- `time`: 해당 **4시간봉의 종료 시각 (close time)** 을 epoch ms로 보냅니다.
- 1시간봉이면 `tf`: `"1h"`, 4시간봉이면 `tf`: `"4h"` 로 맞춥니다.

## 4. Pine Script에서 보내는 방법

봉이 **한 번만** 마감될 때 알림이 나가도록 `request.security()` 또는 봉 마감 감지 후 `alert()` 한 번 호출하는 방식으로 보내면 됩니다.

### 4.1 봉 마감 시각 (close time) 계산

- Binance 기준 4시간봉: 0:00, 4:00, 8:00, 12:00, 16:00, 20:00 (UTC).
- 서버는 **봉 마감 시각(close time)** 을 epoch **밀리초(ms)** 로 받습니다. Pine의 `time_close`는 초 단위이므로 `math.floor(time_close * 1000)` 사용.

Pine Script v5 예시 (4시간봉 마감 시 alert 메시지로 JSON 전달):

```pinescript
//@version=5
indicator("Bar close webhook", overlay=true)

// 4시간봉 마감 시 한 번만 true
barClosed = ta.change(time("240")) != 0 and barstate.isconfirmed

// 마감된 봉의 close time (ms). TradingView은 초 단위이므로 * 1000
closeTimeMs = math.floor(time_close * 1000)

// 전송할 JSON (secret은 Alert 생성 시 {{secret}} 등으로 치환 가능)
payload = '{"symbol":"BTCUSDT","tf":"4h","event":"CANDLE_CLOSED","time":' + str.tostring(closeTimeMs) + ',"secret":"YOUR_WEBHOOK_SECRET"}'

if barClosed
    alert(payload, alert.freq_once_per_bar_close)
```

- **Alert 설정**:  
  - Condition: `barClosed` (또는 해당 조건)  
  - Message: 위 예시에서는 `payload` 변수 내용을 그대로 사용.  
  - TradingView Alert 메시지에 `{{plot_0}}` 등을 쓰는 경우, `payload`를 `plotchar`로 넘기거나, Alert 메시지에 직접 JSON을 넣고 `symbol`/`tf`/`time`/`secret`만 치환해도 됨.

### 4.2 Webhook URL로 보내기 (Alert 연동)

TradingView Alert에서:

1. **Webhook URL**: 서버 주소 + 경로  
   - 예: `https://your-server.com/webhook/tv`
2. **Message**: 아래 형식의 JSON 문자열 (한 줄로).

```
{"symbol":"BTCUSDT","tf":"4h","event":"CANDLE_CLOSED","time":1730001600000,"secret":"YOUR_WEBHOOK_SECRET"}
```

- `time` 자리에는 **마감된 봉의 close time (ms)** 를 넣습니다.  
  Pine에서 `time_close`는 초 단위이므로 `math.floor(time_close * 1000)` 사용.

### 4.3 1시간봉 / 4시간봉 분리 예시

- 4시간봉: `tf": "4h"`, 4시간봉의 `time_close * 1000`.
- 1시간봉: `tf": "1h"`, 1시간봉의 `time_close * 1000`.

같은 차트에서 여러 타임프레임을 쓰려면, 각각 다른 Alert/조건으로 위 JSON의 `tf`와 `time`만 바꿔 보내면 됩니다.

## 5. 서버 응답

- **200 + `ok: true`**
  - `status: "queued"`: 이벤트 정상 등록.
  - `status: "duplicate"`: 동일 `symbol`+`tf`+`time` 이미 처리됨 (중복 무시).
- **401**: `secret` 불일치.
- **400**: `event`가 `CANDLE_CLOSED`가 아님.

## 6. 정리 (복사용 최소 예시)

```json
{
  "symbol": "BTCUSDT",
  "tf": "4h",
  "event": "CANDLE_CLOSED",
  "time": 1730001600000,
  "secret": "여기에_WEBHOOK_SECRET_입력"
}
```

- `symbol`: 거래 심볼 (예: BTCUSDT, ETHUSDT)
- `tf`: `"1h"` 또는 `"4h"`
- `time`: **마감된 봉의 close time (epoch 밀리초)**
- `secret`: 환경변수 `WEBHOOK_SECRET`과 동일한 값

이 형식에 맞게 Pine Script에서 봉 마감 시 위 JSON을 한 번만 보내면 됩니다.
