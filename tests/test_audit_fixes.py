import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from html.parser import HTMLParser
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import EditMessageText, SendDocument, SendMessage
from aiogram.types import BufferedInputFile
from sqlalchemy import func, select

from app.bot.handlers import channels, search, start
from app.bot.middlewares.retry import RetryAfterMiddleware
from app.bot.operations import running
from app.bot.states.forms import AddChannelState
from app.core.config import settings
from app.core.logging import SensitiveFilter, SensitiveFormatter
from app.core.timezone import TASHKENT_TZ
from app.database.models.channel import Channel
from app.services.channel_service import ChannelService
from app.services.live_search import LiveSearchService, SearchRequest, load_search_channels
from tests.test_live_search import channel, custom_request, example_report, manager, post, stream
from tests.test_search_flow import CaptureSession


@pytest.fixture(autouse=True)
def isolated_operations(monkeypatch):
    monkeypatch.setattr(search, "search_slots", asyncio.Semaphore(2))
    monkeypatch.setattr("app.services.live_search.get_tashkent_now", lambda: datetime(2026, 10, 22, 12, tzinfo=TASHKENT_TZ))
    yield
    assert not running
    search.reports.clear()
    channels.health_reports.clear()


def message(text="@otherbot", user=777):
    result = AsyncMock()
    result.text, result.chat.id, result.from_user.id = text, user, user
    return result


def state(user=777):
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=user, user_id=user))


@pytest.mark.asyncio
async def test_cancel_bulk_stops_pending_work_before_new_search(monkeypatch, db_session):
    entered = asyncio.Event()
    calls = []
    async def resolve(raw):
        calls.append(raw)
        if raw == "@second":
            entered.set()
            await asyncio.Future()
        return dict(telegram_channel_id=-100111, title="First", username="first", url="https://t.me/first")
    tg = NS(resolve_channel=resolve)
    @asynccontextmanager
    async def db():
        try:
            yield db_session
            await db_session.commit()
        except BaseException:
            await db_session.rollback()
            raise
    factory = ChannelService
    monkeypatch.setattr(channels, "get_db_session", db)
    monkeypatch.setattr(channels, "ChannelService", lambda session: factory(session, tg))
    conversation = state()
    await conversation.set_state(AddChannelState.waiting_for_url)
    worker = asyncio.create_task(channels.process_channel_input(message("@first @second @third"), conversation))
    await asyncio.wait_for(entered.wait(), 2)
    await start.handle_home_text(message("/cancel"), conversation)
    assert worker.done()
    assert calls == ["@first", "@second"]
    await search.begin_search(message(), conversation, "latest")
    await worker
    assert await conversation.get_state() == search.SearchState.keywords.state
    assert (await conversation.get_data())["mode"] == "latest"
    # The first item finished before cancellation; pending/remaining items never save.
    assert await db_session.scalar(select(func.count()).select_from(Channel)) == 1
    assert (await db_session.scalar(select(Channel))).title == "First"
    await conversation.storage.close()


@pytest.mark.asyncio
async def test_two_users_search_concurrently_and_queued_user_can_cancel(monkeypatch):
    @asynccontextmanager
    async def db():
        yield object()
    monkeypatch.setattr(search, "get_db_session", db)
    monkeypatch.setattr(search, "load_search_channels", AsyncMock(return_value=[channel()]))
    monkeypatch.setattr(search, "send_excel", AsyncMock())
    release = asyncio.Event()
    both_entered = asyncio.Event()
    count = 0
    async def query(*args):
        nonlocal count
        count += 1
        if count == 2:
            both_entered.set()
        await release.wait()
        return example_report()
    monkeypatch.setattr(search.service, "search", query)
    conversations = [state(user) for user in (777, 888, 999)]
    workers = [asyncio.create_task(search.run_search(message(user=user), conversation,
        SearchRequest.create("@otherbot", "latest"))) for user, conversation in zip((777, 888), conversations)]
    await asyncio.wait_for(both_entered.wait(), 2)
    queued = asyncio.create_task(search.run_search(message(user=999), conversations[2], SearchRequest.create("@otherbot", "latest")))
    # Wait for the queued task's registration, without relying on a wall-clock delay.
    for _ in range(20):
        if (999, 999) in running:
            break
        await asyncio.sleep(0)
    await search.cancel_search(999, 999)
    await asyncio.wait_for(queued, 2)
    assert count == 2
    release.set()
    await asyncio.gather(*workers)
    assert search.send_excel.await_count == 2
    for conversation in conversations:
        await conversation.storage.close()


@pytest.mark.asyncio
async def test_index_finds_latest_in_large_history_with_few_messages():
    newest = post(100000, "news")
    target = post(99999)
    mgr = manager({})
    examined = {"index": 0, "history": 0}
    async def iterate(peer, **kwargs):
        if "search" in kwargs:
            examined["index"] += 1
            yield target
        else:
            for number in range(100000, 0, -1):
                examined["history"] += 1
                yield target if number == 99999 else post(number, "news")
    mgr.client.iter_messages.side_effect = iterate
    report = await LiveSearchService(mgr).search([channel()], SearchRequest.create("@otherbot", "latest"))
    assert report.channels[0].status == "found"
    assert report.channels[0].ads[0].message_id == 99999
    assert examined == {"index": 1, "history": 2}


