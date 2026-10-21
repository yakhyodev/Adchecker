import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database.models.base import Base
from app.database.models.administrator import Administrator
from app.database.models.channel import Channel
from app.database.models.advertisement import Advertisement
from app.database.models.view_snapshot import ViewSnapshot
from app.core.security import UserRole


@pytest_asyncio.fixture
async def db_session():
    """Provides an isolated in-memory SQLite database session for each test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def sample_admin(db_session: AsyncSession) -> Administrator:
    admin = Administrator(
        telegram_user_id=123456789,
        username="testadmin",
        full_name="Test Administrator",
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def sample_channel(db_session: AsyncSession) -> Channel:
    channel = Channel(
        telegram_channel_id=-1001987654321,
        title="Toshkent Yangiliklari",
        username="toshkent_yangiliklar",
        url="https://t.me/toshkent_yangiliklar",
        cpm_price=250000.0,
        is_active=True,
        is_deleted=False,
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return channel


@pytest_asyncio.fixture
async def sample_ad(db_session: AsyncSession, sample_channel: Channel) -> Advertisement:
    ad = Advertisement(
        channel_id=sample_channel.id,
        message_id=105,
        post_url=f"https://t.me/toshkent_yangiliklar/105",
        post_text="IMKON savdo markazida ulkan chegirmalar! Bog'lanish: @imkonhelpbot",
        posted_at=datetime.now(timezone.utc),
        media_type="photo",
        views=15000,
        reactions=120,
        forwards=45,
        status="active",
        is_deleted_from_tg=False,
    )
    db_session.add(ad)
    await db_session.commit()
    await db_session.refresh(ad)
    return ad
