"""
ORM 모델 — MariaDB 스키마(180.230.8.65 tradebot)와 동일한 컬럼명/타입 사용.
Python에서는 snake_case 속성으로 접근하고 DB 컬럼은 name= 으로 camelCase 매핑.
"""
import time
from sqlalchemy import (
    String, Integer, BigInteger, Boolean, Text, JSON,
    UniqueConstraint, Column, Numeric,
)
from app.database import Base


def _epoch_ms():
    return int(time.time() * 1000)


# ---------- 1) events ----------
class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("dedupKey", name="uk_events_dedup"),
        {"mysql_charset": "utf8mb4"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    tf = Column(String(10), nullable=False)
    close_time = Column(BigInteger, name="closeTime", nullable=False)
    received_at = Column(BigInteger, name="receivedAt", nullable=False)
    dedup_key = Column(String(128), name="dedupKey", nullable=False)
    raw = Column(JSON, name="raw")
    status = Column(String(16), default="pending")  # migration으로 추가됨

    def __init__(self, **kwargs):
        if "received_at" not in kwargs and "receivedAt" not in kwargs:
            kwargs["received_at"] = _epoch_ms()
        super().__init__(**kwargs)


# ---------- 2) candles ----------
class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("symbol", "tf", "openTime", name="uk_candles_symbol_tf_open"),
        {"mysql_charset": "utf8mb4"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    tf = Column(String(10), nullable=False)
    open_time = Column(BigInteger, name="openTime", nullable=False)
    o = Column(Numeric(20, 8), nullable=False)
    h = Column(Numeric(20, 8), nullable=False)
    l = Column(Numeric(20, 8), nullable=False)
    c = Column(Numeric(20, 8), nullable=False)
    v = Column(Numeric(28, 8), nullable=False)


# ---------- 3) param_sets ----------
class ParamSet(Base):
    __tablename__ = "param_sets"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    json = Column(JSON, nullable=False)
    active = Column(Boolean, default=False)
    updated_at = Column(BigInteger, name="updatedAt", nullable=False)

    def __init__(self, **kwargs):
        if "updated_at" not in kwargs and "updatedAt" not in kwargs:
            kwargs["updated_at"] = _epoch_ms()
        super().__init__(**kwargs)


# ---------- 4) signals ----------
class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    tf = Column(String(10), nullable=False)
    close_time = Column(BigInteger, name="closeTime", nullable=False)
    action = Column(String(32), nullable=False)
    indicators_snapshot = Column(JSON, name="indicatorsSnapshot")
    params_snapshot = Column(JSON, name="paramsSnapshot")
    created_at = Column(BigInteger, name="createdAt", nullable=False)

    def __init__(self, **kwargs):
        if "created_at" not in kwargs and "createdAt" not in kwargs:
            kwargs["created_at"] = _epoch_ms()
        super().__init__(**kwargs)


# ---------- 5) orders ----------
class Order(Base):
    __tablename__ = "orders"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    tf = Column(String(10))
    order_id = Column(BigInteger, name="orderId")
    type = Column(String(32), nullable=False)
    side = Column(String(8), nullable=False)
    qty = Column(Numeric(28, 8), nullable=False)
    price = Column(Numeric(20, 8))
    status = Column(String(32), nullable=False)
    raw = Column(JSON, name="raw")
    created_at = Column(BigInteger, name="createdAt", nullable=False)

    def __init__(self, **kwargs):
        if "created_at" not in kwargs and "createdAt" not in kwargs:
            kwargs["created_at"] = _epoch_ms()
        if "order_id" in kwargs and isinstance(kwargs["order_id"], str):
            try:
                kwargs["order_id"] = int(kwargs["order_id"])
            except ValueError:
                pass
        super().__init__(**kwargs)


# ---------- 6) positions ----------
class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("symbol", name="uk_positions_symbol"),
        {"mysql_charset": "utf8mb4"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    side = Column(String(8), nullable=False)
    size = Column(Numeric(28, 8), nullable=False)
    entry_price = Column(Numeric(20, 8), name="entryPrice", nullable=False)
    stop_price = Column(Numeric(20, 8), name="stopPrice")  # 고정 스탑 (진입 시 1회 설정)
    updated_at = Column(BigInteger, name="updatedAt", nullable=False)

    def __init__(self, **kwargs):
        if "updated_at" not in kwargs and "updatedAt" not in kwargs:
            kwargs["updated_at"] = _epoch_ms()
        super().__init__(**kwargs)


# ---------- app_settings (킬스위치 등, 프로젝트용) ----------
class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False)
    value = Column(String(256))
