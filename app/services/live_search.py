"""On-demand Telegram searches. Only the channel list comes from the database."""

import json
from pathlib import Path
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from time import monotonic
from typing import Awaitable, Callable

from telethon.errors import ChannelPrivateError, FloodWaitError
from telethon.tl.types import MessageEmpty

from app.core.logging import logger
from app.core.timezone import get_date_range_boundaries_utc, get_tashkent_now
from app.database.repositories.channel_repo import ChannelRepository
from app.telegram_client.client import telegram_client_manager
from app.telegram_client.parser import build_post_url, is_ad_message


@dataclass(frozen=True)
class SearchChannel:
    id: int
    telegram_id: int
    title: str
    url: str
    username: str | None
    region: str = ""
    contact: str = ""


async def load_search_channels(session, channel_id: int | None = None) -> list[SearchChannel]:
    channels = await ChannelRepository(session).get_all_active()
    reference = json.loads((Path(__file__).parents[1] / "reports" / "channel_report_reference.json").read_text(encoding="utf-8"))
    result = []
    for ch in channels:
        if channel_id is not None and ch.id != channel_id:
            continue
        metadata = reference.get((ch.username or "").casefold(), {})
        result.append(SearchChannel(ch.id, ch.telegram_channel_id, ch.title, ch.url, ch.username,
                                    metadata.get("region", ""), metadata.get("contact", "")))
    return result


def parse_keywords(raw: str) -> tuple[str, ...]:
    # Spaces remain part of a phrase; commas/newlines separate alternatives (OR).
    keywords = tuple(dict.fromkeys(k.strip().casefold()
                                   for k in raw.replace("\n", ",").split(",") if k.strip()))
    if not keywords or len(keywords) > 10 or any(len(k) > 200 for k in keywords):
        raise ValueError("1–10 ta kalit so'z kiriting, har biri 200 belgidan oshmasin.")
    return keywords


@dataclass(frozen=True)
class SearchRequest:
    keywords: tuple[str, ...]
    mode: str
    start: datetime | None
    end: datetime
    label: str

    @classmethod
    def create(cls, raw: str, mode: str, start_date: date | None = None,
               end_date: date | None = None):
        keywords = parse_keywords(raw)
        now = get_tashkent_now()
        end = now.astimezone(timezone.utc)
        if mode == "latest":
            return cls(keywords, mode, None, end, "Har kanaldagi eng oxirgi mos reklama")
        if mode == "month":
            start_date, end_date = now.date().replace(day=1), now.date()
        elif mode == "week":
            start_date, end_date = now.date() - timedelta(days=6), now.date()
        elif mode == "year":
            start_date, end_date = now.date() - timedelta(days=364), now.date()
        elif mode != "custom":
            raise ValueError("Noto'g'ri qidiruv davri.")
        if not start_date or not end_date or start_date > end_date:
            raise ValueError("Boshlanish sanasi tugash sanasidan katta bo'lmasin.")
        if start_date > now.date() or end_date > now.date():
            raise ValueError("Kelajakdagi sanani kiritmang.")
        start, selected_end = get_date_range_boundaries_utc(start_date, end_date)
        return cls(keywords, mode, start, min(end, selected_end),
                   f"{start_date:%d.%m.%Y} — {end_date:%d.%m.%Y} (Toshkent)")


@dataclass
class LiveAd:
    message_id: int
    url: str
    posted_at: datetime
    views: int | None
    forwards: int | None


@dataclass
class ChannelSearchResult:
    channel: SearchChannel
    ads: list[LiveAd] = field(default_factory=list)
    status: str = "not_found"
    detail: str = "Topilmadi"


@dataclass
class SearchReport:
    request: SearchRequest
    channels: list[ChannelSearchResult]
    checked_at: datetime

    @property
    def total_ads(self):
        return sum(len(ch.ads) for ch in self.channels)


class SearchUnavailable(Exception):
    pass


Progress = Callable[[int, int, str, int], Awaitable[None]]


