from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Numeric
from app.db.base import Base


class OutsourceWorkGroup(Base):
    __tablename__ = "outsource_work_group"
    __table_args__ = (
        CheckConstraint(
            "process_type IN ('CUT','PRINT','DIECUT')",
            name="ck_outsource_work_group__process_type",
        ),
        CheckConstraint(
            "sheet_qty > 0",
            name="ck_outsource_work_group__sheet_qty_gt_0",
        ),
        CheckConstraint(
            "sheet_cut_count > 0",
            name="ck_outsource_work_group__sheet_cut_count_gt_0",
        ),
        CheckConstraint(
            "status IS NULL OR status IN ('VENDOR_RECEIVED','WORK_DONE','SHIPPED','CANCELED')",
            name="ck_outsource_work_group__status",
        ),
        CheckConstraint(
            "work_done_sheet_qty IS NULL OR work_done_sheet_qty >= 0",
            name="ck_outsource_work_group__work_done_sheet_qty_ge_0",
        ),
        CheckConstraint(
            "outsource_processing_fee IS NULL OR outsource_processing_fee >= 0",
            name="ck_outsource_work_group__outsource_processing_fee_ge_0",
        ),
        Index(
            "ix_outsource_work_group__instruction_id",
            "outsource_work_instruction_id",
        ),
        Index(
            "ix_outsource_work_group__process_type",
            "process_type",
        ),
        Index(
            "ix_outsource_work_group__representative_lot_id",
            "representative_lot_id",
        ),
    )

    outsource_work_group_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    outsource_work_instruction_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "outsource_work_instruction.outsource_work_instruction_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    group_seq: Mapped[str] = mapped_column(String(20), nullable=False)
    process_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_bundle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sheet_qty: Mapped[int] = mapped_column(BigInteger, nullable=False)
    length_m: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    sheet_cut_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    fabric_lot_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    representative_lot_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("lot.lot_id", ondelete="RESTRICT"),
        nullable=True,
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vendor_received_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    work_done_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    shipped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    canceled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    work_done_sheet_qty: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )

    outsource_processing_fee: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    work_done_remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    canceled_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    instruction = relationship("OutsourceWorkInstruction")
    representative_lot = relationship("Lot", foreign_keys=[representative_lot_id])

    items: Mapped[List["OutsourceWorkGroupItem"]] = relationship(
        "OutsourceWorkGroupItem",
        back_populates="work_group",
        cascade="all, delete-orphan",
    )

    purchase_order_groups: Mapped[List["OutsourcePurchaseOrderGroup"]] = relationship(
        "OutsourcePurchaseOrderGroup",
        back_populates="work_group",
        cascade="all, delete-orphan",
    )
