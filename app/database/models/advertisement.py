from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    BigInteger,
    String,
    Boolean,
    DateTime,
    Numeric,
    Text,
    Integer,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.models.base import Base


class Advertisement(Base):
    __tablename__ = "advertisements"
    __table_args__ = (
        UniqueConstraint("channel_id", "message_id", name="uq_channel_message"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    message_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    post_url: Mapped[str] = mapped_column(String(255), nullable=False)
    post_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    media_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    views: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reactions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    forwards: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    is_deleted_from_tg: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    channel: Mapped["Channel"] = relationship("Channel", back_populates="advertisements")
    snapshots: Mapped[List["ViewSnapshot"]] = relationship(
        "ViewSnapshot", back_populates="advertisement", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Advertisement(id={self.id}, channel_id={self.channel_id}, msg_id={self.message_id}, views={self.views})>"
