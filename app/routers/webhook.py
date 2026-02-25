from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.services.ingest import (
    validate_secret,
    dedup_key,
    is_duplicate,
    enqueue_event,
    EVENT_CANDLE_CLOSED,
)

router = APIRouter(prefix="/webhook", tags=["webhook"])


class TVWebhookPayload(BaseModel):
    symbol: str
    tf: str  # 1h, 4h
    event: str = EVENT_CANDLE_CLOSED
    time: int  # bar close time (ms)
    secret: str

    class Config:
        extra = "allow"  # allow extra fields from TV


@router.post("/tv")
def webhook_tv(payload: TVWebhookPayload, request: Request, db: Session = Depends(get_db)):
    if not validate_secret(payload.secret):
        raise HTTPException(status_code=401, detail="Invalid secret")

    if payload.event != EVENT_CANDLE_CLOSED:
        raise HTTPException(status_code=400, detail=f"Unsupported event: {payload.event}")

    # dedup: same symbol+tf+closeTime only once
    dk = dedup_key(payload.symbol, payload.tf, payload.time)
    if is_duplicate(db, dk):
        return {"ok": True, "status": "duplicate", "dedup_key": dk}

    raw = payload.model_dump(mode="json")
    event = enqueue_event(
        db,
        symbol=payload.symbol,
        tf=payload.tf,
        close_time=payload.time,
        raw=raw,
    )
    if not event:
        return {"ok": True, "status": "duplicate", "dedup_key": dk}

    return {"ok": True, "status": "queued", "event_id": event.id, "dedup_key": dk}
