"""Dashboard API: positions, events, orders, signals for UI."""
from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Position, Event, Order, Signal
from app.services.params import get_active_params
from app.services.trade_switch import get_trade_enabled

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/data")
def dashboard_data(db: Session = Depends(get_db)):
    """JSON for dashboard: positions, recent events, orders, signals, params."""
    positions = db.query(Position).filter(Position.size > 0).all()
    events = db.query(Event).order_by(Event.id.desc()).limit(50).all()
    orders = db.query(Order).order_by(Order.id.desc()).limit(50).all()
    signals = db.query(Signal).order_by(Signal.id.desc()).limit(50).all()
    params = get_active_params(db)
    return {
        "trade_enabled": get_trade_enabled(),
        "positions": [{"symbol": p.symbol, "side": p.side, "size": p.size, "entry_price": p.entry_price} for p in positions],
        "events": [{"id": e.id, "symbol": e.symbol, "tf": e.tf, "close_time": e.close_time, "status": e.status} for e in events],
        "orders": [{"id": o.id, "order_id": o.order_id, "symbol": o.symbol, "type": o.type, "side": o.side, "qty": o.qty, "price": o.price, "status": o.status} for o in orders],
        "signals": [{"id": s.id, "symbol": s.symbol, "tf": s.tf, "action": s.action, "close_time": s.close_time} for s in signals],
        "params": params,
    }


@router.get("/", response_class=HTMLResponse)
def dashboard_page():
    """Simple HTML dashboard that fetches /dashboard/data."""
    return """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>TradeBot Dashboard</title>
  <style>
    body { font-family: system-ui; margin: 1rem; }
    h1 { margin-bottom: 0.5rem; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
    .badge.on { background: #22c55e; color: white; }
    .badge.off { background: #ef4444; color: white; }
    section { margin-top: 1.5rem; }
    table { border-collapse: collapse; width: 100%; max-width: 800px; }
    th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
    th { background: #f5f5f5; }
    pre { background: #f5f5f5; padding: 10px; overflow: auto; font-size: 12px; }
  </style>
</head>
<body>
  <h1>TradeBot Dashboard</h1>
  <p>Trade: <span id="trade-status" class="badge off">-</span></p>
  <button onclick="load()">Refresh</button>
  <section>
    <h2>Positions</h2>
    <table id="positions"><thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th></tr></thead><tbody></tbody></table>
  </section>
  <section>
    <h2>Recent Signals</h2>
    <table id="signals"><thead><tr><th>ID</th><th>Symbol</th><th>TF</th><th>Action</th><th>Close time</th></tr></thead><tbody></tbody></table>
  </section>
  <section>
    <h2>Recent Orders</h2>
    <table id="orders"><thead><tr><th>OrderId</th><th>Symbol</th><th>Type</th><th>Side</th><th>Qty</th><th>Price</th><th>Status</th></tr></thead><tbody></tbody></table>
  </section>
  <section>
    <h2>Recent Events</h2>
    <table id="events"><thead><tr><th>ID</th><th>Symbol</th><th>TF</th><th>Close time</th><th>Status</th></tr></thead><tbody></tbody></table>
  </section>
  <section>
    <h2>Params</h2>
    <pre id="params"></pre>
  </section>
  <script>
    function load() {
      fetch('/dashboard/data').then(r => r.json()).then(d => {
        document.getElementById('trade-status').textContent = d.trade_enabled ? 'ON' : 'OFF';
        document.getElementById('trade-status').className = 'badge ' + (d.trade_enabled ? 'on' : 'off');
        const tb = (id, rows, fn) => {
          const t = document.querySelector(id + ' tbody');
          if (t) t.innerHTML = rows.map(fn).join('');
        };
        tb('#positions', d.positions, p => '<tr><td>'+p.symbol+'</td><td>'+p.side+'</td><td>'+p.size+'</td><td>'+p.entry_price+'</td></tr>');
        tb('#signals', d.signals, s => '<tr><td>'+s.id+'</td><td>'+s.symbol+'</td><td>'+s.tf+'</td><td>'+s.action+'</td><td>'+s.close_time+'</td></tr>');
        tb('#orders', d.orders, o => '<tr><td>'+o.order_id+'</td><td>'+o.symbol+'</td><td>'+o.type+'</td><td>'+o.side+'</td><td>'+o.qty+'</td><td>'+o.price+'</td><td>'+o.status+'</td></tr>');
        tb('#events', d.events, e => '<tr><td>'+e.id+'</td><td>'+e.symbol+'</td><td>'+e.tf+'</td><td>'+e.close_time+'</td><td>'+e.status+'</td></tr>');
        document.getElementById('params').textContent = JSON.stringify(d.params, null, 2);
      });
    }
    load();
  </script>
</body>
</html>"""
