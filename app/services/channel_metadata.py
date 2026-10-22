"""Preserve template metadata by stable Telegram ID when directory names change."""

import json
from functools import lru_cache
from pathlib import Path

from app.database.repositories.settings_repo import SettingsRepository


@lru_cache(maxsize=1)
def template_metadata() -> dict:
    path = Path(__file__).parents[1] / "reports" / "channel_report_reference.json"
    return json.loads(path.read_text(encoding="utf-8"))


def metadata_key(telegram_id: int) -> str:
    return f"channel_report:{telegram_id}"


async def preserve_metadata(session, telegram_id: int, *usernames) -> None:
    repo = SettingsRepository(session)
    key = metadata_key(telegram_id)
    if await repo.get_value(key) is not None:
        return
    for username in usernames:
        metadata = template_metadata().get((username or "").casefold())
        if metadata:
            await repo.set_value(key, json.dumps(metadata, ensure_ascii=False))
            return
