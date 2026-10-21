from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import BigInteger, String, Boolean, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.models.base import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_channel_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    username: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cpm_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_scanned_message_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    advertisements: Mapped[List["Advertisement"]] = relationship(
        "Advertisement", back_populates="channel", cascade="all, delete-orphan"
    )
    monitoring_jobs: Mapped[List["MonitoringJob"]] = relationship(
        "MonitoringJob", back_populates="channel"
    )

    def __repr__(self) -> str:
        return f"<Channel(id={self.id}, title='{self.title}', username='{self.username}')>"
