from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

settings = get_settings()
if not (settings.database_url and "mysql" in settings.database_url):
    raise ValueError("DATABASE_URL must be set to MariaDB (e.g. mysql+pymysql://user:pass@host/db?charset=utf8mb4)")

engine = create_engine(
    settings.database_url,
    connect_args={"charset": "utf8mb4"},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401
    from app.models import AppSetting
    # events/candles/signals/orders/positions/param_sets는 마이그레이션으로 이미 존재 가정. app_settings만 생성.
    Base.metadata.create_all(bind=engine, tables=[AppSetting.__table__])
