"""
B봇(평균회귀) 대시보드 API + 뷰.
- GET /dashboard/b/data → 설계서의 JSON (뷰가 받는 데이터)
- GET /dashboard/b → HTML 단일 페이지
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.binance_client import fetch_klines
from app.services.bot_b_indicators import compute_bot_b_indicators
from app.services.bot_b_strategy import (
    get_regime_from_adx,
    evaluate_long_checks,
    evaluate_short_checks,
    signal_ready,
    checks_to_dict,
    signal_score,
    REGIME_RANGE,
    REGIME_NEUTRAL,
    REGIME_TREND,
)
from app.services.bot_b_state import (
    get_position,
    get_logs,
    get_risk_from_db,
    get_status_from_db,
)

router = APIRouter(prefix="/dashboard/b", tags=["dashboard-b"])

# 규칙 기본값 (뷰 rules 표시 + 체크에 사용)
DEFAULT_ADX_RANGE_MAX = 16
DEFAULT_RSI_LONG_MAX = 30
DEFAULT_RSI_SHORT_MIN = 70
DEFAULT_ATR_PCT_HOT_LIMIT = 3.0
DEFAULT_TIMEOUT_BARS = 24
DEFAULT_COOLDOWN_BARS = 2


def _bar_close_time_ms(open_time_ms: int, tf: str) -> int:
    """봉 close time (ms). 4h → + 4*3600*1000 - 1."""
    tf = (tf or "4h").lower()
    if tf == "4h":
        bar_ms = 4 * 3600 * 1000
    elif tf == "1h":
        bar_ms = 3600 * 1000
    else:
        bar_ms = 4 * 3600 * 1000
    return open_time_ms + bar_ms - 1


@router.get("/data")
def dashboard_b_data(
    db: Session = Depends(get_db),
    symbol: str = Query("BTCUSDT", description="심볼"),
    tf: str = Query("4h", description="1h 또는 4h"),
    regime_override: str | None = Query(None, description="테스트용: RANGE/NEUTRAL/TREND 강제"),
):
    """
    B봇 대시보드용 JSON. 설계서 데이터 모델 그대로 반환.
    - 지표/신호는 Binance 최신 캔들 기준으로 계산.
    - 포지션/로그/리스크는 인메모리·DB 상태 사용.
    """
    status = get_status_from_db(db)
    risk = get_risk_from_db(db)
    position = get_position()
    logs = get_logs()

    # 지표 계산을 위해 캔들 조회 (실패 시 빈 구조)
    indicators = {}
    candle_time = None
    try:
        klines = fetch_klines(symbol, tf, limit=60)
        if klines:
            indicators = compute_bot_b_indicators(klines)
            last = klines[-1]
            candle_time = _bar_close_time_ms(int(last["open_time"]), tf)
    except Exception:
        pass

    close = indicators.get("close")
    bb = indicators.get("bb") or {}
    adx = indicators.get("adx")
    atr_pct = indicators.get("atrPct")

    # Regime: 중재봇 연동 전에는 ADX로 판단 (override 있으면 사용)
    if regime_override and regime_override.upper() in (REGIME_RANGE, REGIME_NEUTRAL, REGIME_TREND):
        regime = regime_override.upper()
    else:
        regime = get_regime_from_adx(adx, DEFAULT_ADX_RANGE_MAX)

    cooldown_remaining = 0  # TODO: 실제 쿨다운 바 남은 수 (상태에서 관리)
    trading_allowed = risk.get("tradingAllowed", True)
    blocked_reason = risk.get("tradeDisabledReason")

    long_checks = evaluate_long_checks(
        indicators,
        adx_range_max=DEFAULT_ADX_RANGE_MAX,
        rsi_long_max=DEFAULT_RSI_LONG_MAX,
        atr_pct_hot_limit=DEFAULT_ATR_PCT_HOT_LIMIT,
        cooldown_remaining_bars=cooldown_remaining,
        trading_allowed=trading_allowed,
    )
    short_checks = evaluate_short_checks(
        indicators,
        adx_range_max=DEFAULT_ADX_RANGE_MAX,
        rsi_short_min=DEFAULT_RSI_SHORT_MIN,
        atr_pct_hot_limit=DEFAULT_ATR_PCT_HOT_LIMIT,
        cooldown_remaining_bars=cooldown_remaining,
        trading_allowed=trading_allowed,
    )

    long_ready = regime == REGIME_RANGE and signal_ready(long_checks)
    short_ready = regime == REGIME_RANGE and signal_ready(short_checks)

    # ATR too hot (볼atility guard)
    atr_too_hot = atr_pct is not None and atr_pct >= DEFAULT_ATR_PCT_HOT_LIMIT

    return {
        "status": status,
        "regime": regime,
        "tf": tf,
        "symbol": symbol,
        "candleTime": candle_time,
        "indicators": {
            "close": close,
            "bb": {"upper": bb.get("upper"), "mid": bb.get("mid"), "lower": bb.get("lower")},
            "rsi": indicators.get("rsi"),
            "adx": adx,
            "atr": indicators.get("atr"),
            "atrPct": atr_pct,
            "bbWidth": indicators.get("bbWidth"),
            "bbZone": indicators.get("bbZone"),
            "rsiStatus": indicators.get("rsiStatus"),
        },
        "rules": {
            "adxRangeMax": DEFAULT_ADX_RANGE_MAX,
            "rsiLongMax": DEFAULT_RSI_LONG_MAX,
            "rsiShortMin": DEFAULT_RSI_SHORT_MIN,
            "atrPctHotLimit": DEFAULT_ATR_PCT_HOT_LIMIT,
            "cooldownRemainingBars": cooldown_remaining,
        },
        "signal": {
            "long": {
                "ready": long_ready,
                "entryType": "Immediate",
                "checks": checks_to_dict(long_checks),
                "score": signal_score(long_checks),
            },
            "short": {
                "ready": short_ready,
                "entryType": "Immediate",
                "checks": checks_to_dict(short_checks),
                "score": signal_score(short_checks),
            },
            "blockedReason": blocked_reason,
        },
        "position": position,
        "risk": {
            "dailyPnl": risk.get("dailyPnl", 0),
            "dailyLossLimit": risk.get("dailyLossLimit", -500),
            "consecutiveLosses": risk.get("consecutiveLosses", 0),
            "tradingAllowed": risk.get("tradingAllowed", True),
            "tradeDisabledReason": risk.get("tradeDisabledReason"),
        },
        "atrTooHot": atr_too_hot,
        "logs": logs[-20:],
    }


@router.get("/", response_class=HTMLResponse)
def dashboard_b_page():
    """B봇 대시보드 단일 페이지 (세로 1페이지, 섹션 A~F)."""
    return _dashboard_b_html()


def _dashboard_b_html() -> str:
    return """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>B봇 (평균회귀) 대시보드</title>
  <style>
    :root { --bg: #0f1419; --card: #1a2332; --text: #e6edf3; --muted: #8b949e; --green: #3fb950; --red: #f85149; --yellow: #d29922; }
    * { box-sizing: border-box; }
    body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 1rem; line-height: 1.5; }
    h1 { font-size: 1.25rem; margin: 0 0 1rem 0; }
    h2 { font-size: 0.95rem; margin: 0 0 0.5rem 0; color: var(--muted); }
    .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem 1.5rem; padding: 0.75rem 1rem; background: var(--card); border-radius: 8px; margin-bottom: 1rem; }
    .bar .item { display: flex; align-items: center; gap: 0.35rem; }
    .bar .label { color: var(--muted); font-size: 0.8rem; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
    .badge.running { background: var(--green); color: #000; }
    .badge.paused { background: var(--yellow); color: #000; }
    .badge.no-trade { background: var(--muted); color: var(--bg); }
    .badge.range { background: var(--green); color: #000; }
    .badge.neutral, .badge.trend { background: var(--muted); color: var(--bg); }
    .card { background: var(--card); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
    .card h2 { margin-bottom: 0.75rem; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    @media (max-width: 640px) { .grid2 { grid-template-columns: 1fr; } }
    .check { color: var(--green); }
    .cross { color: var(--red); }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.06); }
    th { color: var(--muted); font-weight: 500; }
    .log-type { font-size: 0.75rem; padding: 2px 6px; border-radius: 3px; }
    .log-type.BLOCKED { background: var(--red); color: #fff; }
    .log-type.ENTER, .log-type.EXIT { background: var(--green); color: #000; }
    .log-type.SIGNAL { background: var(--yellow); color: #000; }
    .log-type.REGIME_CHANGE { background: var(--muted); color: #000; }
    button { background: var(--muted); color: var(--bg); border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 0.85rem; }
    button:hover { filter: brightness(1.1); }
    button.danger { background: var(--red); color: #fff; }
    pre { margin: 0; font-size: 0.8rem; overflow: auto; }
    .muted { color: var(--muted); }
  </style>
</head>
<body>
  <h1>B봇 (평균회귀) 대시보드</h1>
  <div class="bar" id="topBar">
    <span class="item"><span class="label">Bot Status</span> <span id="status" class="badge">-</span></span>
    <span class="item"><span class="label">Regime</span> <span id="regime" class="badge">-</span></span>
    <span class="item"><span class="label">B봇 활성</span> <span id="botActive">-</span></span>
    <span class="item"><span class="label">Timeframe</span> <span id="tf">-</span></span>
    <span class="item"><span class="label">Symbol</span> <span id="symbol">-</span></span>
    <span class="item"><span class="label">Last Update</span> <span id="candleTime">-</span></span>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>B. Entry Signal — Long</h2>
      <p><strong>Signal Ready:</strong> <span id="longReady">-</span></p>
      <p><strong>Entry Type:</strong> <span id="longEntryType">-</span></p>
      <ul id="longChecks" style="list-style:none; padding:0; margin:0.5rem 0;"></ul>
      <p><strong>Signal Score:</strong> <span id="longScore">-</span></p>
    </div>
    <div class="card">
      <h2>B. Entry Signal — Short</h2>
      <p><strong>Signal Ready:</strong> <span id="shortReady">-</span></p>
      <p><strong>Entry Type:</strong> <span id="shortEntryType">-</span></p>
      <ul id="shortChecks" style="list-style:none; padding:0; margin:0.5rem 0;"></ul>
      <p><strong>Signal Score:</strong> <span id="shortScore">-</span></p>
    </div>
  </div>

  <div class="card">
    <h2>C. Indicators</h2>
    <p><strong>BB(20,2)</strong> Upper / Mid / Lower: <span id="bbVals">-</span></p>
    <p>Close vs Band: <span id="bbZone">-</span></p>
    <p><strong>RSI(14):</strong> <span id="rsiVal">-</span> <span id="rsiStatus" class="muted">-</span></p>
    <p><strong>ADX(14):</strong> <span id="adxVal">-</span> <span id="adxRange">-</span></p>
    <p><strong>ATR(14):</strong> <span id="atrVal">-</span> | ATR%: <span id="atrPct">-</span></p>
    <p><strong>Volatility Guard:</strong> ATR% too hot? <span id="atrTooHot">-</span></p>
  </div>

  <div class="card" id="positionCard" style="display:none;">
    <h2>D. Position</h2>
    <p>Position: <span id="posSide">-</span> | Entry: <span id="posEntry">-</span> | Size: <span id="posSize">-</span> | Leverage: <span id="posLeverage">-</span></p>
    <p>Unrealized PnL: <span id="posUpnl">-</span></p>
    <p>Stop Loss / Take Profit: <span id="posSlTp">-</span></p>
    <p>Timeout: bars in trade / bars left: <span id="posTimeout">-</span></p>
    <p>Exit Plan: TP at mid-band, SL at entry ± k×ATR, Time-out exit.</p>
    <p><button>Pause Bot</button> <button class="danger">Close Position</button></p>
  </div>

  <div class="card">
    <h2>E. Risk Manager</h2>
    <p>Daily PnL / Daily Loss Limit: <span id="riskDaily">-</span></p>
    <p>Consecutive Losses: <span id="riskConsec">-</span></p>
    <p><strong>Trade Disabled Reason:</strong> <span id="riskReason">-</span></p>
  </div>

  <div class="card">
    <h2>F. Decision Log (최근 20)</h2>
    <table><thead><tr><th>시간</th><th>타입</th><th>메시지</th></tr></thead><tbody id="logBody"></tbody></table>
  </div>

  <p><button onclick="load()">Refresh</button></p>

  <script>
    function load() {
      fetch('/dashboard/b/data?symbol=BTCUSDT&tf=4h')
        .then(r => r.json())
        .then(d => {
          document.getElementById('status').textContent = d.status || '-';
          document.getElementById('status').className = 'badge ' + (d.status || '').toLowerCase().replace('_','-');
          document.getElementById('regime').textContent = d.regime || '-';
          document.getElementById('regime').className = 'badge ' + (d.regime || '').toLowerCase();
          document.getElementById('botActive').textContent = d.regime === 'RANGE' ? 'B봇 활성' : '비활성';
          document.getElementById('botActive').style.color = d.regime === 'RANGE' ? 'var(--green)' : 'var(--muted)';
          document.getElementById('tf').textContent = d.tf || '-';
          document.getElementById('symbol').textContent = d.symbol || '-';
          document.getElementById('candleTime').textContent = d.candleTime ? new Date(d.candleTime).toISOString() : '-';

          var sig = d.signal || {};
          var long = sig.long || {};
          var short = sig.short || {};
          document.getElementById('longReady').textContent = long.ready ? 'YES' : 'NO';
          document.getElementById('longEntryType').textContent = long.entryType || 'Immediate';
          document.getElementById('shortReady').textContent = short.ready ? 'YES' : 'NO';
          document.getElementById('shortEntryType').textContent = short.entryType || 'Immediate';
          document.getElementById('longScore').textContent = long.score != null ? long.score : '-';
          document.getElementById('shortScore').textContent = short.score != null ? short.score : '-';

          function renderChecks(checks, ulId) {
            var names = { adx_ok: 'ADX < threshold', price_outside_bb: 'Price outside BB', rsi_ok: 'RSI condition', reentry_confirmed: 'Re-entry confirmed', cooldown_ok: 'Cooldown ok', risk_ok: 'Risk ok' };
            var ul = document.getElementById(ulId);
            if (!ul) return;
            ul.innerHTML = '';
            for (var k in (checks || {})) {
              var li = document.createElement('li');
              li.innerHTML = (checks[k] ? '<span class="check">✓</span>' : '<span class="cross">✗</span>') + ' ' + (names[k] || k);
              ul.appendChild(li);
            }
          }
          renderChecks(long.checks, 'longChecks');
          renderChecks(short.checks, 'shortChecks');

          var ind = d.indicators || {};
          var bb = ind.bb || {};
          document.getElementById('bbVals').textContent = [bb.upper, bb.mid, bb.lower].filter(Boolean).map(function(x){ return x != null ? Number(x).toFixed(2) : '-'; }).join(' / ');
          document.getElementById('bbZone').textContent = ind.bbZone === 'above_upper' ? 'Above upper' : ind.bbZone === 'below_lower' ? 'Below lower' : 'Inside';
          document.getElementById('rsiVal').textContent = ind.rsi != null ? ind.rsi.toFixed(1) : '-';
          document.getElementById('rsiStatus').textContent = ind.rsiStatus || '';
          document.getElementById('adxVal').textContent = ind.adx != null ? ind.adx.toFixed(1) : '-';
          document.getElementById('adxRange').textContent = (ind.adx != null && ind.adx < (d.rules && d.rules.adxRangeMax)) ? 'RANGE 가능' : 'RANGE 불가';
          document.getElementById('atrVal').textContent = ind.atr != null ? ind.atr.toFixed(4) : '-';
          document.getElementById('atrPct').textContent = ind.atrPct != null ? ind.atrPct.toFixed(2) + '%' : '-';
          document.getElementById('atrTooHot').textContent = d.atrTooHot ? 'YES' : 'NO';

          var pos = d.position;
          var posCard = document.getElementById('positionCard');
          if (pos && pos.side) {
            posCard.style.display = 'block';
            document.getElementById('posSide').textContent = pos.side;
            document.getElementById('posEntry').textContent = pos.entry != null ? pos.entry : '-';
            document.getElementById('posSize').textContent = pos.size != null ? pos.size : '-';
            document.getElementById('posLeverage').textContent = pos.leverage != null ? pos.leverage : '-';
            document.getElementById('posUpnl').textContent = (pos.upnl != null ? pos.upnl : '-') + (pos.upnlPct != null ? ' (' + pos.upnlPct + '%)' : '');
            document.getElementById('posSlTp').textContent = (pos.sl != null ? pos.sl : '-') + ' / ' + (pos.tp != null ? pos.tp : '-');
            document.getElementById('posTimeout').textContent = (pos.barsInTrade != null ? pos.barsInTrade : '-') + ' / ' + (pos.timeoutBarsLeft != null ? pos.timeoutBarsLeft : '-');
          } else {
            posCard.style.display = 'none';
          }

          var risk = d.risk || {};
          document.getElementById('riskDaily').textContent = (risk.dailyPnl != null ? risk.dailyPnl : 0) + ' / ' + (risk.dailyLossLimit != null ? risk.dailyLossLimit : '-');
          document.getElementById('riskConsec').textContent = risk.consecutiveLosses != null ? risk.consecutiveLosses : '0';
          document.getElementById('riskReason').textContent = risk.tradeDisabledReason || (d.signal && d.signal.blockedReason) || '-';

          var logs = d.logs || [];
          var tbody = document.getElementById('logBody');
          tbody.innerHTML = logs.slice().reverse().map(function(l) {
            return '<tr><td>' + (l.time ? new Date(l.time).toISOString() : '') + '</td><td><span class="log-type ' + (l.type || '') + '">' + (l.type || '') + '</span></td><td>' + (l.msg || '') + '</td></tr>';
          }).join('');
        })
        .catch(function(e) {
          document.getElementById('candleTime').textContent = 'Error: ' + e.message;
        });
    }
    load();
    setInterval(load, 30000);
  </script>
</body>
</html>"""
