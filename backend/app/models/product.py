# app/models/product.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List
from app.db.base import Base


class Product(Base):
    __tablename__ = "product"
    __table_args__ = (
        UniqueConstraint("product_code", name="uq_product__product_code"),
        UniqueConstraint("drawing_id", name="uq_product__drawing_id"),  # ✅ 1:1 강제
        Index("ix_product__is_active", "is_active"),
        Index(
            "ix_product__product_code_trgm",
            "product_code",
            postgresql_using="gin",
            postgresql_ops={"product_code": "gin_trgm_ops"},
        ),
        Index(
            "ix_product__product_name_trgm",
            "product_name",
            postgresql_using="gin",
            postgresql_ops={"product_name": "gin_trgm_ops"},
        ),
    )

    product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(60), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_unprinted_managed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    uom: Mapped[str] = mapped_column(String(10), nullable=False)  # EA 등

    # ✅ 필수 + 1:1
    drawing_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("drawing.drawing_id", ondelete="RESTRICT"),
        nullable=False,
    )

    panel_width_mm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    panel_length_mm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    product_spec: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cut_qty_per_panel: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    routing_template_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("routing_template.routing_template_id", ondelete="RESTRICT"),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    drawing = relationship("Drawing", back_populates="product")
    routing_template = relationship("RoutingTemplate")  # 네가 이미 모델 갖고 있으면 back_populates로 연결
    order_lines: Mapped[List["OrderLine"]] = relationship("OrderLine", back_populates="product")
