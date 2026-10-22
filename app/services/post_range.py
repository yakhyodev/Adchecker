"""Sequential, retryable date-range reports with a small disk-backed working set."""

import asyncio
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone

from telethon.tl.types import Channel, MessageEmpty

from app.core.timezone import get_date_range_boundaries_utc, get_tashkent_now, get_utc_now
from app.services.post_report import (
    SOURCE_CHANNEL, PostMetrics, PostReport, PostReportRetry, PostReportService, PostReportUnavailable, metrics,
)


@dataclass(frozen=True)
class PostRange:
    start: date
    end: date

    @classmethod
    def create(cls, start, end):
        if start > end:
            raise ValueError("Tugash sanasi boshlanish sanasidan kichik bo'lmasin.")
        if end > get_tashkent_now().date():
            raise ValueError("Kelajakdagi sanani kiritmang.")
        return cls(start, end)


def encode(post):
    return json.dumps(asdict(post), default=lambda value: value.isoformat(), ensure_ascii=False)


def decode(value):
    fields = json.loads(value)
    if fields["published_at"]:
        fields["published_at"] = datetime.fromisoformat(fields["published_at"])
    return PostMetrics(**fields)


class RangeStore:
    """Per-request spool, not a historical analytics database or background monitor."""

    def __init__(self, path):
        self.collection_complete = True
        self.collection_notice = None
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA cache_size=-2048")
        self.db.execute("PRAGMA temp_store=FILE")
        self.db.executescript("""
            CREATE TABLE posts(seq INTEGER PRIMARY KEY, message_id INTEGER UNIQUE,
                day TEXT, source TEXT, public INTEGER, private INTEGER, checked TEXT, complete INTEGER);
            CREATE TABLE destinations(id INTEGER PRIMARY KEY, title TEXT, kind TEXT, url TEXT);
            CREATE TABLE forwards(source_id INTEGER, destination_id INTEGER, message_id INTEGER,
                published TEXT, payload TEXT, PRIMARY KEY(source_id,destination_id,message_id));
        """)

    def close(self):
        self.db.close()

    def sink(self, source_id):
        return ForwardSink(self, source_id)

    def save_post(self, report, day):
        self.db.execute("INSERT INTO posts(message_id,day,source,public,private,checked,complete) VALUES(?,?,?,?,?,?,?)",
                        (report.source.message_id, day.isoformat(), encode(report.source), report.public_shares,
                         report.private_shares, report.checked_at.isoformat(), int(report.forwards_complete)))
        self.db.commit()

    @property
    def post_count(self):
        return self.db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

    @property
    def partial_count(self):
        return self.db.execute("SELECT COUNT(*) FROM posts WHERE complete=0").fetchone()[0]


class ForwardSink:
    def __init__(self, store, source_id):
        self.store, self.source_id = store, source_id

    def contains(self, destination_id, message_id):
        return self.store.db.execute("SELECT 1 FROM forwards WHERE source_id=? AND destination_id=? AND message_id=?",
                                     (self.source_id, destination_id, message_id)).fetchone() is not None

    def save(self, row):
        self.store.db.execute("INSERT OR REPLACE INTO forwards VALUES(?,?,?,?,?)",
            (self.source_id, row.telegram_id, row.message_id,
             row.published_at.isoformat() if row.published_at else "", encode(row)))
        self.store.db.execute("""INSERT INTO destinations VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            title=COALESCE(excluded.title,title),kind=COALESCE(excluded.kind,kind),url=COALESCE(excluded.url,url)""",
            (row.telegram_id, row.title, row.kind, row.channel_url))


