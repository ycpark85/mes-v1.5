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


class OrderLineChangeLog(Base):
    __tablename__ = "order_line_change_log"
    __table_args__ = (
        CheckConstraint(
            "change_type IN ('QUANTITY_CHANGE','DUE_DATE_CHANGE','MEMO_CHANGE','SHORT_CLOSE')",
            name="ck_order_line_change_log__change_type",
        ),
        Index(
            "ix_order_line_change_log__order_line_created_at",
            "order_line_id",
            "created_at",
            "order_line_change_log_id",
        ),
        Index(
            "ix_order_line_change_log__lot_created_at",
            "lot_id",
            "created_at",
        ),
    )

    order_line_change_log_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    order_line_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("order_line.order_line_id", ondelete="CASCADE"),
        nullable=False,
    )
    lot_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("lot.lot_id", ondelete="SET NULL"),
        nullable=True,
    )
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    before_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    after_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    order_line = relationship("OrderLine")
    lot = relationship("Lot")
