from sqlalchemy.orm import Session
from app.models import Event
from app.config import get_settings

EVENT_CANDLE_CLOSED = "CANDLE_CLOSED"


def dedup_key(symbol: str, tf: str, close_time: int) -> str:
    return f"{symbol}_{tf}_{close_time}"


def is_duplicate(db: Session, dedup_key_str: str) -> bool:
    return db.query(Event).filter(Event.dedup_key == dedup_key_str).first() is not None


def validate_secret(secret: str) -> bool:
    return bool(secret and secret == get_settings().webhook_secret)


def enqueue_event(
    db: Session,
    symbol: str,
    tf: str,
    close_time: int,
    raw: dict,
) -> Event | None:
    dk = dedup_key(symbol, tf, close_time)
    if is_duplicate(db, dk):
        return None
    event = Event(
        symbol=symbol,
        tf=tf,
        close_time=close_time,
        dedup_key=dk,
        raw=raw if isinstance(raw, dict) else {"raw": str(raw)},
        status="pending",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
