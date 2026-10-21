from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.channel import Channel


class ChannelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, channel_id: int) -> Optional[Channel]:
        stmt = select(Channel).where(Channel.id == channel_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_tg_id(self, telegram_channel_id: int) -> Optional[Channel]:
        stmt = select(Channel).where(Channel.telegram_channel_id == telegram_channel_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[Channel]:
        clean_user = username.lstrip("@").lower()
        stmt = select(Channel).where(Channel.username.ilike(clean_user))
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_all_active(self) -> List[Channel]:
        stmt = (
            select(Channel)
            .where(Channel.is_active == True, Channel.is_deleted == False)
            .order_by(Channel.title.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_all(self, include_deleted: bool = False) -> List[Channel]:
        stmt = select(Channel)
        if not include_deleted:
            stmt = stmt.where(Channel.is_deleted == False)
        stmt = stmt.order_by(Channel.created_at.desc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create(
        self,
        telegram_channel_id: int,
        title: str,
        username: Optional[str],
        url: str,
        cpm_price: Optional[float] = None,
    ) -> Channel:
        # Check if already exists (even if soft-deleted)
        existing = await self.get_by_tg_id(telegram_channel_id)
        if existing:
            if existing.is_deleted:
                existing.is_deleted = False
                existing.is_active = True
                existing.title = title
                existing.username = username
                existing.url = url
                if cpm_price is not None:
                    existing.cpm_price = cpm_price
                await self.session.flush()
                return existing
            return existing

        channel = Channel(
            telegram_channel_id=telegram_channel_id,
            title=title,
            username=username,
            url=url,
            cpm_price=cpm_price,
            is_active=True,
            is_deleted=False,
        )
        self.session.add(channel)
        await self.session.flush()
        return channel

    async def set_active(self, channel_id: int, is_active: bool) -> Optional[Channel]:
        channel = await self.get_by_id(channel_id)
        if not channel:
            return None
        channel.is_active = is_active
        await self.session.flush()
        return channel

    async def soft_delete(self, channel_id: int) -> bool:
        channel = await self.get_by_id(channel_id)
        if not channel:
            return False
        channel.is_deleted = True
        channel.is_active = False
        await self.session.flush()
        return True

    async def update_scan_state(
        self, channel_id: int, last_msg_id: Optional[int], scanned_at: datetime
    ) -> None:
        stmt = (
            update(Channel)
            .where(Channel.id == channel_id)
            .values(last_scanned_message_id=last_msg_id, last_scanned_at=scanned_at)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def update_cpm_price(
        self, channel_id: int, cpm_price: Optional[float]
    ) -> Optional[Channel]:
        channel = await self.get_by_id(channel_id)
        if not channel:
            return None
        channel.cpm_price = cpm_price
        await self.session.flush()
        return channel
