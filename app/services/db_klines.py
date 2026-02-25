"""
DB에 저장된 캔들 테이블(예: btc4h)에서 klines 로드.
btc4h: (symbol, openTime, o, h, l, c, v, closeTime, createdAt)
"""
from sqlalchemy import text
from app.database import engine

# symbol + tf → 테이블명 (필요 시 확장)
TABLE_MAP = {
    ("BTCUSDT", "1h"): "btc1h",
    ("btcusdt", "1h"): "btc1h",
    ("BTCUSDT", "4h"): "btc4h",
    ("btcusdt", "4h"): "btc4h",
    ("ETHUSDT", "1h"): "eth1h",
    ("ethusdt", "1h"): "eth1h",
    ("ETHUSDT", "4h"): "eth4h",
    ("ethusdt", "4h"): "eth4h",
}


def get_table_name(symbol: str, tf: str) -> str | None:
    key = (symbol.upper(), tf.lower())
    if key in TABLE_MAP:
        return TABLE_MAP[key]
    if (symbol.lower(), tf.lower()) in TABLE_MAP:
        return TABLE_MAP[(symbol.lower(), tf.lower())]
    return None


def load_klines_from_db(symbol: str, tf: str, limit: int | None = None) -> list[dict]:
    """
    btc4h 등 DB 캔들 테이블에서 openTime 오름차순으로 로드.
    반환 형식: [{"open_time": ms, "o": float, "h": float, "l": float, "c": float, "v": float}, ...]
    """
    table = get_table_name(symbol, tf)
    if not table:
        raise ValueError(f"Unknown symbol/tf for DB table: {symbol} {tf}. TABLE_MAP에 추가하세요.")

    # 테이블의 symbol 컬럼 값 (대문자 통일: BTCUSDT, ETHUSDT 등)
    sym_val = symbol.upper()
    with engine.connect() as conn:
        sql = f"SELECT openTime, o, h, l, c, v FROM {table} WHERE symbol = :sym ORDER BY openTime ASC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        result = conn.execute(text(sql), {"sym": sym_val})
        rows = result.fetchall()

    return [
        {
            "open_time": int(row[0]),
            "o": float(row[1]),
            "h": float(row[2]),
            "l": float(row[3]),
            "c": float(row[4]),
            "v": float(row[5]),
        }
        for row in rows
    ]
