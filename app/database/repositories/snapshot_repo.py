from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.view_snapshot import ViewSnapshot


class SnapshotRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_snapshot(
        self,
        advertisement_id: int,
        views: Optional[int],
        reactions: Optional[int],
        forwards: Optional[int],
        recorded_at: Optional[datetime] = None,
    ) -> ViewSnapshot:
        if recorded_at is None:
            recorded_at = datetime.now(timezone.utc)

        snapshot = ViewSnapshot(
            advertisement_id=advertisement_id,
            views=views,
            reactions=reactions,
            forwards=forwards,
            recorded_at=recorded_at,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def get_snapshots_for_ad(self, advertisement_id: int) -> List[ViewSnapshot]:
        stmt = (
            select(ViewSnapshot)
            .where(ViewSnapshot.advertisement_id == advertisement_id)
            .order_by(ViewSnapshot.recorded_at.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_snapshot_closest_to(
        self,
        advertisement_id: int,
        target_time: datetime,
        tolerance_hours: float = 4.0,
    ) -> Optional[ViewSnapshot]:
        """Finds the recorded snapshot closest to target_time within tolerance_hours."""
        min_time = target_time - timedelta(hours=tolerance_hours)
        max_time = target_time + timedelta(hours=tolerance_hours)

        stmt = (
            select(ViewSnapshot)
            .where(
                and_(
                    ViewSnapshot.advertisement_id == advertisement_id,
                    ViewSnapshot.recorded_at >= min_time,
                    ViewSnapshot.recorded_at <= max_time,
                )
            )
            .order_by(
                func.abs(
                    func.extract("epoch", ViewSnapshot.recorded_at)
                    - target_time.timestamp()
                )
            )
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def calculate_growth(
        self,
        advertisement_id: int,
        current_views: Optional[int],
        hours_ago: int = 24,
        tolerance_hours: float = 4.0,
    ) -> Optional[Dict[str, Any]]:
        """Calculates views growth over the specified hours ago.
        Returns None if no snapshot exists within the tolerance window or views are None.
        """
        if current_views is None:
            return None

        target_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        past_snap = await self.get_snapshot_closest_to(
            advertisement_id, target_time, tolerance_hours=tolerance_hours
        )
        if not past_snap or past_snap.views is None:
            return None

        growth = current_views - past_snap.views
        percent = (
            (growth / past_snap.views * 100)
            if past_snap.views > 0
            else (100.0 if growth > 0 else 0.0)
        )

        return {
            "period_hours": hours_ago,
            "recorded_at": past_snap.recorded_at,
            "initial_views": past_snap.views,
            "current_views": current_views,
            "growth_views": growth,
            "growth_percent": round(percent, 2),
        }
