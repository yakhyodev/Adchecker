from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.channel import Channel
from app.database.repositories.channel_repo import ChannelRepository
from app.telegram_client.client import (
    TelegramClientManager,
    telegram_client_manager,
    ChannelNotFoundError,
    ChannelAccessDeniedError,
)
from app.core.logging import logger


class ChannelService:
    def __init__(
        self,
        session: AsyncSession,
        tg_client: TelegramClientManager = telegram_client_manager,
    ):
        self.session = session
        self.tg_client = tg_client
        self.channel_repo = ChannelRepository(session)

    async def add_channel(self, raw_url_or_username: str) -> Tuple[Channel, bool]:
        """Validates channel with Telethon and registers it in the database.
        Returns: (Channel, is_new: bool)
        """
        # First resolve with Telegram
        info = await self.tg_client.resolve_channel(raw_url_or_username)
        tg_id = info["telegram_channel_id"]

        # Check existing in DB
        existing = await self.channel_repo.get_by_tg_id(tg_id)
        if existing and not existing.is_deleted:
            # Already exists and active
            return existing, False

        channel = await self.channel_repo.create(
            telegram_channel_id=tg_id,
            title=info["title"],
            username=info["username"],
            url=info["url"],
        )
        return channel, True

    async def get_channel_by_id(self, channel_id: int) -> Optional[Channel]:
        return await self.channel_repo.get_by_id(channel_id)

    async def list_active_channels(self) -> List[Channel]:
        return await self.channel_repo.get_all_active()

    async def list_all_channels(self) -> List[Channel]:
        return await self.channel_repo.get_all(include_deleted=False)

    async def pause_monitoring(self, channel_id: int) -> Optional[Channel]:
        return await self.channel_repo.set_active(channel_id, False)

    async def resume_monitoring(self, channel_id: int) -> Optional[Channel]:
        return await self.channel_repo.set_active(channel_id, True)

    async def remove_channel(self, channel_id: int) -> bool:
        """Soft deletes the channel so historical data is preserved."""
        return await self.channel_repo.soft_delete(channel_id)

    async def set_cpm_price(
        self, channel_id: int, price: Optional[float]
    ) -> Optional[Channel]:
        return await self.channel_repo.update_cpm_price(channel_id, price)

    async def check_channel_health(self, channel_id: int) -> Dict[str, Any]:
        """Verifies if the channel is currently reachable via Telegram."""
        channel = await self.get_channel_by_id(channel_id)
        if not channel:
            return {"status": "error", "message": "Kanal bazadan topilmadi"}

        try:
            target = channel.username or channel.telegram_channel_id
            info = await self.tg_client.resolve_channel(str(target))
            return {
                "status": "ok",
                "title": info["title"],
                "username": info["username"],
                "telegram_id": info["telegram_channel_id"],
                "monitoring_active": channel.is_active,
            }
        except ChannelAccessDeniedError:
            return {
                "status": "access_denied",
                "message": "Kanal yopiq yoki akkaunt chiqarib yuborilgan",
            }
        except ChannelNotFoundError:
            return {
                "status": "not_found",
                "message": "Kanal Telegramda topilmadi (ehtimol o'chirilgan yoki username o'zgargan)",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
