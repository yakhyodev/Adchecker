import pytest
from unittest.mock import AsyncMock, MagicMock
from telethon.errors import FloodWaitError, ChannelPrivateError, UsernameNotOccupiedError
from telethon.tl.types import Channel as TelethonChannel

from app.telegram_client.client import (
    TelegramClientManager,
    ChannelNotFoundError,
    ChannelAccessDeniedError,
    TelegramFloodWaitException,
)
from app.services.channel_service import ChannelService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_resolve_channel_success():
    client_mgr = TelegramClientManager(api_id=123, api_hash="0123456789abcdef0123456789abcdef")
    client_mgr._is_started = True

    mock_entity = MagicMock(spec=TelethonChannel)
    mock_entity.id = 123456789
    mock_entity.title = "Imkon Savdo"
    mock_entity.username = "imkon_savdo"
    mock_entity.broadcast = True

    client_mgr.client.get_entity = AsyncMock(return_value=mock_entity)

    res = await client_mgr.resolve_channel("https://t.me/imkon_savdo")
    assert res["telegram_channel_id"] == -100123456789
    assert res["title"] == "Imkon Savdo"
    assert res["username"] == "imkon_savdo"


@pytest.mark.asyncio
async def test_resolve_channel_flood_wait():
    client_mgr = TelegramClientManager(api_id=123, api_hash="0123456789abcdef0123456789abcdef")
    client_mgr._is_started = True

    flood_err = FloodWaitError(request=None)
    flood_err.seconds = 42
    client_mgr.client.get_entity = AsyncMock(side_effect=flood_err)

    with pytest.raises(TelegramFloodWaitException) as excinfo:
        await client_mgr.resolve_channel("mychannel")

    assert excinfo.value.seconds == 42


@pytest.mark.asyncio
async def test_resolve_channel_not_found():
    client_mgr = TelegramClientManager(api_id=123, api_hash="0123456789abcdef0123456789abcdef")
    client_mgr._is_started = True
    client_mgr.client.get_entity = AsyncMock(side_effect=UsernameNotOccupiedError(request=None))

    with pytest.raises(ChannelNotFoundError):
        await client_mgr.resolve_channel("not_existing_channel")


@pytest.mark.asyncio
async def test_resolve_channel_private_forbidden():
    client_mgr = TelegramClientManager(api_id=123, api_hash="0123456789abcdef0123456789abcdef")
    client_mgr._is_started = True
    client_mgr.client = AsyncMock(side_effect=ChannelPrivateError(request=None))

    with pytest.raises(ChannelAccessDeniedError):
        await client_mgr.resolve_channel("+AbCdEf123")


@pytest.mark.asyncio
async def test_private_invite_reads_existing_membership_without_joining():
    from telethon.tl.types import ChatInviteAlready
    from telethon.tl.functions.messages import CheckChatInviteRequest
    client_mgr = TelegramClientManager(api_id=123, api_hash="0123456789abcdef0123456789abcdef")
    client_mgr._is_started = True
    entity = MagicMock(spec=TelethonChannel)
    entity.id, entity.title, entity.username, entity.broadcast = 123456789, "Private", None, True
    client_mgr.client = AsyncMock(return_value=ChatInviteAlready(chat=entity))
    result = await client_mgr.resolve_channel("https://t.me/+ExistingInvite")
    assert result["telegram_channel_id"] == -100123456789
    assert result["url"] == "https://t.me/c/123456789"
    assert isinstance(client_mgr.client.call_args.args[0], CheckChatInviteRequest)
    assert client_mgr.client.await_count == 1


@pytest.mark.asyncio
async def test_invite_without_membership_does_not_join_channel():
    client_mgr = TelegramClientManager(api_id=123, api_hash="0123456789abcdef0123456789abcdef")
    client_mgr._is_started = True
    client_mgr.client = AsyncMock(return_value=object())
    with pytest.raises(ChannelAccessDeniedError):
        await client_mgr.resolve_channel("https://t.me/+NotJoined")
    assert client_mgr.client.await_count == 1


@pytest.mark.asyncio
async def test_supergroup_is_not_saved_as_advertising_channel():
    client_mgr = TelegramClientManager(api_id=123, api_hash="0123456789abcdef0123456789abcdef")
    client_mgr._is_started = True
    entity = MagicMock(spec=TelethonChannel)
    entity.broadcast = False
    client_mgr.client.get_entity = AsyncMock(return_value=entity)
    with pytest.raises(ChannelNotFoundError):
        await client_mgr.resolve_channel("@some_group")


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["-100123456789", "https://t.me/c/123456789/555"])
async def test_saved_channel_id_and_private_post_link_resolve_without_username(target):
    client_mgr = TelegramClientManager(api_id=123, api_hash="0123456789abcdef0123456789abcdef")
    client_mgr._is_started = True
    entity = MagicMock(spec=TelethonChannel)
    entity.id, entity.title, entity.username, entity.broadcast = 123456789, "Renamed", "new_name", True
    client_mgr.client.get_entity = AsyncMock(return_value=entity)
    result = await client_mgr.resolve_channel(target)
    client_mgr.client.get_entity.assert_awaited_once_with(-100123456789)
    assert result["telegram_channel_id"] == -100123456789
