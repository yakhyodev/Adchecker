import asyncio
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import post_report
from app.bot.operations import cancel_operation, running
from app.services.post_report import MISSING, PostReportUnavailable
from tests.test_post_report import LINK, NOW, post, channel


def state_and_message(user=777):
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=user, user_id=user))
    message = AsyncMock()
    message.chat.id = message.from_user.id = user
    return state, message


@pytest.mark.asyncio
async def test_cancel_stops_post_request_and_releases_slot(monkeypatch):
    state, message = state_and_message()
    entered = asyncio.Event()

    async def blocked(raw):
        entered.set()
        await asyncio.Future()

    monkeypatch.setattr(post_report.service, "collect", blocked)
    task = asyncio.create_task(post_report.run_report(message, state, LINK))
    await asyncio.wait_for(entered.wait(), 2)
    await cancel_operation(777, 777)
    await asyncio.wait_for(task, 2)
    assert not post_report.report_slots.locked()
    assert (777, 777) not in running
    assert await state.get_state() is None
    message.answer_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_waiting_report_is_cancellable_without_querying_telegram(monkeypatch):
    state, message = state_and_message()
    semaphore = asyncio.Semaphore(1)
    await semaphore.acquire()
    monkeypatch.setattr(post_report, "report_slots", semaphore)
    collect = AsyncMock()
    monkeypatch.setattr(post_report.service, "collect", collect)
    task = asyncio.create_task(post_report.run_report(message, state, LINK))
    for _ in range(20):
        if (777, 777) in running and message.answer.await_count:
            break
        await asyncio.sleep(0)
    await cancel_operation(777, 777)
    await asyncio.wait_for(task, 2)
    collect.assert_not_awaited()
    assert await state.get_state() is None
    semaphore.release()


@pytest.mark.asyncio
async def test_missing_post_shows_information_without_error_log(monkeypatch, caplog):
    state, message = state_and_message()
    monkeypatch.setattr(post_report.service, "collect", AsyncMock(side_effect=PostReportUnavailable(MISSING)))
    await post_report.run_report(message, state, LINK)
    wait = message.answer.return_value
    assert any(MISSING in call.args[0] for call in wait.edit_text.await_args_list)
    message.answer_document.assert_not_awaited()
    assert not caplog.records
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_invalid_input_makes_no_api_call(monkeypatch):
    state, message = state_and_message()
    collect = AsyncMock()
    monkeypatch.setattr(post_report.service, "collect", collect)
    await post_report.run_report(message, state, "not a post")
    collect.assert_not_awaited()
    assert await state.get_state() == post_report.PostReportState.link.state


@pytest.mark.asyncio
async def test_deleted_status_message_does_not_prevent_excel_delivery(monkeypatch):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import EditMessageText
    from app.services.post_report import PostReport, metrics

    state, message = state_and_message()
    report = PostReport(source=metrics(post(), channel()), checked_at=NOW, forwards_complete=True)
    monkeypatch.setattr(post_report.service, "collect", AsyncMock(return_value=report))
    wait = message.answer.return_value
    wait.edit_text.side_effect = TelegramBadRequest(
        method=EditMessageText(text="test"), message="message to edit not found")
    await post_report.run_report(message, state, LINK)
    message.answer_document.assert_awaited_once()
    assert any("POST HISOBOTI" in call.args[0] for call in message.answer.await_args_list)
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_failed_status_and_cleanup_messages_do_not_block_report_or_leave_running_state(monkeypatch):
    from aiogram.exceptions import TelegramNetworkError
    from aiogram.methods import SendMessage
    from app.services.post_report import PostReport, metrics

    state, message = state_and_message()
    report = PostReport(source=metrics(post(), channel()), checked_at=NOW, forwards_complete=True)
    monkeypatch.setattr(post_report.service, "collect", AsyncMock(return_value=report))
    message.answer.side_effect = TelegramNetworkError(method=SendMessage(chat_id=777, text="test"), message="unreachable")
    await post_report.run_report(message, state, LINK)
    message.answer_document.assert_awaited_once()
    assert await state.get_state() is None and (777, 777) not in running
    assert not post_report.report_slots.locked()


def test_direct_link_accepts_surrounding_whitespace_and_case():
    assert post_report.is_post_link("  HTTPS://T.ME/imkonsavdomarkazi/5644  ")
    assert not post_report.is_post_link(None)


def test_partial_report_explains_transport_failure_without_inventing_missing_data():
    from app.services.post_report import PostReport, metrics
    report = PostReport(source=metrics(post(), channel()), checked_at=NOW,
                        notice="Telegram bilan ulanish tugamadi.")
    text = post_report.summary(report)
    assert "ulanish tugamadi" in text and "to'liq olinmadi" in text
