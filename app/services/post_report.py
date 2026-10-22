"""One-shot post statistics. Only Telegram-provided messages/counters are used."""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

from telethon import utils
from telethon.errors import FloodWaitError, RPCError, StatsMigrateError
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.stats import GetMessagePublicForwardsRequest
from telethon.tl.types import (
    Channel, Chat, MessageEmpty, PeerChannel, PeerChat, PublicForwardMessage,
)

from app.core.logging import logger
from app.core.timezone import get_utc_now
from app.telegram_client.client import telegram_client_manager

MISSING = "Ma'lumot topilmadi"
# This feature was requested for the owned channel, not arbitrary chats visible
# to the shared Telegram account. No new deployment environment is needed.
SOURCE_CHANNEL = "imkonsavdomarkazi"


class PostReportUnavailable(Exception):
    """A report cannot currently be obtained; safe to display to the user."""


class PostReportRetry(PostReportUnavailable):
    def __init__(self, text, retry_after=None):
        super().__init__(text)
        self.retry_after = retry_after


@dataclass(frozen=True)
class PostLink:
    channel: str | int
    message_id: int


def parse_post_link(raw: str) -> PostLink:
    value = raw.strip()
    if value.startswith(("t.me/", "telegram.me/")):
        value = "https://" + value
    try:
        url = urlsplit(value)
        if (url.scheme not in ("https", "http")
                or url.netloc.casefold() not in ("t.me", "telegram.me")):
            raise ValueError
        parts = url.path.strip("/").split("/")
        if parts[0] == "s":
            parts = parts[1:]
        if len(parts) == 3 and parts[0] == "c" and parts[1].isascii() and parts[1].isdigit():
            internal_id = int(parts[1])
            if not 0 < internal_id <= 9999999999:
                raise ValueError
            channel = utils.get_peer_id(PeerChannel(internal_id))
        elif len(parts) == 2 and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", parts[0]):
            channel = parts[0]
        else:
            raise ValueError
        if not parts[-1].isascii() or not parts[-1].isdigit():
            raise ValueError
        message_id = int(parts[-1])
        if not 0 < message_id <= 2**31 - 1:
            raise ValueError
        return PostLink(channel, message_id)
    except (ValueError, IndexError):
        raise ValueError("Post havolasini yuboring. Masalan: https://t.me/imkonsavdomarkazi/5644") from None