class SequentialPostService(PostReportService):
    def __init__(self, manager, progress, *, pace=0.5, sleep=asyncio.sleep, request_timeout=30):
        super().__init__(manager, request_timeout)
        self.progress, self.pace, self.sleep = progress, pace, sleep

    async def _optional(self, factory, label):
        attempt = 0
        while True:
            if self.pace:
                await self.sleep(self.pace)
            try:
                return await super()._optional(factory, label)
            except PostReportRetry as exc:
                attempt += 1
                seconds = exc.retry_after + 1 if exc.retry_after is not None else min(60, 5 * 2**min(attempt - 1, 4))
                await self.progress("wait", f"Telegram: {seconds} soniya kutilmoqda. Shu joydan davom etadi. ({label})")
                # Cancellation remains immediate even for hours-long Telegram waits.
                while seconds > 0:
                    step = min(seconds, 30)
                    await self.sleep(step)
                    seconds -= step
                await self.progress("resume", "Kutish tugadi. Hisobot davom etmoqda.")


class PostRangeService:
    def __init__(self, manager, *, pace=0.5, sleep=asyncio.sleep):
        self.manager, self.pace, self.sleep = manager, pace, sleep

    async def collect(self, selected, store, progress):
        api = SequentialPostService(self.manager, progress, pace=self.pace, sleep=self.sleep)
        if not await api._optional(self.manager.probe_authorization, "akkaunt avtorizatsiyasi"):
            raise PostReportUnavailable("Ulangan Telegram akkaunti avtorizatsiyadan o'tmagan.")
        entity = await api._optional(lambda: self.manager.client.get_entity(SOURCE_CHANNEL), "asosiy kanal")
        if not isinstance(entity, Channel) or not entity.broadcast:
            raise PostReportUnavailable("Asosiy kanal ma'lumoti topilmadi.")
        day = selected.start
        cutoff = get_tashkent_now().astimezone(timezone.utc) + timedelta(seconds=1)
        while day <= selected.end:
            start, end = get_date_range_boundaries_utc(day, day)
            upper = min(end + timedelta(microseconds=1), cutoff)
            cursor = 0
            await progress("day", f"{day:%d.%m.%Y}: postlar eskidan yangiga olinmoqda. Tayyor: {store.post_count} ta.")
            iterator = None

            async def read_next():
                nonlocal iterator
                if iterator is None:
                    iterator = self.manager.client.iter_messages(
                        entity, reverse=True, limit=None, min_id=cursor,
                        offset_date=start - timedelta(seconds=1) if not cursor else None, wait_time=1)
                try:
                    return await iterator.__anext__()
                except BaseException:
                    # Reopen at the last completed message after a failed page.
                    # An async generator may already be closed after its first error.
                    iterator = None
                    raise

            try:
                while True:
                    item = await api._optional(read_next, "kanal tarixi")
                    if item is None:
                        raise PostReportUnavailable("Kanal tarixini to'liq olib bo'lmadi. Qayta urinib ko'ring.")
                    posted = getattr(item, "date", None)
                    if posted and posted.tzinfo is None:
                        posted = posted.replace(tzinfo=timezone.utc)
                    if posted and posted >= upper:
                        break
                    if item.id <= cursor:
                        continue
                    if posted and posted >= start and not isinstance(item, MessageEmpty) and not getattr(item, "action", None):
                        await progress("post", f"{day:%d.%m.%Y} · Post #{item.id}. Tayyor: {store.post_count} ta.")
                        # History pages may be buffered for a long time. Refresh the
                        # exact post when its turn arrives, including deletion checks.
                        current = await api._optional(lambda: self.manager.client.get_messages(entity, ids=item.id), "asosiy post")
                        if current is None or isinstance(current, MessageEmpty):
                            source = metrics(item, entity)
                            source.views = source.reactions = source.shares = source.replies = source.members = None
                            report = PostReport(source=source, checked_at=get_utc_now(), notice="Post ma'lumoti topilmadi.")
                        else:
                            if current.id != item.id:
                                raise PostReportUnavailable("Telegram post ID'si mos kelmadi. Hisobot to'xtatildi.")
                            report = await api.collect_message(entity, current, store.sink(item.id))
                        store.save_post(report, day)
                        del report
                    cursor = item.id
            except StopAsyncIteration:
                pass
            finally:
                close = getattr(iterator, "aclose", None)
                if close:
                    await close()
                del iterator
            day += timedelta(days=1)
