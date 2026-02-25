"""
C봇 v1.1 API: 상태 스냅샷, 풀 스냅샷(지표 포함), evaluate(캔들 마감 시), 관리자 페이지.
"""
from fastapi import APIRouter, Depends, Query, Body
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.c_bot import get_snapshot, evaluate
from app.services.c_bot_thresholds import get_thresholds
from app.services.c_bot_indicators import compute_c_bot_indicators
from app.services.binance_client import fetch_klines

router = APIRouter(prefix="/admin/c-bot", tags=["admin-c-bot"])


class EvaluateBody(BaseModel):
    tf: str = "4h"
    symbol: str = "BTCUSDT"
    now_candle_time: int | None = None
    account_state: dict | None = None
    bot_states: dict | None = None


@router.post("/evaluate")
def c_bot_evaluate(db: Session = Depends(get_db), body: EvaluateBody = Body(default=None)):
    """
    캔들 마감 시 호출. ohlcv는 Binance에서 조회 후 evaluate() 실행.
    """
    body = body or EvaluateBody()
    tf = body.tf or "4h"
    symbol = body.symbol or "BTCUSDT"
    account_state = body.account_state or {}
    bot_states = body.bot_states or {}
    try:
        klines = fetch_klines(symbol, tf, limit=200)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not klines:
        return {"ok": False, "error": "No klines"}
    bar_ms = 4 * 3600 * 1000 if tf.lower() == "4h" else 3600 * 1000
    last_open = klines[-1]["open_time"]
    now_candle_time = body.now_candle_time or (last_open + bar_ms - 1)
    result = evaluate(
        db,
        tf=tf,
        symbol=symbol,
        ohlcv=klines,
        now_candle_time=now_candle_time,
        account_state=account_state,
        bot_states=bot_states,
    )
    return {"ok": True, "snapshot": result}


@router.get("/state")
def c_bot_state(db: Session = Depends(get_db)):
    """저장된 C봇 상태만 (지표 없음)."""
    return get_snapshot(db)


@router.get("/full")
def c_bot_full(
    db: Session = Depends(get_db),
    symbol: str = Query("BTCUSDT"),
    tf: str = Query("4h"),
):
    """
    관리자용 풀 스냅샷: 저장된 state + 현재 캔들 기준 지표 + 임계값.
    (evaluate 호출은 하지 않음; 최신 지표 표시용)
    """
    state = get_snapshot(db)
    th = get_thresholds(symbol, tf)
    indicators = {}
    try:
        klines = fetch_klines(symbol, tf, limit=200)
        if klines:
            indicators = compute_c_bot_indicators(klines)
    except Exception:
        pass
    return {
        **state,
        "symbol": symbol,
        "tf": tf,
        "indicators": {
            "adx": indicators.get("adx"),
            "atr_pct": indicators.get("atr_pct"),
            "atr_pct_ma50": indicators.get("atr_pct_ma50"),
            "atr_hot": indicators.get("atr_hot", False),
            "ema_slope_pct": indicators.get("ema_slope_pct"),
        },
        "threshold_profile": th,
    }


@router.get("/", response_class=HTMLResponse)
def admin_c_bot_page():
    """관리자 페이지: 필수 6개 + 보강 4개 (v1.1)."""
    return _admin_c_bot_html()


