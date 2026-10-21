from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.advertisement import Advertisement
from app.database.models.channel import Channel


class AdRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, ad_id: int) -> Optional[Advertisement]:
        stmt = (
            select(Advertisement)
            .options(selectinload(Advertisement.channel))
            .where(Advertisement.id == ad_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_channel_and_msg_id(
        self, channel_id: int, message_id: int
    ) -> Optional[Advertisement]:
        stmt = (
            select(Advertisement)
            .options(selectinload(Advertisement.channel))
            .where(
                and_(
                    Advertisement.channel_id == channel_id,
                    Advertisement.message_id == message_id,
                )
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def upsert_ad(
        self,
        channel_id: int,
        message_id: int,
        post_url: str,
        post_text: Optional[str],
        posted_at: datetime,
        media_type: Optional[str] = None,
        views: Optional[int] = None,
        reactions: Optional[int] = None,
        forwards: Optional[int] = None,
    ) -> Tuple[Advertisement, bool]:
        """Upserts an ad record. Returns (Advertisement, is_new)."""
        existing = await self.get_by_channel_and_msg_id(channel_id, message_id)
        utc_now = datetime.now(timezone.utc)

        if existing:
            # Update metrics if provided
            if views is not None:
                existing.views = views
            if reactions is not None:
                existing.reactions = reactions
            if forwards is not None:
                existing.forwards = forwards
            if post_text is not None and not existing.post_text:
                existing.post_text = post_text
            if media_type is not None and not existing.media_type:
                existing.media_type = media_type

            existing.post_url = post_url
            existing.last_updated_at = utc_now
            existing.status = "active"
            existing.is_deleted_from_tg = False

            await self.session.flush()
            return existing, False

        # Create new ad
        new_ad = Advertisement(
            channel_id=channel_id,
            message_id=message_id,
            post_url=post_url,
            post_text=post_text,
            posted_at=posted_at,
            media_type=media_type,
            views=views,
            reactions=reactions,
            forwards=forwards,
            status="active",
            is_deleted_from_tg=False,
            first_detected_at=utc_now,
            last_updated_at=utc_now,
        )
        self.session.add(new_ad)
        await self.session.flush()
        # Eagerly load channel
        await self.session.refresh(new_ad, ["channel"])
        return new_ad, True

    async def get_recent(
        self, limit: int = 10, offset: int = 0
    ) -> List[Advertisement]:
        stmt = (
            select(Advertisement)
            .join(Channel, Advertisement.channel_id == Channel.id)
            .where(Channel.is_deleted == False)
            .options(selectinload(Advertisement.channel))
            .order_by(Advertisement.posted_at.desc(), Advertisement.id.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def count_all(self) -> int:
        stmt = (
            select(func.count(Advertisement.id))
            .join(Channel, Advertisement.channel_id == Channel.id)
            .where(Channel.is_deleted == False)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one() or 0

    async def get_ads_in_period(
        self,
        start_dt_utc: datetime,
        end_dt_utc: datetime,
        channel_id: Optional[int] = None,
    ) -> List[Advertisement]:
        stmt = (
            select(Advertisement)
            .join(Channel, Advertisement.channel_id == Channel.id)
            .where(
                and_(
                    Channel.is_deleted == False,
                    Advertisement.posted_at >= start_dt_utc,
                    Advertisement.posted_at <= end_dt_utc,
                )
            )
            .options(selectinload(Advertisement.channel))
            .order_by(Advertisement.posted_at.desc(), Advertisement.id.desc())
        )
        if channel_id is not None:
            stmt = stmt.where(Advertisement.channel_id == channel_id)

        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_active_ads_for_stats_update(
        self,
        channel_id: Optional[int] = None,
        min_posted_at: Optional[datetime] = None,
        max_posted_at: Optional[datetime] = None,
    ) -> List[Advertisement]:
        stmt = (
            select(Advertisement)
            .join(Channel, Advertisement.channel_id == Channel.id)
            .where(
                and_(
                    Channel.is_deleted == False,
                    Advertisement.is_deleted_from_tg == False,
                )
            )
            .options(selectinload(Advertisement.channel))
            .order_by(Advertisement.last_updated_at.asc())
        )
        if channel_id is not None:
            stmt = stmt.where(Advertisement.channel_id == channel_id)
        if min_posted_at is not None:
            stmt = stmt.where(Advertisement.posted_at >= min_posted_at)
        if max_posted_at is not None:
            stmt = stmt.where(Advertisement.posted_at <= max_posted_at)

        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def mark_as_deleted(self, ad_id: int) -> None:
        ad = await self.get_by_id(ad_id)
        if ad:
            ad.is_deleted_from_tg = True
            ad.status = "deleted"
            ad.last_updated_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def update_ad_cost(self, ad_id: int, cost: float) -> Optional[Advertisement]:
        ad = await self.get_by_id(ad_id)
        if ad:
            ad.cost = cost
            await self.session.flush()
        return ad
