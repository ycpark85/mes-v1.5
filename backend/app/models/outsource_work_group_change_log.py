from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OutsourceWorkGroupChangeLog(Base):
    __tablename__ = "outsource_work_group_change_log"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('UPDATE','CANCEL')",
            name="ck_outsource_work_group_change_log__action_type",
        ),
        Index(
            "ix_owg_change_log__work_group_id",
            "outsource_work_group_id",
        ),
        Index(
            "ix_owg_change_log__created_at",
            "created_at",
        ),
    )

    outsource_work_group_change_log_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    outsource_work_group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("outsource_work_group.outsource_work_group_id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    before_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    after_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    work_group = relationship("OutsourceWorkGroup")
