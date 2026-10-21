import json
from datetime import datetime, timezone
from typing import Optional, List, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.setting import Setting
from app.core.config import settings as app_settings


class SettingsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        stmt = select(Setting).where(Setting.key == key)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if record:
            return record.value
        return default

    async def set_value(self, key: str, value: str) -> None:
        stmt = select(Setting).where(Setting.key == key)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if record:
            record.value = value
            record.updated_at = datetime.now(timezone.utc)
        else:
            new_record = Setting(
                key=key, value=value, updated_at=datetime.now(timezone.utc)
            )
            self.session.add(new_record)
        await self.session.flush()

    async def get_all(self) -> Dict[str, str]:
        stmt = select(Setting)
        res = await self.session.execute(stmt)
        return {item.key: item.value for item in res.scalars().all()}

    async def get_search_keywords(self) -> List[str]:
        val = await self.get_value("search_keywords")
        if val:
            try:
                data = json.loads(val)
                if isinstance(data, list) and data:
                    return [str(x).strip() for x in data if str(x).strip()]
            except Exception:
                return [x.strip() for x in val.split(",") if x.strip()]
        return (
            app_settings.SEARCH_KEYWORDS
            if isinstance(app_settings.SEARCH_KEYWORDS, list)
            else [app_settings.DEFAULT_SEARCH_KEYWORD]
        )

    async def set_search_keywords(self, keywords: List[str]) -> None:
        clean = [k.strip() for k in keywords if k.strip()]
        if not clean:
            clean = [app_settings.DEFAULT_SEARCH_KEYWORD]
        await self.set_value("search_keywords", json.dumps(clean))

    async def is_auto_monitoring_enabled(self) -> bool:
        val = await self.get_value("enable_auto_monitoring")
        if val is not None:
            return val.lower() in ("true", "1", "yes")
        return app_settings.ENABLE_AUTO_MONITORING

    async def set_auto_monitoring_enabled(self, enabled: bool) -> None:
        await self.set_value("enable_auto_monitoring", "true" if enabled else "false")
