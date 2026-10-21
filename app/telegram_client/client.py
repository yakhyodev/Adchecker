import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, AsyncGenerator, Tuple
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    UsernameNotOccupiedError,
    UsernameInvalidError,
    ChannelInvalidError,
)
from telethon.tl.types import Channel as TelethonChannel, Message, MessageEmpty

from app.core.config import settings
from app.core.logging import logger
from app.telegram_client.parser import (
    normalize_channel_input,
    is_ad_message,
    extract_media_type,
    extract_reactions_count,
    build_post_url,
)


class TelegramClientError(Exception):
    """Base exception for Telegram client errors."""

    pass


class ChannelNotFoundError(TelegramClientError):
    """Raised when channel does not exist."""

    pass


class ChannelAccessDeniedError(TelegramClientError):
    """Raised when user account has no access to the channel."""

    pass


class TelegramFloodWaitException(TelegramClientError):
    """Raised when Telegram limits requests."""

    def __init__(self, seconds: int):
        self.seconds = seconds
        super().__init__(f"Telegram FloodWait: {seconds} soniya kuting")


class TelegramClientManager:
    """Manages the MTProto Telethon client connection and message retrieval."""

    def __init__(
        self,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        session_string: Optional[str] = None,
        session_name: Optional[str] = None,
    ):
        self.api_id = api_id or settings.TELEGRAM_API_ID
        self.api_hash = api_hash or settings.TELEGRAM_API_HASH
        self.session_string = (
            session_string
            if session_string is not None
            else settings.TELEGRAM_SESSION_STRING
        )
        self.session_name = session_name or settings.TELEGRAM_SESSION_NAME

        if self.session_string:
            session = StringSession(self.session_string)
        else:
            session = self.session_name

        # If api_id or api_hash is missing, use safe dummy values until configured
        valid_api_id = self.api_id if self.api_id else 123456
        valid_api_hash = (
            self.api_hash
            if self.api_hash
            else "0123456789abcdef0123456789abcdef"
        )
        self.client = TelegramClient(session, valid_api_id, valid_api_hash)
        self._is_started = False

    async def start(self) -> None:
        """Connects to Telegram MTProto servers."""
        if not self._is_started:
            try:
                await self.client.connect()
                self._is_started = True
                logger.info("Telethon client ulandi")
            except Exception as e:
                logger.error(f"Telethon ulanishda xatolik: {e}")
                raise

    async def disconnect(self) -> None:
        """Disconnects the client."""
        if self._is_started:
            await self.client.disconnect()
            self._is_started = False
            logger.info("Telethon client uzildi")

    async def is_authorized(self) -> bool:
        """Checks if the MTProto account is logged in."""
        if not self._is_started:
            await self.start()
        try:
            return await self.client.is_user_authorized()
        except Exception as e:
            logger.error(f"Avtorizatsiyani tekshirishda xatolik: {e}")
            return False

    async def resolve_channel(self, raw_input: str) -> Dict[str, Any]:
        """Resolves channel info and validates access.
        Returns dict with telegram_channel_id, title, username, url.
        """
        if not self._is_started:
            await self.start()

        target = normalize_channel_input(raw_input)
        if not target:
            raise ChannelNotFoundError("Kanal havolasi yoki username bo'sh")

        try:
            entity = await self.client.get_entity(target)
            if not isinstance(entity, TelethonChannel):
                raise ChannelNotFoundError("Ko'rsatilgan havola kanal emas")

            # Format full telegram channel id with -100 prefix if needed
            raw_id = entity.id
            if not str(raw_id).startswith("-100"):
                tg_channel_id = int(f"-100{raw_id}")
            else:
                tg_channel_id = raw_id

            username = entity.username
            title = entity.title
            canonical_url = (
                f"https://t.me/{username}"
                if username
                else f"https://t.me/c/{raw_id}"
            )

            return {
                "telegram_channel_id": tg_channel_id,
                "title": title,
                "username": username,
                "url": canonical_url,
                "entity": entity,
            }

        except (UsernameNotOccupiedError, UsernameInvalidError, ChannelInvalidError):
            raise ChannelNotFoundError(f"Kanal topilmadi: {raw_input}")
        except ChannelPrivateError:
            raise ChannelAccessDeniedError(
                f"Kanal yopiq yoki akkaunt kirish huquqiga ega emas: {raw_input}"
            )
        except FloodWaitError as e:
            raise TelegramFloodWaitException(e.seconds)
        except Exception as e:
            logger.error(f"Kanalni aniqlashda xatolik ({raw_input}): {e}")
            raise TelegramClientError(f"Kanalni tekshirib bo'lmadi: {str(e)}")

    async def scan_channel_ads(
        self,
        entity: any,
        keywords: List[str],
        limit: Optional[int] = None,
        min_date_utc: Optional[datetime] = None,
        min_id: Optional[int] = None,
        batch_size: int = 100,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Scans channel messages for ads matching keywords.
        Yields message data dictionaries.
        """
        if not self._is_started:
            await self.start()

        entity_id = getattr(entity, "id", None)
        entity_username = getattr(entity, "username", None)

        try:
            # We iterate over messages in the channel
            async for message in self.client.iter_messages(
                entity,
                limit=limit,
                offset_date=None,
                min_id=min_id or 0,
            ):
                if not message or isinstance(message, MessageEmpty):
                    continue

                msg_date = message.date
                if msg_date and msg_date.tzinfo is None:
                    msg_date = msg_date.replace(tzinfo=timezone.utc)

                # If message is older than min_date_utc, stop scan
                if min_date_utc and msg_date and msg_date < min_date_utc:
                    break

                text = message.text or message.message or ""
                entities = getattr(message, "entities", None)

                # Check if it contains advertising keywords
                if is_ad_message(text, entities=entities, keywords=keywords):
                    post_url = build_post_url(entity_id, entity_username, message.id)
                    media_type = extract_media_type(message)
                    reactions = extract_reactions_count(message)

                    yield {
                        "message_id": message.id,
                        "post_url": post_url,
                        "post_text": text,
                        "posted_at": msg_date,
                        "media_type": media_type,
                        "views": message.views,
                        "reactions": reactions,
                        "forwards": message.forwards,
                    }

        except FloodWaitError as e:
            logger.warning(f"Scan paytida FloodWait: {e.seconds}s")
            raise TelegramFloodWaitException(e.seconds)
        except Exception as e:
            logger.error(f"Xabarlarni skanerlashda xatolik: {e}")
            raise

    async def fetch_message_stats(
        self,
        entity: any,
        message_id: int,
    ) -> Tuple[bool, Optional[int], Optional[int], Optional[int]]:
        """Fetches current stats of a specific message.
        Returns: (is_available, views, reactions, forwards).
        If message is deleted, is_available=False.
        """
        if not self._is_started:
            await self.start()

        try:
            messages = await self.client.get_messages(entity, ids=[message_id])
            if not messages or not messages[0] or isinstance(messages[0], MessageEmpty):
                return False, None, None, None

            msg = messages[0]
            reactions = extract_reactions_count(msg)
            return True, msg.views, reactions, msg.forwards

        except FloodWaitError as e:
            raise TelegramFloodWaitException(e.seconds)
        except Exception as e:
            logger.error(f"Post statistikasini olishda xatolik (msg={message_id}): {e}")
            # A failed request does not prove the message was deleted.
            raise TelegramClientError("Post statistikasini olib bo'lmadi") from e


# Global client instance
telegram_client_manager = TelegramClientManager()
