import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage, EditMessageText, SendDocument
from aiogram.types import Chat, Message, Update, User, CallbackQuery

from app.bot.handlers import get_main_router, search, post_report
from tests.test_live_search import example_report
from app.core.timezone import TASHKENT_TZ


@pytest.fixture(autouse=True)
def freeze_query_time(monkeypatch):
    monkeypatch.setattr("app.services.live_search.get_tashkent_now", lambda: datetime(2026, 10, 22, 12, tzinfo=TASHKENT_TZ))


class CaptureSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText, SendDocument)):
            return Message(message_id=len(self.calls), date=datetime.now(timezone.utc),
                           chat=Chat(id=int(method.chat_id), type="private"),
                           text=getattr(method, "text", None)).as_(bot)
        return True

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b""


@pytest.mark.asyncio
async def test_dispatcher_start_period_keyword_report_and_bulk_channel_navigation(monkeypatch, tmp_path):
    # Use the actual router order and FSM filters, without Bot API or MTProto traffic.
    dp = Dispatcher()
    dp.include_router(get_main_router())
    session = CaptureSession()
    bot = Bot("123456:TEST_BOT_TOKEN", session=session)
    user = User(id=777, is_bot=False, first_name="Test")
    report = example_report()
    @asynccontextmanager
    async def fake_db():
        yield object()
    monkeypatch.setattr(search, "get_db_session", fake_db)
    load = AsyncMock(return_value=[report.channels[0].channel])
    monkeypatch.setattr(search, "load_search_channels", load)
    search_fn = AsyncMock(return_value=report)
    monkeypatch.setattr(search.service, "search", search_fn)

    async def send(text, number):
        return await dp.feed_update(bot, Update(update_id=number, message=Message(
            message_id=number, date=datetime.now(timezone.utc),
            chat=Chat(id=user.id, type="private"), from_user=user, text=text)))
    state = FSMContext(dp.storage, StorageKey(bot_id=bot.id, chat_id=user.id, user_id=user.id))
    try:
        await send("/start", 1)
        assert "Saqlangan kanallardan" in session.calls[-1].text
        await send("🆕 Oxirgi reklamalar", 2)
        assert await state.get_state() == search.SearchState.keywords.state
        # Global channel navigation must win over a pending keyword state.
        await send("📢 Kanallar", 3)
        assert await state.get_state() is None
        assert "KANALLARNI BOSHQARISH" in session.calls[-1].text
        # A search button must also win over a pending channel-input state.
        from app.bot.states.forms import AddChannelState
        await state.set_state(AddChannelState.waiting_for_url)
        await send("🗓 Shu oy", 4)
        assert (await state.get_data())["mode"] == "month"
        await send("@anotherbot", 5)
        search_fn.assert_awaited_once()
        assert search_fn.call_args.args[1].keywords == ("@anotherbot",)
        assert load.await_count == 1 and load.call_args.args[1] is None
        assert any(isinstance(call, SendDocument) for call in session.calls)
        assert await state.get_state() is None
        await send("📆 Sana bo‘yicha", 6)
        await send("not a date", 7)
        assert await state.get_state() == search.SearchState.start_date.state
        await send("2026-10-01", 8)
        await send("2026-10-21", 9)
        assert await state.get_state() == search.SearchState.keywords.state
        await send("/cancel", 10)
        assert await state.get_state() is None

        # Post reports navigate independently and do not turn links into keyword searches.
        from app.services.post_report import PostReport, metrics
        from tests.test_post_report import channel, post, LINK, NOW
        post_result = PostReport(source=metrics(post(), channel()), checked_at=NOW,
                                 public_shares=15, private_shares=213, forwards_complete=True)
        collect = AsyncMock(return_value=post_result)
        monkeypatch.setattr(post_report.service, "collect", collect)
        await send("🆕 Oxirgi reklamalar", 11)
        await send("📋 Post hisoboti", 12)
        assert await state.get_state() == post_report.PostReportState.link.state
        await send("invalid link", 13)
        assert await state.get_state() == post_report.PostReportState.link.state
        collect.assert_not_awaited()
        await send(LINK, 14)
        assert collect.await_count == 1
        assert await state.get_state() is None
        assert any(isinstance(call, EditMessageText) and "Private Shares: 213" in call.text
                   for call in session.calls)
        assert any(isinstance(call, SendDocument) and call.document.filename == "Post_hisoboti.xlsx"
                   for call in session.calls)
        await send(LINK, 15)  # A direct link also works from the main menu.
        assert collect.await_count == 2
        await send("/post " + LINK, 16)
        assert collect.await_count == 3
        await send("📋 Post hisoboti", 17)
        await send("🗓 Shu oy", 18)  # Existing navigation wins over the pending post state.
        assert await state.get_state() == search.SearchState.keywords.state
        await send("📋 Post hisoboti", 19)
        await send("📢 Kanallar", 20)
        assert await state.get_state() is None
        await send("📋 Post hisoboti", 21)
        await send("/cancel", 22)
        assert await state.get_state() is None
        from app.bot.handlers import post_range
        monkeypatch.setattr(post_range, "WORK_ROOT", tmp_path / "spool")
        monkeypatch.setattr(post_range, "get_tashkent_now", lambda: datetime(2026, 10, 22, 12, tzinfo=TASHKENT_TZ))

        async def collect_range(selected, store, progress):
            assert selected.start.isoformat() == selected.end.isoformat() == "2026-10-21"
            store.save_post(post_result, selected.start)
        ranged = AsyncMock(side_effect=collect_range)
        monkeypatch.setattr(post_range.service, "collect", ranged)
        await send("🆕 Oxirgi reklamalar", 23)
        await send("🗓 Postlar hisoboti", 24)
        assert await state.get_state() == post_range.PostRangeState.start.state
        await send("bad date", 25)
        assert await state.get_state() == post_range.PostRangeState.start.state
        await send("2026-10-21", 26)
        assert await state.get_state() == post_range.PostRangeState.end.state
        await send("2026-10-20", 27)
        assert await state.get_state() == post_range.PostRangeState.end.state
        await send("2026-10-21", 28)
        ranged.assert_awaited_once()
        assert await state.get_state() is None
        assert any(isinstance(call, SendDocument) and call.document.filename == "Postlar_2026-10-21_2026-10-21.xlsx"
                   for call in session.calls)
        assert not list((tmp_path / "spool").iterdir())
        await send("/posts_range", 29)
        await send("📋 Post hisoboti", 30)
        assert await state.get_state() == post_report.PostReportState.link.state
        await send("🗓 Postlar hisoboti", 31)
        await send("🗓 Shu oy", 32)
        assert await state.get_state() == search.SearchState.keywords.state
        await send("/cancel", 33)
        # Post reports have not queried or changed the saved-channel search service.
        assert search_fn.await_count == 1 and load.await_count == 1
    finally:
        search.reports.clear()
        await dp.storage.close()
        await bot.session.close()


