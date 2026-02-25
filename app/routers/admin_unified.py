"""
Unified 관리자 대시보드 (ETH 단일 보수형).
- GET /admin/state       : 관리자 UI용 상태 JSON (controls/meta/botA/botB/position/bot_opinions)
- GET /admin/unified     : 단일 HTML 페이지 (Top Banner, Action Bar, Cards, Reporter, Timeline 골조)
- POST /admin/control/...: Run/Pause, New Entry, Emergency, Mode, Leverage, Risk, Close Position 제어
"""
from fastapi import APIRouter, Depends, Body
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.admin_state import (
    get_unified_admin_state,
    set_run_state,
    set_new_entry,
    set_emergency,
    set_mode,
    set_leverage,
    set_risk_text,
)
from app.services.execution import execute_exit
from app.models import Position


router = APIRouter(prefix="/admin", tags=["admin-unified"])


@router.get("/state")
def admin_state(db: Session = Depends(get_db)):
    """ETH 단일 관리자 대시보드용 상태 JSON."""
    return get_unified_admin_state(db)


@router.post("/control/run")
def admin_control_run(db: Session = Depends(get_db), body: dict = Body(...)):
    """Run/Pause 제어."""
    run_state = (body or {}).get("run_state", "RUNNING")
    reason = (body or {}).get("reason")
    running = run_state.upper() == "RUNNING"
    set_run_state(db, running, reason)
    db.commit()
    return {"ok": True}


@router.post("/control/new-entry")
def admin_control_new_entry(db: Session = Depends(get_db), body: dict = Body(...)):
    """New Entry ON/OFF 제어."""
    enabled = bool((body or {}).get("enabled", True))
    reason = (body or {}).get("reason")
    set_new_entry(db, enabled, reason)
    db.commit()
    return {"ok": True}


@router.post("/control/emergency")
def admin_control_emergency(db: Session = Depends(get_db), body: dict = Body(...)):
    """Emergency Stop ON/OFF 제어."""
    active = bool((body or {}).get("active", True))
    reason = (body or {}).get("reason")
    set_emergency(db, active, reason)
    if active:
        # 비상 모드에서는 즉시 거래 중지
        set_run_state(db, False, reason or "Emergency Stop")
    db.commit()
    return {"ok": True}


@router.post("/control/mode")
def admin_control_mode(db: Session = Depends(get_db), body: dict = Body(...)):
    """Mode (BACKTEST/PAPER/LIVE) 설정."""
    mode = (body or {}).get("mode", "PAPER")
    reason = (body or {}).get("reason")
    set_mode(db, str(mode).upper(), reason)
    db.commit()
    return {"ok": True}


@router.post("/control/leverage")
def admin_control_leverage(db: Session = Depends(get_db), body: dict = Body(...)):
    """레버리지 설정 (다음 진입부터 적용)."""
    leverage = str((body or {}).get("value", ""))
    reason = (body or {}).get("reason")
    set_leverage(db, leverage, reason)
    db.commit()
    return {"ok": True}


@router.post("/control/risk")
def admin_control_risk(db: Session = Depends(get_db), body: dict = Body(...)):
    """Risk% / Max positions 등의 텍스트 설정 (파라미터 문자열)."""
    risk_text = str((body or {}).get("value", ""))
    reason = (body or {}).get("reason")
    set_risk_text(db, risk_text, reason)
    db.commit()
    return {"ok": True}


@router.post("/control/close-position")
def admin_control_close_position(db: Session = Depends(get_db), body: dict = Body(default=None)):
    """현재 ETHUSDT 포지션 강제 종료 (MARKET exit)."""
    reason = (body or {}).get("reason") if body else None
    pos = (
        db.query(Position)
        .filter(Position.symbol == "ETHUSDT", Position.size > 0)
        .first()
    )
    if not pos:
        return {"ok": False, "error": "No open ETHUSDT position"}
    side = pos.side  # LONG / SHORT
    ok, _pnl = execute_exit(db, "ETHUSDT", side)
    if ok:
        text = f"ClosePosition side={side}"
        if reason:
            text += f" ({reason})"
        # last_control_action에 반영
        set_risk_text(db, text[:200], None)
        db.commit()
        return {"ok": True}
    return {"ok": False, "error": "Exit failed"}


@router.get("/unified", response_class=HTMLResponse)
def admin_unified_page():
    """통합 관리자 UI 골조 페이지."""
    return _html()


