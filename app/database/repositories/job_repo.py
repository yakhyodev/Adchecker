from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.monitoring_job import MonitoringJob


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_job(
        self,
        job_type: str,
        channel_id: Optional[int] = None,
        status: str = "pending",
    ) -> MonitoringJob:
        job = MonitoringJob(
            job_type=job_type,
            channel_id=channel_id,
            status=status,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_by_id(self, job_id: int) -> Optional[MonitoringJob]:
        stmt = (
            select(MonitoringJob)
            .options(selectinload(MonitoringJob.channel))
            .where(MonitoringJob.id == job_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def has_active_job(
        self, channel_id: int, job_type: Optional[str] = None
    ) -> bool:
        """Checks if a job is currently pending or scanning for the given channel."""
        conditions = [
            MonitoringJob.channel_id == channel_id,
            MonitoringJob.status.in_(["pending", "scanning"]),
        ]
        if job_type:
            conditions.append(MonitoringJob.job_type == job_type)

        stmt = select(MonitoringJob).where(and_(*conditions)).limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none() is not None

    async def update_status(
        self,
        job_id: int,
        status: str,
        posts_scanned: int = 0,
        ads_found: int = 0,
        error_message: Optional[str] = None,
    ) -> Optional[MonitoringJob]:
        job = await self.get_by_id(job_id)
        if not job:
            return None
        job.status = status
        job.posts_scanned = posts_scanned
        job.ads_found = ads_found
        job.error_message = error_message
        if status in ("completed", "failed"):
            job.finished_at = datetime.now(timezone.utc)
        await self.session.flush()
        return job

    async def get_recent(self, limit: int = 10) -> List[MonitoringJob]:
        stmt = (
            select(MonitoringJob)
            .options(selectinload(MonitoringJob.channel))
            .order_by(MonitoringJob.started_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_active_count(self) -> int:
        stmt = select(MonitoringJob).where(
            MonitoringJob.status.in_(["pending", "scanning"])
        )
        res = await self.session.execute(stmt)
        return len(res.scalars().all())
