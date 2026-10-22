"""On-demand indexed search with bounded verification and explicit full verification."""

import json
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from time import monotonic
from typing import Awaitable, Callable

from telethon.errors import ChannelPrivateError, FloodWaitError
from telethon.tl.types import MessageEmpty

from app.core.logging import logger
from app.core.timezone import get_date_range_boundaries_utc, get_tashkent_now
from app.database.repositories.channel_repo import ChannelRepository
from app.database.repositories.settings_repo import SettingsRepository
from app.services.channel_metadata import metadata_key, template_metadata
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
    saved_metadata = await SettingsRepository(session).get_all()
    result = []
    for ch in channels:
        if channel_id is not None and ch.id != channel_id:
            continue
        stored = saved_metadata.get(metadata_key(ch.telegram_channel_id))
        metadata = json.loads(stored) if stored else template_metadata().get((ch.username or "").casefold(), {})
        result.append(SearchChannel(ch.id, ch.telegram_channel_id, ch.title, ch.url, ch.username,
                                    metadata.get("region", ""), metadata.get("contact", "")))
    return result


def parse_keywords(raw: str) -> tuple[str, ...]:
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
    full_history: bool = False

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
    partial: bool = False


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
    def __init__(self, manager=telegram_client_manager, history_limit: int = 500, index_limit: int = 1000):
        self.manager = manager
        self.history_limit = history_limit
        self.index_limit = index_limit
        self.retry_at: datetime | None = None

    @staticmethod
    async def _notify(progress, *args):
        if progress:
            try:
                await progress(*args)
            except Exception as exc:
                logger.warning("Qidiruv holatini yuborib bo'lmadi: %s", type(exc).__name__)

    @staticmethod
    def _posted(message):
        if not message or isinstance(message, MessageEmpty):
            return None
        posted = getattr(message, "date", None)
        return posted.replace(tzinfo=timezone.utc) if posted and posted.tzinfo is None else posted

    async def _search_channel(self, result, entity, request, progress, index, total):
        selected = {}
        scanned = 0
        last_progress = monotonic()

        def matches(message):
            # Audit item 2 is deliberately unchanged, including substring matching.
            return is_ad_message(message.message or "", getattr(message, "entities", None), list(request.keywords))

        async def notify():
            nonlocal last_progress
            if monotonic() - last_progress >= 5:
                await self._notify(progress, index, total, result.channel.title, scanned)
                last_progress = monotonic()

        offset = request.end + timedelta(seconds=1)
        try:
            if not request.full_history:
                # The index supplies candidates, not proof that hidden links or
                # arbitrary substrings are absent. History verification decides completeness.
                for query in dict.fromkeys(k.lstrip("@") or k for k in request.keywords):
                    if not any(char.isalnum() for char in query):
                        continue
                    async for message in self.manager.client.iter_messages(
                        entity, search=query, limit=self.index_limit, offset_date=offset,
                    ):
                        scanned += 1
                        await notify()
                        posted = self._posted(message)
                        if posted is None or posted > request.end:
                            continue
                        if request.start and posted < request.start:
                            break
                        if matches(message):
                            selected[message.id] = (message, posted)
                            if request.mode == "latest":
                                break

            best_id = max(selected, default=0) if request.mode == "latest" else 0
            history_complete = False
            position = 0
            async for message in self.manager.client.iter_messages(
                entity, limit=None if request.full_history else self.history_limit + 1, offset_date=offset,
            ):
                position += 1
                if not request.full_history and position > self.history_limit:
                    break
                scanned += 1
                await notify()
                posted = self._posted(message)
                if posted is None:
                    continue
                if request.start and posted < request.start:
                    history_complete = True
                    break
                if posted > request.end:
                    continue
                if matches(message):
                    selected[message.id] = (message, posted)
                    if request.mode == "latest":
                        history_complete = True
                        break
                if best_id and message.id <= best_id:
                    history_complete = True
                    break
            else:
                history_complete = True
            result.partial = not history_complete
            if result.partial:
                result.status, result.detail = "error", "Qisman tekshirildi. To'liq tekshirishni bosing"
            elif selected:
                result.status, result.detail = "found", "Topildi"
        finally:
            # Preserve discovered posts even if a later request fails or is rate limited.
            albums = set()
            ads = []
            for message, posted in sorted(selected.values(), key=lambda pair: (pair[1], pair[0].id), reverse=True):
                album = getattr(message, "grouped_id", None)
                if album is not None and album in albums:
                    continue
                if album is not None:
                    albums.add(album)
                ads.append(LiveAd(message.id, build_post_url(entity.id, entity.username, message.id),
                                  posted, message.views, message.forwards))
                if request.mode == "latest":
                    break
            result.ads = ads

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
            if self.retry_at and self.retry_at > datetime.now(timezone.utc):
                results.extend(ChannelSearchResult(ch, status="error", detail="Telegram cheklovi: tekshirilmadi")
                               for ch in channels[index + 1:])
                result.status, result.detail = "error", "Telegram cheklovi: tekshirilmadi"
                break
            await self._notify(progress, index, len(channels), channel.title, 0)
            try:
                try:
                    entity = await self.manager.client.get_entity(channel.telegram_id)
                except ValueError:
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
                await self._search_channel(result, entity, request, progress, index, len(channels))
            except FloodWaitError as exc:
                self.retry_at = datetime.now(timezone.utc) + timedelta(seconds=exc.seconds)
                result.status = "error"
                result.detail = f"Tekshiruv tugamadi: Telegram cheklovi ({exc.seconds} soniya)"
                results.extend(ChannelSearchResult(ch, status="error", detail="Telegram cheklovi: tekshirilmadi")
                               for ch in channels[index + 1:])
                break
            except ChannelPrivateError:
                result.status, result.detail = "error", "Kanalga kirish huquqi yo'q"
            except Exception as exc:
                logger.warning("Bevosita qidiruvda kanal %s: %s", channel.id, type(exc).__name__)
                result.status, result.detail = "error", "Tekshiruv tugamadi: kanal yoki aloqa xatosi"
            await self._notify(progress, index + 1, len(channels), channel.title, 0)
        return SearchReport(request, results, datetime.now(timezone.utc))
