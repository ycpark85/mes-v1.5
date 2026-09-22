# app/models/order_line.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, List

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrderLine(Base):
    """
    수주 라인 (주문의 SSOT)

    상태 정의(확정):
    - OPEN: primary LOT 생성 가능
    - CLOSED: primary LOT 생성 완료
    - DONE: 생산완료(LOT 집계 기반)
    - CANCELED: 취소
    """

    __tablename__ = "order_line"
    __table_args__ = (
        UniqueConstraint("order_no", "line_no", name="uq_order_line__order_no__line_no"),
        CheckConstraint("line_no > 0", name="ck_order_line__line_no_gt_0"),
        CheckConstraint("order_qty > 0", name="ck_order_line__order_qty_gt_0"),
        CheckConstraint(
            "status IN ('OPEN','CLOSED','DONE','CANCELED')",
            name="ck_order_line__status_enum",
        ),
        CheckConstraint(
            "short_close_state IN ('NONE','CONFIRMED','REVIEW_REQUIRED')",
            name="ck_order_line__short_close_state",
        ),
        Index("ix_order_line__partner_id", "partner_id"),
        Index("ix_order_line__product_id", "product_id"),
        Index("ix_order_line__order_date", "order_date"),
        Index("ix_order_line__due_date", "due_date"),
        Index("ix_order_line__order_no", "order_no"),
        Index("ix_order_line__status", "status"),
        Index("ix_order_line__is_active", "is_active"),
        Index(
            "ix_order_line__active_status_due",
            "is_active",
            "status",
            "due_date",
            "order_no",
            "line_no",
        ),
    )

    order_line_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # 업무 식별자
    order_no: Mapped[str] = mapped_column(String(40), nullable=False)  # 예: SO-2026-000123
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)      # 1,2,3...

    # 마스터 참조
    partner_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("partner.partner_id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("product.product_id", ondelete="RESTRICT"),
        nullable=False,
    )

    # 수주 속성
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    order_qty: Mapped[int] = mapped_column(Integer, nullable=False)

    # ✅ 단위 스냅샷 (기본값은 서비스에서 product.uom으로 채움)
    uom: Mapped[str] = mapped_column(String(10), nullable=False)

    # ✅ 상태/활성/우선순위 (MVP)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="OPEN")
    short_close_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NONE", server_default="NONE"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 운영 보조
    customer_po: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 처리계획(1단계)
    fulfillment_mode: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    production_policy: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    extra_production_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    decision_made: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decision_made_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_made_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


    # 감사
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # 관계
    partner = relationship("Partner", back_populates="order_lines")
    product = relationship("Product", back_populates="order_lines")
    lots: Mapped[List["Lot"]] = relationship("Lot", back_populates="order_line")
