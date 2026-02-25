"""Runtime trade enable/disable (kill switch) stored in DB."""
from app.database import SessionLocal
from app.models import AppSetting
from app.config import get_settings


def get_trade_enabled() -> bool:
    """Return trade_enabled from DB if set, else from env."""
    try:
        db = SessionLocal()
        row = db.query(AppSetting).filter(AppSetting.key == "trade_enabled").first()
        db.close()
        if row and row.value:
            return row.value.lower() in ("true", "1", "yes")
    except Exception:
        pass
    return get_settings().trade_enabled


def set_trade_enabled(enabled: bool) -> None:
    """Set trade_enabled in DB."""
    db = SessionLocal()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == "trade_enabled").first()
        if row:
            row.value = "true" if enabled else "false"
        else:
            db.add(AppSetting(key="trade_enabled", value="true" if enabled else "false"))
        db.commit()
    finally:
        db.close()
