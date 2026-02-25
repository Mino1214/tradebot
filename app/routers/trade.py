from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.trade_switch import get_trade_enabled, set_trade_enabled
from app.config import get_settings

router = APIRouter(prefix="/trade", tags=["trade"])


class TradeSwitchBody(BaseModel):
    secret: str


def require_admin(secret: str) -> None:
    if not secret or secret != get_settings().admin_secret:
        raise HTTPException(status_code=401, detail="Invalid admin secret")


@router.post("/enable")
def trade_enable(body: TradeSwitchBody):
    """Turn on order execution (kill switch off)."""
    require_admin(body.secret)
    set_trade_enabled(True)
    return {"ok": True, "trade_enabled": True}


@router.post("/disable")
def trade_disable(body: TradeSwitchBody):
    """Turn off order execution (kill switch)."""
    require_admin(body.secret)
    set_trade_enabled(False)
    return {"ok": True, "trade_enabled": False}


@router.get("/status")
def trade_status():
    """Current trade enabled status."""
    return {"trade_enabled": get_trade_enabled()}