class LiveSearchService:
    def __init__(self, manager=telegram_client_manager):
        self.manager = manager
        self.retry_at: datetime | None = None

    async def search(self, channels: list[SearchChannel], request: SearchRequest,
                     progress: Progress | None = None) -> SearchReport:
        if self.retry_at and self.retry_at > datetime.now(timezone.utc):
            seconds = int((self.retry_at - datetime.now(timezone.utc)).total_seconds()) + 1
            raise SearchUnavailable(f"Telegram cheklovi: {seconds} soniyadan keyin qayta qidiring.")
        if not await self.manager.is_authorized():
            raise SearchUnavailable("Telegram akkaunti ulanmagan. Serverda telegram_login.py orqali ulang.")

        results = []
        dialog_entities = None
        for index, channel in enumerate(channels):
            result = ChannelSearchResult(channel)
            results.append(result)
            scanned = 0
            last_progress = monotonic()
            if progress:
                await progress(index, len(channels), channel.title, scanned)
            try:
                # ID identifies the saved channel even after a username change. Telethon
                # resolves its access hash from the authenticated account/session.
                try:
                    entity = await self.manager.client.get_entity(channel.telegram_id)
                except ValueError:
                    # StringSession does not persist the entity/access-hash cache.
                    # Read dialog metadata once, then select only stored channel IDs.
                    if dialog_entities is None:
                        dialog_entities = {}
                        async for dialog in self.manager.client.iter_dialogs(limit=None):
                            peer = dialog.entity
                            if getattr(peer, "broadcast", False):
                                dialog_entities[peer.id] = peer
                    raw_id = int(str(channel.telegram_id).removeprefix("-100"))
                    entity = dialog_entities.get(raw_id)
                    if entity is None:
                        raise ValueError("Saved channel is no longer accessible")
                expected_id = int(str(channel.telegram_id).removeprefix("-100"))
                if entity.id != expected_id or not getattr(entity, "broadcast", False):
                    raise ValueError("Resolved channel ID does not match the saved channel")
                result.channel = replace(channel, title=entity.title, username=entity.username,
                                         url=build_post_url(entity.id, entity.username, 1).rsplit("/", 1)[0])
                seen_albums = set()
                async for message in self.manager.client.iter_messages(
                    entity, limit=None,
                    # offset_date is exclusive; Telegram timestamps have second precision.
                    offset_date=request.end + timedelta(seconds=1),
                ):
                    if not message or isinstance(message, MessageEmpty):
                        continue
                    scanned += 1
                    posted = getattr(message, "date", None)
                    if posted is None:
                        continue
                    if posted.tzinfo is None:
                        posted = posted.replace(tzinfo=timezone.utc)
                    if request.start and posted < request.start:
                        break
                    if posted > request.end:
                        continue
                    if progress and monotonic() - last_progress >= 5:
                        await progress(index, len(channels), channel.title, scanned)
                        last_progress = monotonic()
                    text = message.message or ""
                    if not is_ad_message(text, getattr(message, "entities", None), list(request.keywords)):
                        continue
                    album = getattr(message, "grouped_id", None)
                    if album is not None and album in seen_albums:
                        continue
                    if album is not None:
                        seen_albums.add(album)
                    result.ads.append(LiveAd(
                        message.id, build_post_url(entity.id, entity.username, message.id),
                        posted, message.views, message.forwards,
                    ))
                    if request.mode == "latest":
                        break
                if result.ads:
                    result.status, result.detail = "found", "Topildi"
            except FloodWaitError as exc:
                self.retry_at = datetime.now(timezone.utc) + timedelta(seconds=exc.seconds)
                result.status = "error"
                result.detail = f"Tekshiruv tugamadi: Telegram cheklovi ({exc.seconds} soniya)"
                # Do not hammer the remaining channels during an account-wide cooldown.
                results.extend(ChannelSearchResult(ch, status="error", detail="Telegram cheklovi: tekshirilmadi")
                               for ch in channels[index + 1:])
                break
            except ChannelPrivateError:
                result.status, result.detail = "error", "Kanalga kirish huquqi yo'q"
            except Exception as exc:
                logger.warning("Bevosita qidiruvda kanal %s: %s", channel.id, type(exc).__name__)
                result.status, result.detail = "error", "Tekshiruv tugamadi: kanal yoki aloqa xatosi"
            if progress:
                await progress(index + 1, len(channels), channel.title, scanned)
        return SearchReport(request, results, datetime.now(timezone.utc))
