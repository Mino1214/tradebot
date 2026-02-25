from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import ParamSet
from app.services.params import get_active_params, DEFAULT_PARAMS
from app.services.trade_switch import get_trade_enabled, set_trade_enabled
from app.config import get_settings

router = APIRouter(prefix="/params", tags=["params"])


class UpdateParamsBody(BaseModel):
    name: str | None = None
    secret: str
    params: dict | None = None  # param set overrides (e.g. adx_min, entry_len)


def require_admin(secret: str) -> None:
    if not secret or secret != get_settings().admin_secret:
        raise HTTPException(status_code=401, detail="Invalid admin secret")


@router.get("/current")
def get_current_params(db: Session = Depends(get_db)):
    """Return currently active param set (for display / dashboard)."""
    params = get_active_params(db)
    return {"trade_enabled": get_trade_enabled(), "params": params}


@router.post("/update")
def update_params(body: UpdateParamsBody, db: Session = Depends(get_db)):
    """Update active param set. Requires admin secret."""
    require_admin(body.secret)
    if body.params is None:
        return {"ok": True, "message": "No changes"}
    name = body.name or "default"
    active_row = db.query(ParamSet).filter(ParamSet.active == True).first()
    if active_row:
        active_row.active = False
        db.flush()
    new_row = ParamSet(name=name, json={**DEFAULT_PARAMS, **body.params}, active=True)
    db.add(new_row)
    db.commit()
    return {"ok": True, "params": get_active_params(db)}