def _admin_c_bot_html() -> str:
    return """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>C봇 v1.1 (중재봇) 관리자</title>
  <style>
    :root { --bg: #0d1117; --card: #161b22; --text: #e6edf3; --muted: #8b949e; --green: #3fb950; --red: #f85149; --yellow: #d29922; }
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 1rem; }
    h1 { font-size: 1.25rem; margin-bottom: 0.5rem; }
    .sub { color: var(--muted); font-size: 0.85rem; margin-bottom: 1rem; }
    .card { background: var(--card); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
    .card h2 { font-size: 0.95rem; margin: 0 0 0.5rem 0; color: var(--muted); }
    .row { display: flex; flex-wrap: wrap; gap: 1rem 2rem; margin: 0.25rem 0; }
    .item { min-width: 140px; }
    .label { color: var(--muted); font-size: 0.8rem; }
    .value { font-weight: 600; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
    .badge.trend { background: #1f6feb; color: #fff; }
    .badge.range { background: var(--green); color: #000; }
    .badge.neutral { background: var(--muted); color: #000; }
    .badge.a { background: #1f6feb; color: #fff; }
    .badge.b { background: var(--green); color: #000; }
    .badge.none { background: var(--muted); color: #000; }
    .on { color: var(--green); }
    .off { color: var(--red); }
    button { background: var(--muted); color: var(--bg); border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; }
    pre { font-size: 0.8rem; overflow: auto; margin: 0; }
  </style>
</head>
<body>
  <h1>C봇 v1.1 (중재봇) 관리자</h1>
  <p class="sub">필수 6개 + 보강 4개</p>
  <p><button onclick="load()">Refresh</button> Symbol <input id="symbol" value="BTCUSDT" size="8"> TF <select id="tf"><option value="4h">4H</option><option value="1h">1H</option></select></p>

  <div class="card">
    <h2>필수 6개</h2>
    <div class="row">
      <span class="item"><span class="label">1. regime_current</span><br><span id="regime_current" class="value badge">-</span></span>
      <span class="item"><span class="label">2. active_strategy</span><br><span id="active_strategy" class="value badge">-</span></span>
      <span class="item"><span class="label">3. trading_allowed</span><br><span id="trading_allowed" class="value">-</span></span>
    </div>
    <div class="row">
      <span class="item"><span class="label">4. blocked_reason</span><br><span id="blocked_reason" class="value">-</span></span>
    </div>
    <div class="row">
      <span class="item"><span class="label">5. ADX / ema_slope_pct / atr_pct</span><br><span id="indicators_main" class="value">-</span></span>
    </div>
    <div class="row">
      <span class="item"><span class="label">6. confirm_count / cooldown_until</span><br><span id="switch_state" class="value">-</span></span>
    </div>
  </div>

  <div class="card">
    <h2>보강 4개 (운영 안정성)</h2>
    <div class="row">
      <span class="item"><span class="label">7. atr_hot + atr_pct_ma50</span><br><span id="atr_extra" class="value">-</span></span>
    </div>
    <div class="row">
      <span class="item"><span class="label">8. thresholds profile</span><br><pre id="threshold_profile">-</pre></span>
    </div>
    <div class="row">
      <span class="item"><span class="label">9. emergency_mode / emergency_reason</span><br><span id="emergency" class="value">-</span></span>
    </div>
    <div class="row">
      <span class="item"><span class="label">10. last_decision_time</span><br><span id="last_decision_time" class="value">-</span></span>
    </div>
  </div>

  <script>
    function load() {
      var symbol = document.getElementById('symbol').value;
      var tf = document.getElementById('tf').value;
      fetch('/admin/c-bot/full?symbol=' + encodeURIComponent(symbol) + '&tf=' + encodeURIComponent(tf))
        .then(function(r) { return r.json(); })
        .then(function(d) {
          var r = d.regime_current || '-';
          document.getElementById('regime_current').textContent = r;
          document.getElementById('regime_current').className = 'value badge ' + (r || '').toLowerCase();

          var s = d.active_strategy || '-';
          document.getElementById('active_strategy').textContent = s;
          document.getElementById('active_strategy').className = 'value badge ' + (s || 'none').toLowerCase();

          var t = d.trading_allowed;
          document.getElementById('trading_allowed').textContent = t ? 'ON' : 'OFF';
          document.getElementById('trading_allowed').className = 'value ' + (t ? 'on' : 'off');

          document.getElementById('blocked_reason').textContent = d.blocked_reason || '-';

          var ind = d.indicators || {};
          document.getElementById('indicators_main').textContent = [ind.adx, ind.ema_slope_pct, ind.atr_pct].map(function(x){ return x != null ? (typeof x === 'number' ? x.toFixed(4) : x) : '-'; }).join(' / ');

          var sw = d.switch_state || {};
          document.getElementById('switch_state').textContent = (sw.confirm_count != null ? sw.confirm_count : '-') + ' / ' + (sw.cooldown_until ? new Date(sw.cooldown_until).toISOString() : '-');

          document.getElementById('atr_extra').textContent = (ind.atr_hot ? 'ON' : 'OFF') + ' / ' + (ind.atr_pct_ma50 != null ? ind.atr_pct_ma50.toFixed(4) : '-');

          document.getElementById('threshold_profile').textContent = JSON.stringify(d.threshold_profile || {}, null, 2);

          document.getElementById('emergency').textContent = (d.emergency_mode ? 'ON' : 'OFF') + ' / ' + (d.emergency_reason || '-');
          document.getElementById('emergency').className = 'value ' + (d.emergency_mode ? 'off' : 'on');

          var lt = d.last_decision_time;
          document.getElementById('last_decision_time').textContent = lt ? new Date(lt).toISOString() : '-';
        })
        .catch(function(e) {
          document.getElementById('blocked_reason').textContent = 'Error: ' + e.message;
        });
    }
    load();
    setInterval(load, 20000);
  </script>
</body>
</html>"""
