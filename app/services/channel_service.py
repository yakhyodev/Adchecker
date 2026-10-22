import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.channel import Channel
from app.database.repositories.channel_repo import ChannelRepository
from app.telegram_client.client import (
    TelegramClientManager,
    telegram_client_manager,
    ChannelNotFoundError,
    ChannelAccessDeniedError,
    TelegramFloodWaitException,
)
from app.core.logging import logger
from app.services.channel_metadata import preserve_metadata


@dataclass
class ChannelAddResult:
    supplied: str
    status: str
    title: str = ""
    telegram_id: int | None = None
    detail: str = ""


def split_channel_inputs(raw: str) -> list[str]:
    return [part for part in re.split(r"[\s,;]+", raw.strip()) if part]


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
            await self.refresh_metadata(existing, info)
            return existing, False

        try:
            # The unique Telegram-ID constraint also protects simultaneous bulk adds.
            async with self.session.begin_nested():
                channel = await self.channel_repo.create(
                    telegram_channel_id=tg_id, title=info["title"],
                    username=info["username"], url=info["url"],
                )
                await self.refresh_metadata(channel, info)
        except IntegrityError:
            channel = await self.channel_repo.get_by_tg_id(tg_id)
            if channel is None:
                raise
            await self.refresh_metadata(channel, info)
            return channel, False
        return channel, True

    async def refresh_metadata(self, channel: Channel, info: dict) -> None:
        if info["telegram_channel_id"] != channel.telegram_channel_id:
            raise ValueError("Telegram channel ID mismatch")
        await preserve_metadata(self.session, channel.telegram_channel_id, channel.username, info["username"])
        channel.title = info["title"]
        channel.username = info["username"]
        channel.url = info["url"]
        await self.session.flush()

    async def add_channels(self, raw: str) -> list[ChannelAddResult]:
        inputs = split_channel_inputs(raw)
        results = []
        for index, item in enumerate(inputs):
            try:
                async with self.session.begin_nested():
                    channel, added = await self.add_channel(item)
                # A completed item survives cancellation of a later network request;
                # do not hold the directory transaction open for the entire batch.
                await self.session.commit()
                results.append(ChannelAddResult(item, "added" if added else "duplicate",
                                               channel.title, channel.telegram_channel_id))
            except TelegramFloodWaitException as exc:
                results.extend(ChannelAddResult(value, "error", detail=f"Telegram cheklovi: {exc.seconds} soniyadan keyin qayta yuboring")
                               for value in inputs[index:])
                break
            except ChannelNotFoundError:
                results.append(ChannelAddResult(item, "error", detail="Kanal topilmadi"))
            except ChannelAccessDeniedError:
                results.append(ChannelAddResult(item, "error", detail="Kanalga kirish huquqi yo'q"))
            except Exception as exc:
                logger.warning("Kanalni qo'shib bo'lmadi: %s", type(exc).__name__)
                results.append(ChannelAddResult(item, "error", detail="Kanalni tekshirib yoki saqlab bo'lmadi"))
        return results

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
            info = await self.tg_client.resolve_channel(str(channel.telegram_channel_id))
            await self.refresh_metadata(channel, info)
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
                "message": "Kanal Telegramda topilmadi yoki akkauntga ko'rinmayapti",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