@pytest.mark.asyncio
async def test_large_unindexed_history_is_partial_until_explicit_full_verification():
    mgr = manager({111: [post(n, "news") if n != 1 else post(1, "Contact", entities=[NS(url="https://t.me/otherbot")])
                         for n in range(100, 0, -1)]})
    service = LiveSearchService(mgr, history_limit=5)
    request = SearchRequest.create("@otherbot", "latest")
    fast = await service.search([channel()], request)
    assert fast.channels[0].partial is True
    assert fast.channels[0].status != "not_found"
    _, keyboard = search.render_page(fast, "token")
    assert any(button.callback_data == "search:full:token" for row in keyboard.inline_keyboard for button in row)
    full = await service.search([channel()], replace(request, full_history=True))
    assert full.channels[0].status == "found"
    assert full.channels[0].partial is False
    assert full.channels[0].ads[0].message_id == 1


@pytest.mark.asyncio
async def test_indexed_and_hidden_links_merge_without_duplicates_or_changing_matcher():
    mgr = manager({111: [post(3, "@otherbot_fake"), post(2, "Contact", entities=[NS(url="https://example.test/otherbot")]), post(1, "news")]})
    report = await LiveSearchService(mgr).search([channel()], custom_request())
    assert [ad.message_id for ad in report.channels[0].ads] == [3, 2]
    assert report.channels[0].partial is False


@pytest.mark.asyncio
async def test_native_result_does_not_claim_latest_when_newer_history_is_unverified():
    mgr = manager({})
    def iterate(peer, **kwargs):
        return stream([post(1)]) if "search" in kwargs else stream([post(n, "news") for n in range(100, 0, -1)])
    mgr.client.iter_messages.side_effect = iterate
    result = (await LiveSearchService(mgr, history_limit=5).search([channel()], SearchRequest.create("@otherbot", "latest"))).channels[0]
    assert result.ads[0].message_id == 1
    assert result.partial is True
    assert result.status == "error"


@pytest.mark.asyncio
async def test_full_verification_merges_previous_complete_rows(monkeypatch):
    previous = example_report()
    pending = previous.channels[2]
    pending.status, pending.partial = "error", True
    token = search.cache_report((777, 777), previous)
    targets = [result.channel for result in previous.channels]
    @asynccontextmanager
    async def db():
        yield object()
    monkeypatch.setattr(search, "get_db_session", db)
    monkeypatch.setattr(search, "load_search_channels", AsyncMock(return_value=targets))
    verified = replace(pending, status="not_found", detail="Topilmadi", partial=False)
    async def query(channels, request, progress):
        assert [ch.id for ch in channels] == [pending.channel.id]
        assert request.full_history is True
        return replace(previous, request=request, channels=[verified])
    monkeypatch.setattr(search.service, "search", query)
    delivered = AsyncMock()
    monkeypatch.setattr(search, "send_excel", delivered)
    callback = AsyncMock()
    callback.data = f"search:full:{token}"
    callback.message.chat.id, callback.from_user.id = 777, 777
    conversation = state()
    await search.cached_result(callback, conversation)
    result = delivered.call_args.args[1]
    assert len(result.channels) == 4
    assert result.channels[0] is previous.channels[0]
    assert result.channels[2].partial is False
    assert result.channels[2].status == "not_found"
    await conversation.storage.close()


@pytest.mark.asyncio
async def test_progress_429_does_not_abort_search_or_excel(monkeypatch):
    @asynccontextmanager
    async def db():
        yield object()
    monkeypatch.setattr(search, "get_db_session", db)
    monkeypatch.setattr(search, "load_search_channels", AsyncMock(return_value=[channel()]))
    monkeypatch.setattr(search.service, "manager", manager({111: []}))
    monkeypatch.setattr(search, "send_excel", AsyncMock())
    msg = message()
    wait = msg.answer.return_value
    wait.edit_text.side_effect = [TelegramRetryAfter(method=EditMessageText(chat_id=777, message_id=1, text="progress"),
                                                   message="flood", retry_after=3), None]
    conversation = state()
    await conversation.update_data(mode="latest")
    await search.execute_search(msg, conversation)
    search.send_excel.assert_awaited_once()
    assert await conversation.get_state() is None
    await conversation.storage.close()


@pytest.mark.asyncio
async def test_service_ignores_optional_progress_errors_but_propagates_cancellation():
    service = LiveSearchService(manager({111: []}))
    result = await service.search([channel()], custom_request(), AsyncMock(side_effect=RuntimeError("UI unavailable")))
    assert result.channels[0].status == "not_found"
    with pytest.raises(asyncio.CancelledError):
        await service.search([channel()], custom_request(), AsyncMock(side_effect=asyncio.CancelledError()))


