"""
Binance USDT-M Futures API client.
Base URL: https://fapi.binance.com (prod) or https://testnet.binancefuture.com (testnet)
"""
import time
import hmac
import hashlib
from urllib.parse import urlencode
from typing import Any
import requests
from app.config import get_settings

# Binance interval for klines: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w
TF_TO_INTERVAL = {"1h": "1h", "4h": "4h", "1m": "1m", "15m": "15m", "30m": "30m", "2h": "2h", "6h": "6h", "12h": "12h", "1d": "1d"}

RECV_WINDOW = 10000


def _sign(query: dict, secret: str) -> str:
    return hmac.new(secret.encode(), urlencode(query).encode(), hashlib.sha256).hexdigest()


def _headers() -> dict:
    return {"X-MBX-APIKEY": get_settings().binance_api_key}


def _timestamp() -> int:
    return int(time.time() * 1000)


def _request_signed(method: str, path: str, params: dict | None = None, data: dict | None = None) -> dict:
    """Signed request for private endpoints."""
    base = get_settings().binance_base_url.rstrip("/")
    url = f"{base}{path}"
    secret = get_settings().binance_api_secret
    if not secret:
        raise ValueError("BINANCE_API_SECRET not set")
    ts = _timestamp()
    query = dict(params or {})
    query.update(data or {})
    query["timestamp"] = ts
    query["recvWindow"] = RECV_WINDOW
    query["signature"] = _sign(query, secret)
    if method == "GET":
        r = requests.get(url, params=query, headers=_headers(), timeout=15)
    else:
        r = requests.post(url, data=query, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def get_klines(symbol: str, interval: str, limit: int = 200, end_time: int | None = None) -> list[list]:
    """
    GET fapi/v1/klines
    Returns list of [open_time, o, h, l, c, v, close_time, ...]
    """
    base = get_settings().binance_base_url.rstrip("/")
    url = f"{base}/fapi/v1/klines"
    params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": min(limit, 1500)}
    if end_time is not None:
        params["endTime"] = end_time
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_klines(symbol: str, tf: str, limit: int) -> list[dict]:
    """
    Fetch klines and return list of dicts with open_time, o, h, l, c, v.
    Uses Binance interval (e.g. 1h, 4h).
    """
    interval = TF_TO_INTERVAL.get(tf.lower(), tf)
    raw = get_klines(symbol, interval, limit=limit)
    return [
        {
            "open_time": row[0],
            "o": float(row[1]),
            "h": float(row[2]),
            "l": float(row[3]),
            "c": float(row[4]),
            "v": float(row[5]),
        }
        for row in raw
    ]


def fetch_latest_closed_kline(symbol: str, tf: str) -> dict | None:
    """
    Fetch the most recent *closed* candle only.
    Binance returns oldest-first; last element is current (possibly open). So latest closed = second-to-last.
    """
    interval = TF_TO_INTERVAL.get(tf.lower(), tf)
    raw = get_klines(symbol, interval, limit=2)
    if len(raw) < 2:
        return None
    # Latest closed = second-to-last (index 0 when limit=2)
    row = raw[0]
    return {
        "open_time": row[0],
        "o": float(row[1]),
        "h": float(row[2]),
        "l": float(row[3]),
        "c": float(row[4]),
        "v": float(row[5]),
        "close_time": row[6],
    }


# ---------- Private (signed) APIs ----------


def get_exchange_info(symbol: str | None = None) -> dict:
    """GET fapi/v1/exchangeInfo. Optional symbol filter."""
    base = get_settings().binance_base_url.rstrip("/")
    params = {}
    if symbol:
        params["symbol"] = symbol
    r = requests.get(f"{base}/fapi/v1/exchangeInfo", params=params or None, timeout=15)
    r.raise_for_status()
    return r.json()


def get_symbol_filters(symbol: str) -> dict:
    """Step size, tick size, min notional for symbol."""
    data = get_exchange_info(symbol)
    info = next((s for s in data.get("symbols", []) if s["symbol"] == symbol), None)
    if not info:
        raise ValueError(f"Symbol {symbol} not in exchangeInfo")
    filters = {f["filterType"]: f for f in info.get("filters", [])}
    step = 0.001
    tick = 0.01
    min_notional = 0
    if "LOT_SIZE" in filters:
        step = float(filters["LOT_SIZE"].get("stepSize", "0.001"))
    if "PRICE_FILTER" in filters:
        tick = float(filters["PRICE_FILTER"].get("tickSize", "0.01"))
    if "MIN_NOTIONAL" in filters:
        min_notional = float(filters["MIN_NOTIONAL"].get("notional", "0"))
    return {"stepSize": step, "tickSize": tick, "minNotional": min_notional}


def get_mark_price(symbol: str) -> float:
    """GET fapi/v1/premiumIndex. Returns mark price for symbol."""
    base = get_settings().binance_base_url.rstrip("/")
    r = requests.get(f"{base}/fapi/v1/premiumIndex", params={"symbol": symbol}, timeout=10)
    r.raise_for_status()
    data = r.json()
    return float(data.get("markPrice", 0))


def get_account() -> dict:
    """GET fapi/v2/account. Returns balances and positions."""
    return _request_signed("GET", "/fapi/v2/account")


def get_position_risk(symbol: str | None = None) -> list[dict]:
    """GET fapi/v2/positionRisk. Returns list of position info."""
    params = {}
    if symbol:
        params["symbol"] = symbol
    return _request_signed("GET", "/fapi/v2/positionRisk", params=params)


def set_leverage(symbol: str, leverage: int) -> dict:
    """POST fapi/v1/leverage."""
    return _request_signed("POST", "/fapi/v1/leverage", data={"symbol": symbol, "leverage": leverage})


def set_margin_type(symbol: str, margin_type: str = "ISOLATED") -> dict:
    """POST fapi/v1/marginType. May fail if position open; call when no position."""
    return _request_signed("POST", "/fapi/v1/marginType", data={"symbol": symbol, "marginType": margin_type})


def create_order(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float | None = None,
    price: float | None = None,
    stop_price: float | None = None,
    reduce_only: bool = False,
) -> dict:
    """
    POST fapi/v1/order.
    order_type: MARKET, STOP_MARKET, etc.
    For STOP_MARKET: pass stopPrice and quantity; reduce_only=True for stop-loss.
    """
    data = {"symbol": symbol, "side": side, "type": order_type}
    if quantity is not None:
        data["quantity"] = quantity
    if price is not None:
        data["price"] = price
    if stop_price is not None:
        data["stopPrice"] = stop_price
    if reduce_only:
        data["reduceOnly"] = "true"
    return _request_signed("POST", "/fapi/v1/order", data=data)
