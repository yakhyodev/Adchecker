from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram Bot
    BOT_TOKEN: str = "123456:TEST_BOT_TOKEN"
    ADMIN_IDS: Union[str, List[int]] = []

    # Telethon MTProto Client
    TELEGRAM_API_ID: int = 123456
    TELEGRAM_API_HASH: str = "0123456789abcdef0123456789abcdef"
    TELEGRAM_SESSION_STRING: str = ""
    TELEGRAM_SESSION_NAME: str = "imkon_session"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/imkon_ads"

    # Search & Monitoring
    DEFAULT_SEARCH_KEYWORD: str = "@imkonhelpbot"
    SEARCH_KEYWORDS: Union[str, List[str]] = ["@imkonhelpbot"]

    # Scheduler intervals (in minutes/hours)
    SCAN_INTERVAL_MINUTES: int = 60
    RECENT_STATS_UPDATE_INTERVAL_HOURS: int = 3
    OLD_STATS_UPDATE_INTERVAL_HOURS: int = 24
    ENABLE_AUTO_MONITORING: bool = True
    NOTIFY_ADMINS_ON_NEW_AD: bool = True

    # General
    TIMEZONE: str = "Asia/Tashkent"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return []

    @field_validator("SEARCH_KEYWORDS", mode="before")
    @classmethod
    def parse_search_keywords(cls, v):
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return ["@imkonhelpbot"]
            return [x.strip() for x in v.split(",") if x.strip()]
        return ["@imkonhelpbot"]


settings = Settings()
