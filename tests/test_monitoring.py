from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon.errors import FloodWaitError

from app.database.repositories.snapshot_repo import SnapshotRepository
from app.services.monitoring import MonitoringService
from app.telegram_client.client import TelegramClientManager


def make_client(result=None, error=None):
    # Avoid opening another on-disk session; exercise the real fetch implementation.
    manager = TelegramClientManager.__new__(TelegramClientManager)
    manager._is_started = True
    manager.client = SimpleNamespace(get_messages=AsyncMock(return_value=result, side_effect=error))
    manager.resolve_channel = AsyncMock(return_value={"entity": object()})
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError("timeout"), ConnectionError("offline")])
async def test_failed_stats_request_preserves_ad_and_can_retry(db_session, sample_ad, error):
    client = make_client(error=error)
    service = MonitoringService(db_session, tg_client=client)
    result = await service.run_stats_update()
    assert result == {"status": "partial", "type": "recent", "updated": 0, "deleted": 0, "failed": 1}
    assert sample_ad.is_deleted_from_tg is False
    assert sample_ad.views == 15000
    assert await SnapshotRepository(db_session).get_snapshots_for_ad(sample_ad.id) == []

    client.client.get_messages.side_effect = None
    client.client.get_messages.return_value = [SimpleNamespace(views=16000, forwards=50, reactions=None)]
    result = await service.run_stats_update()
    assert result["updated"] == 1
    assert result["status"] == "completed"
    assert sample_ad.views == 16000
    assert len(await SnapshotRepository(db_session).get_snapshots_for_ad(sample_ad.id)) == 1


@pytest.mark.asyncio
async def test_confirmed_missing_message_is_marked_deleted(db_session, sample_ad):
    client = make_client(result=[None])
    result = await MonitoringService(db_session, tg_client=client).run_stats_update()
    assert result["deleted"] == 1
    assert result["failed"] == 0
    assert sample_ad.is_deleted_from_tg is True


@pytest.mark.asyncio
async def test_flood_wait_preserves_ad(db_session, sample_ad):
    error = FloodWaitError(request=None)
    error.seconds = 42
    client = make_client(error=error)
    result = await MonitoringService(db_session, tg_client=client).run_stats_update()
    assert result["status"] == "partial"
    assert result["deleted"] == 0
    assert sample_ad.is_deleted_from_tg is False


@pytest.mark.asyncio
@pytest.mark.parametrize("update_type", ["recent", "old"])
async def test_paused_channel_is_skipped_then_resumes(db_session, sample_ad, update_type):
    from datetime import datetime, timezone, timedelta
    from app.database.repositories.channel_repo import ChannelRepository

    sample_ad.posted_at = datetime.now(timezone.utc) - timedelta(days=10 if update_type == "old" else 1)
    repo = ChannelRepository(db_session)
    await repo.set_active(sample_ad.channel_id, False)
    client = make_client(result=[SimpleNamespace(views=18000, forwards=60, reactions=None)])
    service = MonitoringService(db_session, tg_client=client)
    result = await service.run_stats_update(update_type)
    assert result["updated"] == 0
    client.resolve_channel.assert_not_awaited()
    client.client.get_messages.assert_not_awaited()

    await repo.set_active(sample_ad.channel_id, True)
    result = await service.run_stats_update(update_type)
    assert result["updated"] == 1
    assert sample_ad.views == 18000
