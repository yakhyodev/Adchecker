from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Integer,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.models.base import Base


class ViewSnapshot(Base):
    __tablename__ = "view_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    advertisement_id: Mapped[int] = mapped_column(
        ForeignKey("advertisements.id", ondelete="CASCADE"), index=True, nullable=False
    )
    views: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reactions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    forwards: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )

    advertisement: Mapped["Advertisement"] = relationship(
        "Advertisement", back_populates="snapshots"
    )

    def __repr__(self) -> str:
        return f"<ViewSnapshot(ad_id={self.advertisement_id}, views={self.views}, at={self.recorded_at})>"
