from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    webhook_secret: str = ""
    admin_secret: str = ""
    binance_base_url: str = "https://fapi.binance.com"
    binance_api_key: str = ""
    binance_api_secret: str = ""
    # MariaDB 필수: mysql+pymysql://user:password@host/dbname?charset=utf8mb4
    database_url: str = "mysql+pymysql://mynolab_user:mynolab2026@host/dbname?charset=utf8mb4"
    trade_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