def count(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


def public_username(chat) -> str | None:
    username = getattr(chat, "username", None)
    if username:
        return username
    return next((item.username for item in getattr(chat, "usernames", None) or []
                 if item.active), None)


@dataclass
class PostMetrics:
    title: str | None
    kind: str | None
    channel_url: str | None
    post_url: str | None
    published_at: datetime | None
    members: int | None
    views: int | None
    reactions: int | None
    shares: int | None
    replies: int | None
    telegram_id: int | None = None
    message_id: int | None = None


def metrics(message, chat, members=None) -> PostMetrics:
    username = public_username(chat)
    channel_url = f"https://t.me/{username}" if username else None
    peer = getattr(message, "peer_id", None)
    channel_id = getattr(peer, "channel_id", None)
    post_url = (f"{channel_url}/{message.id}" if channel_url
                else f"https://t.me/c/{channel_id}/{message.id}" if channel_id else None)
    reactions = getattr(message, "reactions", None)
    # An absent optional reaction field is unknown, never a fabricated zero.
    reaction_count = None
    if reactions is not None and getattr(reactions, "results", None) is not None:
        values = [count(item.count) for item in reactions.results]
        if all(value is not None for value in values):
            reaction_count = sum(values)
    return PostMetrics(
        title=getattr(chat, "title", None),
        kind=("Guruh" if isinstance(chat, Chat) or isinstance(peer, PeerChat) or getattr(chat, "megagroup", False)
              else "Kanal" if getattr(chat, "broadcast", False) else None),
        channel_url=channel_url, post_url=post_url,
        published_at=getattr(message, "date", None),
        members=count(members) if members is not None else count(getattr(chat, "participants_count", None)),
        views=count(getattr(message, "views", None)), reactions=reaction_count,
        shares=count(getattr(message, "forwards", None)),
        replies=count(getattr(getattr(message, "replies", None), "replies", None)),
        telegram_id=utils.get_peer_id(peer) if isinstance(peer, (PeerChannel, PeerChat)) else None,
        message_id=getattr(message, "id", None),
    )


@dataclass
class PostReport:
    source: PostMetrics
    checked_at: datetime
    public_shares: int | None = None
    private_shares: int | None = None
    forwards: list[PostMetrics] = field(default_factory=list)
    forwards_complete: bool = False
    notice: str | None = None
    forward_count: int = 0


class PostReportService:
    def __init__(self, manager=telegram_client_manager, request_timeout=30):
        self.manager = manager
        self.request_timeout = request_timeout

    async def _optional(self, request, label):
        try:
            async with asyncio.timeout(self.request_timeout):
                result = await (request() if callable(request) else request)
            if result is None:
                logger.info("Post hisoboti: %s — %s", label, MISSING)
            return result
        except FloodWaitError as exc:
            logger.info("Post hisoboti: Telegram kutish vaqti — %s soniya", exc.seconds)
            raise PostReportRetry(f"Telegram {exc.seconds} soniya kutishni so'radi. Keyin qayta urinib ko'ring.", exc.seconds) from None
        except (RPCError, ValueError) as exc:
            # Other Telegram rate limits (for example FLOOD_PREMIUM_WAIT) also
            # provide a server wait duration, and must not become "not found".
            if isinstance(exc, RPCError) and exc.code == 420 and count(getattr(exc, "seconds", None)) is not None:
                logger.info("Post hisoboti: Telegram kutish vaqti — %s soniya", exc.seconds)
                raise PostReportRetry(f"Telegram {exc.seconds} soniya kutishni so'radi. Keyin qayta urinib ko'ring.", exc.seconds) from None
            # Telethon raises ValueError after exhausting server-error retries.
            # Do not turn that into a false "not found" result.
            if ((isinstance(exc, RPCError) and exc.code >= 500)
                    or isinstance(exc, ValueError) and str(exc).startswith("Request was unsuccessful")):
                logger.warning("Post hisoboti: %s uchun Telegram javobi olinmadi (%s)", label, type(exc).__name__)
                raise PostReportRetry("Telegram vaqtincha javob bermadi. Keyin qayta urinib ko'ring.") from None
            else:
                logger.info("Post hisoboti: %s — %s", label, MISSING)
            return None
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning("Post hisoboti: %s uchun ulanish tugamadi (%s)", label, type(exc).__name__)
            raise PostReportRetry("Telegram bilan ulanish tugamadi. Keyin qayta urinib ko'ring.") from None

    async def _stats_request(self, request, dc):
        """Borrow a stats DC connection without migrating the shared account client."""
        client = self.manager.client
        if dc is None or dc == client.session.dc_id:
            try:
                return await client(request)
            except StatsMigrateError as exc:
                dc = exc.dc
        sender = await client._borrow_exported_sender(dc)
        try:
            return await client._call(sender, request, flood_sleep_threshold=0)
        finally:
            await client._return_exported_sender(sender)

    async def collect(self, raw_link: str) -> PostReport:
        link = parse_post_link(raw_link)
        if isinstance(link.channel, str) and link.channel.casefold() != SOURCE_CHANNEL:
            raise PostReportUnavailable("Bu bo'lim faqat https://t.me/imkonsavdomarkazi kanalining postlari uchun.")
        if not await self._optional(self.manager.is_authorized, "akkaunt avtorizatsiyasi"):
            raise PostReportUnavailable("Ulangan Telegram akkaunti avtorizatsiyadan o'tmagan.")
        client = self.manager.client
        # Resolve the owned source even for /c/ links: never use account access
        # to probe an unrelated private channel ID supplied by a bot user.
        entity = await self._optional(lambda: client.get_entity(SOURCE_CHANNEL), "asosiy kanal")
        if not isinstance(entity, Channel) or not entity.broadcast:
            raise PostReportUnavailable(f"{MISSING}: asosiy kanalga kirish imkonini tekshiring.")
        if isinstance(link.channel, int) and utils.get_peer_id(entity) != link.channel:
            raise PostReportUnavailable("Bu bo'lim faqat https://t.me/imkonsavdomarkazi kanalining postlari uchun.")
        message = await self._optional(lambda: client.get_messages(entity, ids=link.message_id), "asosiy post")
        if message is None or isinstance(message, MessageEmpty):
            if isinstance(message, MessageEmpty):
                logger.info("Post hisoboti: asosiy post — %s", MISSING)
            raise PostReportUnavailable(f"{MISSING}: post mavjudligi va akkaunt kirish huquqini tekshiring.")
        return await self.collect_message(entity, message)

    async def collect_message(self, entity, message, sink=None) -> PostReport:
        """Trusted source history can stream one post's forwards directly to disk."""
        client = self.manager.client
        source = metrics(message, entity)
        report = PostReport(source=source, checked_at=get_utc_now())
        try:
            full = await self._optional(lambda: client(GetFullChannelRequest(entity)), "kanal ma'lumotlari")
            full_chat = getattr(full, "full_chat", None)
            members = count(getattr(full_chat, "participants_count", None))
            if members is not None:
                source.members = members
            await self._collect_forwards(report, entity, message.id, getattr(full_chat, "stats_dc", None), sink)
        except PostReportUnavailable as exc:
            # Preserve Telegram data already obtained when enrichment or a later
            # page hits a rate limit, timeout or transient server failure.
            report.notice = str(exc)
        if (source.shares is not None and report.public_shares is not None
                and source.shares >= report.public_shares):
            # Same calculation as Telegram Desktop, before filtering stories.
            report.private_shares = source.shares - report.public_shares
        if not report.forward_count and not report.notice:
            logger.info("Post hisoboti: public kanal/guruh postlari — %s", MISSING)
        report.checked_at = get_utc_now()
        return report

    async def _collect_forwards(self, report, entity, message_id, dc, sink=None):
        client = self.manager.client
        channel = utils.get_input_channel(entity)
        offset = ""
        offsets = set()
        seen = set()
        chats = {}
        member_counts = {}
        while True:
            page = await self._optional(lambda: self._stats_request(
                GetMessagePublicForwardsRequest(channel, message_id, offset, 100), dc), "public shares")
            if page is None:
                break
            # Use Telegram's total, never the length of our filtered/paginated list.
            if report.public_shares is None:
                report.public_shares = count(page.count)
            if sink is not None:
                chats.clear()
                member_counts.clear()
            chats.update({utils.get_peer_id(chat): chat for chat in page.chats
                          if isinstance(chat, (Channel, Chat))})
            for item in page.forwards:
                if not isinstance(item, PublicForwardMessage):
                    continue  # Stories and user reposts never appear in the report.
                forwarded = item.message
                peer = getattr(forwarded, "peer_id", None)
                if not isinstance(peer, (PeerChannel, PeerChat)) or isinstance(forwarded, MessageEmpty):
                    continue
                peer_id = utils.get_peer_id(peer)
                key = (peer_id, forwarded.id)
                if (sink.contains(*key) if sink is not None else key in seen):
                    continue
                if sink is None:
                    seen.add(key)
                chat = chats.get(peer_id)
                if chat is None:
                    chat = await self._optional(lambda: client.get_entity(peer), "forward kanali/guruhi")
                if chat is not None and not isinstance(chat, (Channel, Chat)):
                    continue
                row = metrics(forwarded, chat)
                if sink is None:
                    report.forwards.append(row)
                else:
                    sink.save(row)
                report.forward_count += 1
                # The stats response can carry only basic counters. Read that exact
                # destination post if richer public counters were omitted; no history search.
                counters = ("views", "reactions", "shares", "replies")
                if chat is not None and any(getattr(row, name) is None for name in counters):
                    current = await self._optional(lambda: client.get_messages(chat, ids=forwarded.id), "forward post statistikasi")
                    if current is not None and not isinstance(current, MessageEmpty):
                        refreshed = metrics(current, chat)
                        for name in counters:
                            value = getattr(refreshed, name)
                            if value is not None:
                                setattr(row, name, value)
                # Some slices omit member counts. Ask only about the returned destination,
                # never scan its history or search for additional placements.
                if row.members is None and isinstance(chat, Channel):
                    if peer_id not in member_counts:
                        details = await self._optional(lambda: client(GetFullChannelRequest(chat)), "kanal/guruh a'zolari")
                        member_counts[peer_id] = count(getattr(getattr(details, "full_chat", None), "participants_count", None))
                    row.members = member_counts[peer_id]
                if sink is not None:
                    sink.save(row)
            next_offset = getattr(page, "next_offset", None)
            if not next_offset:
                report.forwards_complete = True
                break
            if next_offset in offsets or next_offset == offset:
                logger.info("Post hisoboti: public shares ro'yxati to'liq olinmadi (takroriy sahifa)")
                report.notice = "Telegram public forwardlar sahifasini takror qaytardi. Qisman hisobot berildi."
                break
            offsets.add(offset)
            offset = next_offset
