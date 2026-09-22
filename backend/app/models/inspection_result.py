from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InspectionResult(Base):
    """검수 실적 (회차 SSOT)"""

    __tablename__ = "inspection_result"
    __table_args__ = (
        UniqueConstraint("inspection_schedule_id", name="uq_inspection_result__schedule"),
        CheckConstraint("good_qty >= 0", name="ck_inspection_result__good_qty"),
        CheckConstraint("defect_qty >= 0", name="ck_inspection_result__defect_qty"),
        CheckConstraint("defect_ship_qty >= 0", name="ck_inspection_result__defect_ship_qty"),
        CheckConstraint("discard_qty >= 0", name="ck_inspection_result__discard_qty"),
        CheckConstraint("uninspected_qty >= 0", name="ck_inspection_result__uninspected_qty"),
        CheckConstraint(
            "inspected_qty = good_qty + defect_ship_qty + defect_qty",
            name="ck_inspection_result__inspected_qty_calc_v2",
        ),
        CheckConstraint(
            "(settled_at IS NULL AND settled_by IS NULL) OR "
            "(settled_at IS NOT NULL AND settled_by IS NOT NULL)",
            name="ck_inspection_result__settlement_pair",
        ),
        Index("ix_inspection_result__schedule", "inspection_schedule_id"),
        Index("ix_inspection_result__settlement_owner", "settlement_owner_id"),
        CheckConstraint(
            "(settlement_owner_id IS NULL AND settled_sellable_qty IS NULL) OR "
            "(settlement_owner_id IS NOT NULL AND settled_sellable_qty IS NOT NULL "
            "AND settled_sellable_qty >= 0 AND settled_at IS NOT NULL)",
            name="ck_inspection_result__settlement_owner_pair",
        ),
    )

    inspection_result_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    inspection_schedule_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("inspection_schedule.inspection_schedule_id", ondelete="CASCADE"),
        nullable=False,
    )

    good_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    defect_ship_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    defect_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    inspected_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    uninspected_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discard_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    next_inspection_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    partial_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    shortage_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    settled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    settled_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    settlement_owner_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("inspection_result.inspection_result_id", ondelete="RESTRICT",
                               name="fk_inspection_result__settlement_owner"),
        nullable=True,
    )
    settled_sellable_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    inspection_schedule = relationship("InspectionSchedule")
    defects: Mapped[List["InspectionDefect"]] = relationship(
        "InspectionDefect",
        back_populates="inspection_result",
        cascade="all, delete-orphan",
    )

    @property
    def received_qty(self) -> int:
        return int(self.inspected_qty or 0) + int(self.uninspected_qty or 0)
