from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
import app.main as application


def test_runtime_rejects_placeholder_settings_without_exposing_values():
    settings = Settings(_env_file=None, BOT_TOKEN="123456:TEST_BOT_TOKEN", ADMIN_IDS=[],
                        TELEGRAM_API_ID=123456, TELEGRAM_API_HASH="0123456789abcdef0123456789abcdef")
    with pytest.raises(RuntimeError) as exc:
        settings.validate_runtime()
    message = str(exc.value)
    for name in ("BOT_TOKEN", "ADMIN_IDS", "TELEGRAM_API_ID", "TELEGRAM_API_HASH"):
        assert name in message
    assert settings.BOT_TOKEN not in message
    assert settings.TELEGRAM_API_HASH not in message


def test_runtime_accepts_configured_credentials():
    settings = Settings(_env_file=None, BOT_TOKEN="987654321:synthetic_test_token_only",
                        ADMIN_IDS="777777,888888", TELEGRAM_API_ID=7654321,
                        TELEGRAM_API_HASH="a" * 32)
    settings.validate_runtime()


@pytest.mark.asyncio
async def test_startup_failure_still_cleans_up(monkeypatch):
    monkeypatch.setattr(Settings, "validate_runtime", lambda self: None)
    monkeypatch.setattr(application, "setup_logging", lambda level: None)
    monkeypatch.setattr(application, "setup_dispatcher", lambda: None)
    monkeypatch.setattr(application, "on_startup", AsyncMock(side_effect=RuntimeError("DB unavailable")))
    cleanup = AsyncMock()
    monkeypatch.setattr(application, "on_shutdown", cleanup)
    with pytest.raises(RuntimeError, match="DB unavailable"):
        await application.main()
    cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_unconfigured_startup_opens_no_network_connections(monkeypatch):
    monkeypatch.setattr(application, "settings", Settings(
        _env_file=None, BOT_TOKEN="123456:TEST_BOT_TOKEN", ADMIN_IDS=[],
        TELEGRAM_API_ID=123456, TELEGRAM_API_HASH="0123456789abcdef0123456789abcdef",
    ))
    monkeypatch.setattr(application, "setup_logging", lambda level: None)
    startup = AsyncMock()
    monkeypatch.setattr(application, "on_startup", startup)
    with pytest.raises(RuntimeError, match=".env sozlamalarini"):
        await application.main()
    startup.assert_not_awaited()
