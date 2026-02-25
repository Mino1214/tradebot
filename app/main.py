from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.database import init_db
from app.routers import webhook, params, trade, dashboard, dashboard_b, admin_c_bot, admin_unified


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    # shutdown if needed


app = FastAPI(title="TradeBot", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index():
    """진입 화면: 대시보드/관리자 페이지 링크."""
    return """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TradeBot — 진입</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 640px; }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
    .sub { color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }
    ul { list-style: none; padding: 0; }
    li { margin-bottom: 0.75rem; }
    a { display: block; padding: 0.75rem 1rem; background: #f0f0f0; border-radius: 8px; text-decoration: none; color: #111; font-weight: 500; }
    a:hover { background: #e0e0e0; }
    .label { font-size: 0.8rem; color: #666; margin-top: 0.25rem; }
    .note { margin-top: 2rem; padding: 1rem; background: #f9f9f9; border-radius: 8px; font-size: 0.85rem; color: #555; }
  </style>
</head>
<body>
  <h1>TradeBot</h1>
  <p class="sub">ETH 단일 · C-A-B 구조 · 진입 화면</p>
  <ul>
    <li><a href="/dashboard/">📊 A봇 대시보드 (추세)</a><span class="label">포지션, 시그널, 주문, 이벤트, 파라미터</span></li>
    <li><a href="/dashboard/b/">📈 B봇 대시보드 (평균회귀)</a><span class="label">Regime, 신호, 지표, 포지션, 리스크, 로그</span></li>
    <li><a href="/admin/c-bot/">🎛️ C봇 관리자 (중재)</a><span class="label">Regime, Active Strategy, Risk Gate, 지표 10항목</span></li>
    <li><a href="/admin/unified">🖥️ 통합 관리자 (ETH 단일)</a><span class="label">Run/Pause, New Entry, Emergency, 포지션, 한글 리포트</span></li>
    <li><a href="/health">❤️ Health</a><span class="label">API 상태</span></li>
  </ul>
  <div class="note">
    <strong>백테스트 실행 방법</strong><br>
    백테스트는 웹이 아니라 <strong>터미널</strong>에서 실행합니다. 프로젝트 루트에서:<br>
    <code>python -m app.backtest ETHUSDT 4h --source db --capital 1000 -o trades.json</code><br>
    (Binance 캔들: <code>--source binance</code>)<br>
    자세한 옵션: <code>docs/BACKTEST.md</code> 참고.
  </div>
  <div class="note">
    <strong>진입 URL</strong>: <code>http://127.0.0.1:8080/</code> (이 페이지).
  </div>
</body>
</html>"""


app.include_router(webhook.router)
app.include_router(params.router)
app.include_router(trade.router)
app.include_router(dashboard.router)
app.include_router(dashboard_b.router)
app.include_router(admin_c_bot.router)
app.include_router(admin_unified.router)


@app.get("/health")
def health():
    return {"status": "ok"}