@pytest.mark.asyncio
@pytest.mark.parametrize("method", [SendMessage(chat_id=777, text="result"),
    EditMessageText(chat_id=777, message_id=1, text="result"),
    SendDocument(chat_id=777, document=BufferedInputFile(b"test", filename="report.xlsx"))])
async def test_bot_session_retries_429_for_messages_edits_and_uploads(monkeypatch, method):
    retry = TelegramRetryAfter(method=method, message="flood", retry_after=7)
    make_request = AsyncMock(side_effect=[retry, "delivered"])
    sleep = AsyncMock()
    monkeypatch.setattr("app.bot.middlewares.retry.asyncio.sleep", sleep)
    assert await RetryAfterMiddleware()(make_request, object(), method) == "delivered"
    assert make_request.await_count == 2
    sleep.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_retry_is_bounded_and_wait_remains_cancellable(monkeypatch):
    method = SendMessage(chat_id=777, text="result")
    retry = TelegramRetryAfter(method=method, message="flood", retry_after=7)
    request = AsyncMock(side_effect=retry)
    monkeypatch.setattr("app.bot.middlewares.retry.asyncio.sleep", AsyncMock())
    with pytest.raises(TelegramRetryAfter):
        await RetryAfterMiddleware(retries=2)(request, object(), method)
    assert request.await_count == 3
    monkeypatch.setattr("app.bot.middlewares.retry.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await RetryAfterMiddleware()(request, object(), method)


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, data):
        self.text.append(data)


@pytest.mark.asyncio
async def test_health_callback_paginates_500_channels_and_owner_scopes_navigation(monkeypatch):
    @asynccontextmanager
    async def db():
        yield object()
    rows = [NS(id=i, title=f"channel-{i:03}-" + "A" * 110) for i in range(500)]
    service = NS(list_active_channels=AsyncMock(return_value=rows),
                 check_channel_health=AsyncMock(return_value={"status":"error", "message":"<&>" * 80}))
    monkeypatch.setattr(channels, "get_db_session", db)
    monkeypatch.setattr(channels, "ChannelService", lambda session: service)
    callback = AsyncMock()
    callback.message.chat.id = callback.from_user.id = 777
    await channels.callback_check_all_channels(callback)
    token = next(iter(channels.health_reports))
    lines = channels.health_reports[token][2]
    all_text = []
    for page in range(1, 101):
        text, markup = channels.render_health_page(lines, token, page)
        parsed = TextOnly(); parsed.feed(text)
        visible = "".join(parsed.text)
        assert len(visible) <= 4096
        all_text.append(visible)
    assert all("channel-" + f"{i:03}-" in "".join(all_text) for i in range(500))
    callback.data = f"health:page:{token}:2"
    await channels.callback_health_page(callback)
    assert service.check_channel_health.await_count == 500
    callback.from_user.id = 888
    callback.message.edit_text.reset_mock()
    await channels.callback_health_page(callback)
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_renamed_channel_updates_same_record_and_preserves_template_metadata_by_id(db_session):
    tg = NS(resolve_channel=AsyncMock(side_effect=[
        dict(telegram_channel_id=-100111, title="Old", username="vodiybozor", url="https://t.me/vodiybozor"),
        dict(telegram_channel_id=-100111, title="New", username="renamed_channel", url="https://t.me/renamed_channel")]))
    service = ChannelService(db_session, tg)
    original, _ = await service.add_channel("@vodiybozor")
    row, added = await service.add_channel("@renamed_channel")
    assert not added and row.id == original.id
    assert (row.title, row.username, row.url) == ("New", "renamed_channel", "https://t.me/renamed_channel")
    targets = await load_search_channels(db_session)
    assert targets[0].region == "умумий"
    assert targets[0].contact == "https://t.me/Vodiybozormanager"
    assert await db_session.scalar(select(func.count()).select_from(Channel)) == 1


@pytest.mark.parametrize("kind", ["plain", "args", "dict", "exception", "cached_exception", "stack"])
def test_logs_redact_formatted_arguments_tracebacks_and_configured_secrets(monkeypatch, kind):
    token = "987654321:" + "X" * 35
    api_hash = "a" * 32
    session = "1" + "Q" * 150 + "="
    custom = "synthetic-secret-with-unusual-format"
    monkeypatch.setattr(settings, "TELEGRAM_API_HASH", custom)
    secrets = (token, api_hash, session, custom)
    text = " ".join(secrets)
    record = logging.LogRecord("test", logging.ERROR, "file", 1, text, (), None)
    if kind == "args":
        record.msg, record.args = "%s", (text,)
    elif kind == "dict":
        record.msg, record.args = "%(value)s", {"value": text}
    elif kind == "exception":
        try:
            raise RuntimeError(text)
        except RuntimeError:
            record.msg, record.exc_info = "Failure", sys.exc_info()
    elif kind == "cached_exception":
        record.msg, record.exc_text = "Failure", text
    elif kind == "stack":
        record.msg, record.stack_info = "Failure", text
    SensitiveFilter().filter(record)
    output = SensitiveFormatter("%(message)s").format(record)
    assert all(secret not in output for secret in secrets)
    assert "[REDACTED_SECRET]" in output
    assert record.args == ()
