from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message, User

from app.bot.handlers import channels, settings as settings_handlers, statistics
from app.bot.middlewares.auth import AuthMiddleware
from app.database.repositories.settings_repo import SettingsRepository


WRITE_HANDLERS = [
    (channels.router.callback_query, "callback_add_channel_prompt"),
    (channels.router.message, "process_channel_input"),
    (channels.router.callback_query, "callback_toggle_channel"),
    (channels.router.callback_query, "callback_delete_confirm"),
    (channels.router.callback_query, "callback_delete_execute"),
    (channels.router.callback_query, "callback_scan_choice"),
    (channels.router.callback_query, "callback_execute_scan"),
    (channels.router.callback_query, "callback_price_prompt"),
    (channels.router.message, "process_channel_price"),
    (settings_handlers.router.callback_query, "callback_toggle_auto"),
    (settings_handlers.router.callback_query, "callback_keywords"),
    (settings_handlers.router.message, "process_new_keywords"),
    (statistics.router.message, "handle_manual_refresh"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("observer,name", WRITE_HANDLERS, ids=[item[1] for item in WRITE_HANDLERS])
async def test_viewer_cannot_execute_registered_write_handlers(
    monkeypatch, db_session, sample_admin, observer, name
):
    sample_admin.role = "viewer"
    await db_session.flush()
    @asynccontextmanager
    async def session_context():
        yield db_session
    monkeypatch.setattr("app.bot.middlewares.auth.get_db_session", session_context)
    registrations = [h for h in observer.handlers if h.callback.__name__ == name]
    assert registrations
    for registered in registrations:
        assert registered.flags.get("requires_write") is True
        event = MagicMock(spec=CallbackQuery if observer.event_name == "callback_query" else Message)
        event.from_user = User(id=sample_admin.telegram_user_id, is_bot=False, first_name="Viewer")
        event.answer = AsyncMock()
        handler = AsyncMock()
        await AuthMiddleware()(handler, event, {"handler": registered})
        handler.assert_not_awaited()
        event.answer.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["viewer", "admin", "superadmin"])
async def test_toggle_auto_permission_changes_real_database_only_for_admins(
    monkeypatch, db_session, sample_admin, role
):
    sample_admin.role = role
    await db_session.flush()
    @asynccontextmanager
    async def session_context():
        yield db_session
    monkeypatch.setattr("app.bot.middlewares.auth.get_db_session", session_context)
    monkeypatch.setattr(settings_handlers, "get_db_session", session_context)
    registered = next(h for h in settings_handlers.router.callback_query.handlers
                      if h.callback is settings_handlers.callback_toggle_auto)
    event = MagicMock(spec=CallbackQuery)
    event.from_user = User(id=sample_admin.telegram_user_id, is_bot=False, first_name="Test")
    event.answer = AsyncMock()
    event.message = MagicMock(spec=Message)
    event.message.edit_reply_markup = AsyncMock()
    before = await SettingsRepository(db_session).is_auto_monitoring_enabled()
    async def handler(callback, data):
        await settings_handlers.callback_toggle_auto(callback)
    await AuthMiddleware()(handler, event, {"handler": registered})
    after = await SettingsRepository(db_session).is_auto_monitoring_enabled()
    assert after == (before if role == "viewer" else not before)


@pytest.mark.asyncio
async def test_viewer_can_still_read_reports(monkeypatch, db_session, sample_admin):
    sample_admin.role = "viewer"
    await db_session.flush()
    @asynccontextmanager
    async def session_context():
        yield db_session
    monkeypatch.setattr("app.bot.middlewares.auth.get_db_session", session_context)
    registered = next(h for h in statistics.router.message.handlers
                      if h.callback is statistics.handle_stats_week)
    event = MagicMock(spec=Message)
    event.from_user = User(id=sample_admin.telegram_user_id, is_bot=False, first_name="Viewer")
    handler = AsyncMock()
    await AuthMiddleware()(handler, event, {"handler": registered})
    handler.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["viewer", "admin"])
async def test_dispatcher_enforces_write_permission(monkeypatch, db_session, sample_admin, role):
    from datetime import datetime, timezone
    from aiogram import Bot, Dispatcher, Router
    from aiogram.types import Chat, Update

    sample_admin.role = role
    await db_session.flush()
    @asynccontextmanager
    async def session_context():
        yield db_session
    monkeypatch.setattr("app.bot.middlewares.auth.get_db_session", session_context)
    monkeypatch.setattr(settings_handlers, "get_db_session", session_context)
    registered = next(h for h in settings_handlers.router.callback_query.handlers
                      if h.callback is settings_handlers.callback_toggle_auto)
    router = Router()
    router.callback_query.register(
        registered.callback, *[f.callback for f in registered.filters], flags=registered.flags
    )
    dispatcher = Dispatcher()
    dispatcher.callback_query.middleware(AuthMiddleware())
    dispatcher.include_router(router)
    api = AsyncMock(return_value=True)
    bot = Bot("123456:TEST_BOT_TOKEN", session=api)
    user = User(id=sample_admin.telegram_user_id, is_bot=False, first_name="Test")
    update = Update(update_id=1, callback_query=CallbackQuery(
        id="test", from_user=user, chat_instance="test", data="set:toggle_auto",
        message=Message(message_id=1, date=datetime.now(timezone.utc),
                        chat=Chat(id=user.id, type="private")),
    ))
    before = await SettingsRepository(db_session).is_auto_monitoring_enabled()
    try:
        await dispatcher.feed_update(bot, update)
        after = await SettingsRepository(db_session).is_auto_monitoring_enabled()
        assert after == (before if role == "viewer" else not before)
    finally:
        await dispatcher.storage.close()
        await bot.session.close()
