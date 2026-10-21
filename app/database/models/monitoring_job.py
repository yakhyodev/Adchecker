from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.models.base import Base


class MonitoringJob(Base):
    __tablename__ = "monitoring_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, scanning, completed, failed
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    posts_scanned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ads_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    channel: Mapped[Optional["Channel"]] = relationship(
        "Channel", back_populates="monitoring_jobs"
    )

    def __repr__(self) -> str:
        return f"<MonitoringJob(id={self.id}, type='{self.job_type}', status='{self.status}')>"
