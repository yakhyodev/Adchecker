import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.channel_repo import ChannelRepository
from app.database.repositories.ad_repo import AdRepository
from app.database.repositories.snapshot_repo import SnapshotRepository
from app.database.repositories.job_repo import JobRepository
from app.database.models.channel import Channel
from app.database.models.advertisement import Advertisement


@pytest.mark.asyncio
async def test_duplicate_channel_prevention(db_session: AsyncSession):
    repo = ChannelRepository(db_session)

    # 1. First add
    ch1 = await repo.create(
        telegram_channel_id=-100111222333,
        title="Kanal 1",
        username="kanal1",
        url="https://t.me/kanal1",
    )
    assert ch1.id is not None

    # 2. Second add of identical telegram_channel_id
    ch2 = await repo.create(
        telegram_channel_id=-100111222333,
        title="Kanal 1 yangilangan",
        username="kanal1",
        url="https://t.me/kanal1",
    )
    # Must return the existing record and not create duplicate
    assert ch2.id == ch1.id

    all_channels = await repo.get_all()
    assert len(all_channels) == 1


@pytest.mark.asyncio
async def test_duplicate_ad_prevention(db_session: AsyncSession, sample_channel: Channel):
    repo = AdRepository(db_session)
    now = datetime.now(timezone.utc)

    # 1. Insert new ad
    ad1, is_new1 = await repo.upsert_ad(
        channel_id=sample_channel.id,
        message_id=200,
        post_url="https://t.me/chan/200",
        post_text="Chegirma! @imkonhelpbot",
        posted_at=now,
        media_type="photo",
        views=5000,
    )
    assert is_new1 is True
    assert ad1.views == 5000

    # 2. Re-upsert with same channel_id and message_id with updated views
    ad2, is_new2 = await repo.upsert_ad(
        channel_id=sample_channel.id,
        message_id=200,
        post_url="https://t.me/chan/200",
        post_text="Chegirma! @imkonhelpbot",
        posted_at=now,
        views=7500,
    )
    assert is_new2 is False
    assert ad2.id == ad1.id
    assert ad2.views == 7500

    total_count = await repo.count_all()
    assert total_count == 1


@pytest.mark.asyncio
async def test_soft_delete_channel(db_session: AsyncSession, sample_channel: Channel):
    repo = ChannelRepository(db_session)

    success = await repo.soft_delete(sample_channel.id)
    assert success is True

    # Active channels must not include deleted channel
    active = await repo.get_all_active()
    assert sample_channel.id not in [c.id for c in active]

    # But database record still exists
    fetched = await repo.get_by_id(sample_channel.id)
    assert fetched.is_deleted is True


@pytest.mark.asyncio
async def test_deleted_post_status(db_session: AsyncSession, sample_ad: Advertisement):
    repo = AdRepository(db_session)

    await repo.mark_as_deleted(sample_ad.id)
    ad = await repo.get_by_id(sample_ad.id)

    assert ad.is_deleted_from_tg is True
    assert ad.status == "deleted"


@pytest.mark.asyncio
async def test_view_snapshot_and_growth_calculation(
    db_session: AsyncSession, sample_ad: Advertisement
):
    snap_repo = SnapshotRepository(db_session)
    now = datetime.now(timezone.utc)

    # 1. Add snapshot 24 hours ago
    past_24h = now - timedelta(hours=24)
    await snap_repo.add_snapshot(
        advertisement_id=sample_ad.id,
        views=10000,
        reactions=50,
        forwards=20,
        recorded_at=past_24h,
    )

    # 2. Add current snapshot
    await snap_repo.add_snapshot(
        advertisement_id=sample_ad.id,
        views=15000,
        reactions=80,
        forwards=30,
        recorded_at=now,
    )

    # Calculate 24h growth
    growth = await snap_repo.calculate_growth(
        advertisement_id=sample_ad.id,
        current_views=15000,
        hours_ago=24,
        tolerance_hours=2.0,
    )

    assert growth is not None
    assert growth["initial_views"] == 10000
    assert growth["current_views"] == 15000
    assert growth["growth_views"] == 5000
    assert growth["growth_percent"] == 50.0


@pytest.mark.asyncio
async def test_job_concurrency_lock(db_session: AsyncSession, sample_channel: Channel):
    job_repo = JobRepository(db_session)

    # No job initially
    assert await job_repo.has_active_job(sample_channel.id) is False

    # Create active job
    job = await job_repo.create_job(
        job_type="initial_scan",
        channel_id=sample_channel.id,
        status="scanning",
    )
    assert await job_repo.has_active_job(sample_channel.id, "initial_scan") is True

    # Finish job
    await job_repo.update_status(job.id, status="completed")
    assert await job_repo.has_active_job(sample_channel.id, "initial_scan") is False