def _html() -> str:
    return """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ETH 단일 자동매매 관리자</title>
  <style>
    :root {
      --bg: #0f1419;
      --card: #161b22;
      --text: #e6edf3;
      --muted: #8b949e;
      --accent: #58a6ff;
      --danger: #f85149;
      --safe: #3fb950;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    main {
      max-width: 1200px;
      margin: 0 auto;
      padding: 1rem;
    }
    h1 { font-size: 1.4rem; margin: 0; }
    .sub { color: var(--muted); font-size: 0.85rem; margin-top: 0.25rem; }
    .banner {
      margin-top: 1rem;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      background: #1c2128;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 0.5rem 1rem;
      align-items: center;
      font-size: 0.9rem;
    }
    .banner-section { display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; }
    .pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .pill-run { background: var(--safe); color: #000; }
    .pill-pause { background: var(--muted); color: #000; }
    .pill-mode { background: #21262d; color: var(--text); }
    .pill-blocked { background: var(--danger); color: #fff; }
    .pill-allowed { background: var(--safe); color: #000; }
    .action-bar {
      margin-top: 0.75rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      justify-content: space-between;
      align-items: center;
    }
    .actions-safe, .actions-danger {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
    }
    button {
      border: none;
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 0.8rem;
      cursor: pointer;
      background: #30363d;
      color: var(--text);
    }
    button.safe { background: var(--safe); color: #000; }
    button.danger { background: var(--danger); color: #fff; }
    button:disabled { opacity: 0.5; cursor: default; }
    .layout {
      margin-top: 1rem;
      display: grid;
      grid-template-columns: 1.2fr 1.2fr;
      gap: 0.75rem;
    }
    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
    }
    .card {
      background: var(--card);
      border-radius: 8px;
      padding: 0.75rem 1rem;
      font-size: 0.85rem;
    }
    .card h2 {
      margin: 0 0 0.5rem 0;
      font-size: 0.9rem;
      color: var(--muted);
    }
    .row { display: flex; justify-content: space-between; gap: 0.5rem; margin: 0.25rem 0; }
    .label { color: var(--muted); font-size: 0.78rem; }
    .value { font-weight: 500; }
    .muted { color: var(--muted); }
    .reporter {
      margin-top: 0.75rem;
      background: #161b22;
      border-radius: 8px;
      padding: 0.75rem 1rem;
      font-size: 0.85rem;
    }
    .reporter-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.5rem;
    }
    .timeline {
      margin-top: 0.75rem;
      background: #0d1117;
      border-radius: 8px;
      padding: 0.75rem 1rem;
      font-size: 0.82rem;
    }
    .timeline-item {
      border-bottom: 1px solid #21262d;
      padding: 0.35rem 0;
    }
    .timeline-item:last-child { border-bottom: none; }
    .time { color: var(--muted); font-size: 0.75rem; }
    .type { font-weight: 600; margin-right: 0.25rem; }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>ETHUSDT 자동매매 관리자</h1>
      <p class="sub">C-A-B 구조 · 멀티 TF(1D/4H/1H) · 보수형</p>
    </header>

    <section id="top-banner" class="banner">
      <div class="banner-section">
        <span id="banner-run" class="pill pill-pause">상태 정보 없음</span>
        <span id="banner-mode" class="pill pill-mode">MODE ?</span>
        <span id="banner-entry" class="pill pill-allowed">신규 진입 상태 ?</span>
      </div>
      <div class="banner-section">
        <span class="label">이유</span>
        <span id="banner-reason" class="value muted">정보 없음</span>
      </div>
    </section>

    <section class="action-bar">
      <div class="actions-safe">
        <button id="btn-run" class="safe">Run</button>
        <button id="btn-pause">Pause</button>
        <button id="btn-new-entry">New Entry ON/OFF</button>
        <button id="btn-mode">Mode: -</button>
        <button id="btn-leverage">Leverage 설정</button>
        <button id="btn-risk">Risk% / Max positions</button>
      </div>
      <div class="actions-danger">
        <button id="btn-emergency" class="danger">Emergency Stop</button>
        <button id="btn-close-pos" class="danger">Close Position</button>
      </div>
    </section>

    <section class="layout">
      <article class="card" id="card-controls">
        <h2>Controls 상태</h2>
        <div class="row"><span class="label">Run state</span><span class="value" id="c-run">정보 없음</span></div>
        <div class="row"><span class="label">Mode</span><span class="value" id="c-mode">정보 없음</span></div>
        <div class="row"><span class="label">New Entry</span><span class="value" id="c-entry">정보 없음</span></div>
        <div class="row"><span class="label">Emergency</span><span class="value" id="c-emer">정보 없음</span></div>
        <div class="row"><span class="label">Leverage</span><span class="value" id="c-lev">정보 없음</span></div>
        <div class="row"><span class="label">Risk</span><span class="value" id="c-risk">정보 없음</span></div>
        <div class="row"><span class="label">Last control</span><span class="value" id="c-last">정보 없음</span></div>
      </article>

      <article class="card" id="card-cbot">
        <h2>C봇 상태 (중재)</h2>
        <div class="row"><span class="label">Regime / Candidate</span><span class="value" id="m-regime">정보 없음</span></div>
        <div class="row"><span class="label">Active Strategy</span><span class="value" id="m-strategy">정보 없음</span></div>
        <div class="row"><span class="label">Trading Allowed</span><span class="value" id="m-allowed">정보 없음</span></div>
        <div class="row"><span class="label">Blocked Reason</span><span class="value" id="m-block">정보 없음</span></div>
        <div class="row"><span class="label">Confirm / Cooldown</span><span class="value" id="m-switch">정보 없음</span></div>
        <div class="row"><span class="label">지표</span><span class="value" id="m-indicators">정보 없음</span></div>
        <div class="row"><span class="label">Risk (계좌)</span><span class="value" id="m-risk">정보 없음</span></div>
      </article>

      <article class="card" id="card-abot">
        <h2>A봇 상태 (추세)</h2>
        <div class="row"><span class="label">Enabled / Allow Entry</span><span class="value" id="a-state">정보 없음</span></div>
        <div class="row"><span class="label">Signal</span><span class="value" id="a-signal">정보 없음</span></div>
        <div class="row"><span class="label">Signal Ready</span><span class="value" id="a-ready">정보 없음</span></div>
        <div class="row"><span class="label">Health</span><span class="value" id="a-health">정보 없음</span></div>
        <div class="row"><span class="label">Last Action</span><span class="value" id="a-last">정보 없음</span></div>
      </article>

      <article class="card" id="card-bbot">
        <h2>B봇 상태 (평균회귀)</h2>
        <div class="row"><span class="label">Enabled / Allow Entry</span><span class="value" id="b-state">정보 없음</span></div>
        <div class="row"><span class="label">Signal</span><span class="value" id="b-signal">정보 없음</span></div>
        <div class="row"><span class="label">Signal Ready</span><span class="value" id="b-ready">정보 없음</span></div>
        <div class="row"><span class="label">Blocked Reason</span><span class="value" id="b-block">정보 없음</span></div>
        <div class="row"><span class="label">Last Action</span><span class="value" id="b-last">정보 없음</span></div>
      </article>

      <article class="card" id="card-position">
        <h2>Position</h2>
        <div id="pos-empty" class="muted">현재 포지션 없음</div>
        <div id="pos-detail" style="display:none;">
          <div class="row"><span class="label">Side / Size / Lev</span><span class="value" id="p-main">정보 없음</span></div>
          <div class="row"><span class="label">Entry / Mark</span><span class="value" id="p-price">정보 없음</span></div>
          <div class="row"><span class="label">PnL</span><span class="value" id="p-pnl">정보 없음</span></div>
          <div class="row"><span class="label">SL / TP</span><span class="value" id="p-sltp">정보 없음</span></div>
          <div class="row"><span class="label">Owner / Policy</span><span class="value" id="p-owner">정보 없음</span></div>
          <div class="row"><span class="label">Bars</span><span class="value" id="p-bars">정보 없음</span></div>
        </div>
      </article>
    </section>

    <section class="reporter">
      <div class="reporter-header">
        <span class="label">상황 요약 (한글 리포트)</span>
        <button id="btn-copy">복사</button>
      </div>
      <div id="report-text" class="value">
        상태 정보를 불러오는 중입니다...
      </div>
    </section>

    <section class="timeline">
      <div class="row" style="justify-content: space-between;">
        <span class="label">최근 Activity (예: 의사결정/차단/버튼조작/체결)</span>
        <button id="btn-refresh" style="font-size:0.75rem;">새로고침</button>
      </div>
      <div id="timeline-list">
        <div class="timeline-item"><span class="time">-</span> <span class="type">INFO</span> 최근 이벤트 정보 없음 (Logs 화면에서 상세 조회 가능)</div>
      </div>
    </section>
  </main>

  <script>
    let LAST_STATE = null;

    function fetchState() {
      return fetch('/admin/state').then(r => r.json());
    }

    function fmtBool(v) {
      if (v === null || v === undefined) return '정보 없음';
      return v ? 'ON' : 'OFF';
    }

    function fmtPct(v) {
      if (v === null || v === undefined) return '정보 없음';
      return v.toFixed(2) + '%';
    }

    function updateUI(d) {
      LAST_STATE = d;
      const controls = d.controls || {};
      const meta = d.meta || {};
      const botA = d.botA || {};
      const botB = d.botB || {};
      const pos = d.position || null;

      // Top banner
      const run = controls.run_state || '정보 없음';
      const mode = controls.mode || '정보 없음';
      const newEntry = controls.new_entry_enabled;
      const emerStop = controls.emergency_stop;
      const tradingAllowed = meta.trading_allowed;
      const blockedReason = meta.blocked_reason || '';

      const bannerRun = document.getElementById('banner-run');
      bannerRun.textContent = run;
      bannerRun.className = 'pill ' + (run === 'RUNNING' ? 'pill-run' : 'pill-pause');

      const bannerMode = document.getElementById('banner-mode');
      bannerMode.textContent = 'MODE ' + mode;

      const bannerEntry = document.getElementById('banner-entry');
      let entryText = '신규 진입 상태 정보 없음';
      let entryClass = 'pill-allowed';
      if (emerStop) {
        entryText = '신규 진입 차단 (Emergency)';
        entryClass = 'pill-blocked';
      } else if (newEntry === false) {
        entryText = '신규 진입 차단 (운영자 설정)';
        entryClass = 'pill-blocked';
      } else if (tradingAllowed === false) {
        entryText = '신규 진입 차단 (C봇/Risk)';
        entryClass = 'pill-blocked';
      } else if (newEntry === true && tradingAllowed === true) {
        entryText = '신규 진입 허용';
        entryClass = 'pill-allowed';
      }
      bannerEntry.textContent = entryText;
      bannerEntry.className = 'pill ' + entryClass;

      const bannerReason = document.getElementById('banner-reason');
      if (emerStop) {
        bannerReason.textContent = meta.emergency_reason || 'Emergency Stop 활성화';
      } else if (newEntry === false) {
        bannerReason.textContent = '운영자 New Entry OFF 설정';
      } else if (tradingAllowed === false && blockedReason) {
        bannerReason.textContent = blockedReason;
      } else {
        bannerReason.textContent = blockedReason || '차단 사유 없음';
      }

      // Controls card
      document.getElementById('c-run').textContent = run;
      document.getElementById('c-mode').textContent = mode;
      document.getElementById('c-entry').textContent = newEntry === undefined ? '정보 없음' : (newEntry ? 'ON' : 'OFF');
      document.getElementById('c-emer').textContent = emerStop ? 'ON' : 'OFF';
      document.getElementById('c-lev').textContent = controls.leverage_setting || '정보 없음';
      document.getElementById('c-risk').textContent = controls.risk_setting || '정보 없음';
      document.getElementById('c-last').textContent = controls.last_control_action || '정보 없음';

      // C-bot card
      const regime = meta.regime || '정보 없음';
      const cand = meta.candidate_regime || '정보 없음';
      document.getElementById('m-regime').textContent = regime + ' / ' + cand;
      document.getElementById('m-strategy').textContent = meta.active_strategy || '정보 없음';
      document.getElementById('m-allowed').textContent = fmtBool(tradingAllowed);
      document.getElementById('m-block').textContent = blockedReason || '차단 사유 없음';
      const cc = meta.confirm_count != null ? meta.confirm_count : '정보 없음';
      const cu = meta.cooldown_until ? new Date(meta.cooldown_until).toISOString() : '정보 없음';
      document.getElementById('m-switch').textContent = cc + ' / ' + cu;
      const mind = meta.indicators || {};
      const adx = mind.adx != null ? mind.adx.toFixed(1) : '정보 없음';
      const atrp = mind.atr_pct != null ? mind.atr_pct.toFixed(2) + '%' : '정보 없음';
      const slope = mind.ema_slope_pct != null ? mind.ema_slope_pct.toFixed(3) + '%' : '정보 없음';
      document.getElementById('m-indicators').textContent = 'ADX ' + adx + ' · ATR% ' + atrp + ' · Slope ' + slope;
      const mrisk = meta.risk || {};
      const dPnl = mrisk.daily_pnl_pct != null ? mrisk.daily_pnl_pct + '%' : '정보 없음';
      const cons = mrisk.consecutive_losses != null ? mrisk.consecutive_losses : '정보 없음';
      const openPos = mrisk.open_position_exists ? '포지션 있음' : '포지션 없음';
      document.getElementById('m-risk').textContent = dPnl + ' / 연속손실 ' + cons + ' / ' + openPos;

      // A bot (Allow Entry는 meta/controls로 계산)
      const aAllow = (meta.active_strategy === 'A') && tradingAllowed && !emerStop && (newEntry !== false);
      document.getElementById('a-state').textContent =
        (botA.enabled ? 'Enabled' : 'Disabled') + ' / Allow: ' + (aAllow ? 'YES' : 'NO');
      document.getElementById('a-signal').textContent = botA.signal || '정보 없음';
      document.getElementById('a-ready').textContent = botA.signal_ready === null || botA.signal_ready === undefined ? '정보 없음' : (botA.signal_ready ? 'YES' : 'NO');
      document.getElementById('a-health').textContent = botA.health || '정보 없음';
      document.getElementById('a-last').textContent = botA.last_action || '정보 없음';

      // B bot (Allow Entry는 meta/controls로 계산)
      const bAllow = (meta.active_strategy === 'B') && tradingAllowed && !emerStop && (newEntry !== false);
      document.getElementById('b-state').textContent =
        (botB.enabled ? 'Enabled' : 'Disabled') + ' / Allow: ' + (bAllow ? 'YES' : 'NO');
      document.getElementById('b-signal').textContent = botB.signal || '정보 없음';
      document.getElementById('b-ready').textContent = botB.signal_ready === null || botB.signal_ready === undefined ? '정보 없음' : (botB.signal_ready ? 'YES' : 'NO');
      document.getElementById('b-block').textContent = botB.blocked_reason || '정보 없음';
      document.getElementById('b-last').textContent = botB.last_action || '정보 없음';

      // Position
      const posEmpty = document.getElementById('pos-empty');
      const posDetail = document.getElementById('pos-detail');
      if (!pos) {
        posEmpty.style.display = 'block';
        posDetail.style.display = 'none';
      } else {
        posEmpty.style.display = 'none';
        posDetail.style.display = 'block';
        document.getElementById('p-main').textContent =
          (pos.side || '-') + ' / ' + (pos.size != null ? pos.size : '-') + ' / lev ' + (pos.leverage != null ? pos.leverage : '-');
        document.getElementById('p-price').textContent =
          'Entry ' + (pos.entry != null ? pos.entry : '-') + ' / Mark ' + (pos.mark != null ? pos.mark : '-');
        document.getElementById('p-pnl').textContent =
          pos.upnl != null ? pos.upnl : '정보 없음';
        document.getElementById('p-sltp').textContent =
          'SL ' + (pos.sl != null ? pos.sl : '-') + ' / TP ' + (pos.tp != null ? pos.tp : '-');
        document.getElementById('p-owner').textContent =
          (pos.owner_bot || '정보 없음') + ' / ' + (pos.management_policy || '정책 정보 없음');
        document.getElementById('p-bars').textContent =
          (pos.bars_in_trade != null ? pos.bars_in_trade : '-') + ' / ' + (pos.timeout_bars_left != null ? pos.timeout_bars_left : '-');
      }

      // Reporter text (간단 규칙 기반)
      const rep = document.getElementById('report-text');
      let lines = [];
      lines.push('시스템은 ' + (mode || '정보 없음') + ' 모드에서 ' + (run === 'RUNNING' ? '실행 중' : '일시정지 상태') + '입니다.');
      if (emerStop) {
        lines.push('Emergency Stop이 활성화되어 모든 신규 진입이 차단되었습니다.');
      } else if (newEntry === false) {
        lines.push('운영자 설정으로 신규 진입이 임시 차단된 상태입니다.');
      } else if (tradingAllowed === false) {
        lines.push('C봇/Risk Gate에 의해 신규 진입이 차단된 상태입니다. 사유: ' + (blockedReason || '정보 없음') + '.');
      } else {
        lines.push('현재 C봇은 신규 진입을 허용하고 있습니다.');
      }
      lines.push('Regime는 ' + (regime || '정보 없음') + ' 이며, 활성 전략은 ' + (meta.active_strategy || 'NONE') + ' 입니다.');
      rep.textContent = lines.join(' ');
    }

    function copyReport() {
      const txt = document.getElementById('report-text').textContent || '';
      navigator.clipboard.writeText(txt).catch(() => {});
    }

    document.getElementById('btn-copy').addEventListener('click', copyReport);
    document.getElementById('btn-refresh').addEventListener('click', () => {
      fetchState().then(updateUI);
    });

    // 버튼 핸들러 (간단한 fetch + 재로딩)
    document.getElementById('btn-run').addEventListener('click', () => {
      if (!confirm('Run 상태로 전환하시겠습니까?')) return;
      fetch('/admin/control/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_state: 'RUNNING' })
      }).then(() => fetchState().then(updateUI));
    });

    document.getElementById('btn-pause').addEventListener('click', () => {
      if (!confirm('Pause 상태로 전환하시겠습니까?')) return;
      const reason = prompt('일시정지 사유를 입력하세요 (선택):') || null;
      fetch('/admin/control/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_state: 'PAUSED', reason })
      }).then(() => fetchState().then(updateUI));
    });

    document.getElementById('btn-new-entry').addEventListener('click', () => {
      const current = LAST_STATE && LAST_STATE.controls && LAST_STATE.controls.new_entry_enabled;
      const next = !(current === true);
      let reason = null;
      if (!next) {
        reason = prompt('New Entry를 OFF로 전환하는 사유를 입력하세요 (선택):') || null;
      }
      fetch('/admin/control/new-entry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next, reason })
      }).then(() => fetchState().then(updateUI));
    });

    document.getElementById('btn-emergency').addEventListener('click', () => {
      const current = LAST_STATE && LAST_STATE.controls && LAST_STATE.controls.emergency_stop;
      const next = !(current === true);
      if (next) {
        if (!confirm('Emergency Stop을 활성화하시겠습니까? 모든 신규 진입이 차단됩니다.')) return;
        const reason = prompt('Emergency 사유를 입력하세요 (필수):') || 'Emergency Stop';
        fetch('/admin/control/emergency', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ active: true, reason })
        }).then(() => fetchState().then(updateUI));
      } else {
        if (!confirm('Emergency Stop을 해제하시겠습니까?')) return;
        const reason = prompt('Emergency 해제 사유를 입력하세요 (선택):') || null;
        fetch('/admin/control/emergency', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ active: false, reason })
        }).then(() => fetchState().then(updateUI));
      }
    });

    document.getElementById('btn-close-pos').addEventListener('click', () => {
      if (!LAST_STATE || !LAST_STATE.position) {
        alert('현재 ETHUSDT 포지션이 없습니다.');
        return;
      }
      if (!confirm('현재 ETHUSDT 포지션을 MARKET으로 종료하시겠습니까?')) return;
      const reason = prompt('강제 청산 사유를 입력하세요 (필수):') || 'Manual close';
      fetch('/admin/control/close-position', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason })
      }).then(r => r.json()).then(res => {
        if (!res.ok) {
          alert('종료 실패: ' + (res.error || 'unknown error'));
        }
        fetchState().then(updateUI);
      });
    });

    document.getElementById('btn-mode').addEventListener('click', () => {
      const current = LAST_STATE && LAST_STATE.controls && LAST_STATE.controls.mode;
      const next = prompt('모드를 입력하세요 (BACKTEST / PAPER / LIVE). 현재: ' + (current || '-'), current || 'PAPER');
      if (!next) return;
      fetch('/admin/control/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: next })
      }).then(() => fetchState().then(updateUI));
    });

    document.getElementById('btn-leverage').addEventListener('click', () => {
      const current = LAST_STATE && LAST_STATE.controls && LAST_STATE.controls.leverage_setting;
      const value = prompt('레버리지 값을 입력하세요 (예: 3x). 현재: ' + (current || '-'), current || '');
      if (!value) return;
      fetch('/admin/control/leverage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value })
      }).then(() => fetchState().then(updateUI));
    });

    document.getElementById('btn-risk').addEventListener('click', () => {
      const current = LAST_STATE && LAST_STATE.controls && LAST_STATE.controls.risk_setting;
      const value = prompt('Risk 설정 텍스트를 입력하세요 (예: risk=1%,max_pos=1). 현재: ' + (current || '-'), current || '');
      if (!value) return;
      fetch('/admin/control/risk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value })
      }).then(() => fetchState().then(updateUI));
    });

    // 초기 로드
    fetchState().then(updateUI).catch(() => {
      document.getElementById('report-text').textContent = '상태 정보를 불러오지 못했습니다.';
    });
  </script>
</body>
</html>"""