@pytest.mark.asyncio
async def test_report_callbacks_are_owner_scoped_and_do_not_requery_telegram():
    report = example_report()
    token = search.cache_report((777, 777), report)
    callback = AsyncMock()
    callback.data = f"search:excel:{token}"
    callback.message.chat.id = 777
    callback.from_user.id = 888
    await search.cached_result(callback)
    callback.answer.assert_awaited_once()
    assert callback.answer.call_args.kwargs["show_alert"] is True
    callback.message.answer_document.assert_not_awaited()
    search.reports.clear()


@pytest.mark.asyncio
async def test_cancel_stops_running_telegram_request_and_frees_lock(monkeypatch):
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=777, user_id=777))
    await state.update_data(mode="latest")
    message = AsyncMock()
    message.text, message.chat.id, message.from_user.id = "@anotherbot", 777, 777
    @asynccontextmanager
    async def fake_db():
        yield object()
    monkeypatch.setattr(search, "get_db_session", fake_db)
    monkeypatch.setattr(search, "load_search_channels", AsyncMock(return_value=[example_report().channels[0].channel]))
    entered = asyncio.Event()
    async def blocked(*args):
        entered.set()
        await asyncio.Future()
    monkeypatch.setattr(search.service, "search", blocked)
    task = asyncio.create_task(search.execute_search(message, state))
    await asyncio.wait_for(entered.wait(), 2)
    await search.cancel_search(777, 777)
    await asyncio.wait_for(task, 2)
    assert not search.search_slots.locked()
    assert (777, 777) not in search.running
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_startup_does_not_start_automatic_scanning(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "init_db", AsyncMock())
    monkeypatch.setattr(main.settings, "ADMIN_IDS", [])
    monkeypatch.setattr(main.telegram_client_manager, "start", AsyncMock())
    monkeypatch.setattr(main.telegram_client_manager, "is_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "setup_bot_commands", AsyncMock())
    start = AsyncMock()
    monkeypatch.setattr(main.scheduler, "start", start)
    # Even an old deployment's ENABLE_AUTO_MONITORING=true must not start legacy jobs.
    monkeypatch.setattr(main.settings, "ENABLE_AUTO_MONITORING", True)
    await main.on_startup()
    start.assert_not_called()
