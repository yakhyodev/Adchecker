import pytest
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, User

from app.bot.middlewares.auth import AuthMiddleware
from app.database.models.administrator import Administrator
from app.core.security import UserRole
from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_auth_middleware_denies_unauthorized_user(monkeypatch, db_session: AsyncSession):
    # Mock settings.ADMIN_IDS to be empty
    monkeypatch.setattr(settings, "ADMIN_IDS", [])

    @asynccontextmanager
    async def mock_get_db_session():
        yield db_session

    monkeypatch.setattr("app.bot.middlewares.auth.get_db_session", mock_get_db_session)

    middleware = AuthMiddleware()

    # Create mock message from unauthorized user
    user = User(id=999999999, is_bot=False, first_name="Stranger")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.text = "/start"
    message.answer = AsyncMock()

    next_handler = AsyncMock()
    data = {}

    await middleware(next_handler, message, data)

    # Next handler must NOT be called
    next_handler.assert_not_called()
    # User must receive rejection message
    message.answer.assert_called_once_with(
        "⛔ Ushbu botdan foydalanish uchun ruxsatingiz mavjud emas."
    )


@pytest.mark.asyncio
async def test_auth_middleware_allows_authorized_superadmin(monkeypatch, db_session: AsyncSession):
    superadmin_id = 777777777
    monkeypatch.setattr(settings, "ADMIN_IDS", [superadmin_id])

    @asynccontextmanager
    async def mock_get_db_session():
        yield db_session

    monkeypatch.setattr("app.bot.middlewares.auth.get_db_session", mock_get_db_session)

    middleware = AuthMiddleware()

    user = User(id=superadmin_id, is_bot=False, first_name="Boss", username="superadmin")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.text = "/start"
    message.answer = AsyncMock()

    next_handler = AsyncMock()
    data = {}

    await middleware(next_handler, message, data)

    # Next handler MUST be called
    next_handler.assert_called_once()
    assert data.get("is_superadmin") is True
    assert data.get("admin_role") == UserRole.SUPERADMIN.value


@pytest.mark.asyncio
async def test_anonymous_update_cannot_bypass_user_authorization():
    event = MagicMock(spec=Message)
    event.from_user = None
    handler = AsyncMock()
    await AuthMiddleware()(handler, event, {})
    handler.assert_not_awaited()
