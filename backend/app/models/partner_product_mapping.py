from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UnprintedProductCodeCounter(Base):
    __tablename__ = "unprinted_product_code_counter"
    __table_args__ = (
        CheckConstraint("counter_id = 1", name="ck_unprinted_counter__singleton"),
        CheckConstraint("next_value > 0", name="ck_unprinted_counter__positive"),
    )
    counter_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False)


class PartnerProductMapping(Base):
    __tablename__ = "partner_product_mapping"
    __table_args__ = (
        Index("uq_partner_product_mapping__active_key", "partner_id", "erp_product_code", unique=True,
              postgresql_where=text("is_active = true"), sqlite_where=text("is_active = 1")),
        Index("ix_partner_product_mapping__product_id", "product_id"),
        Index("ix_partner_product_mapping__erp_code", "erp_product_code"),
        CheckConstraint("length(trim(erp_product_code)) > 0 AND erp_product_code = upper(trim(erp_product_code))",
                        name="ck_partner_product_mapping__normalized_code"),
        CheckConstraint("length(trim(customer_product_name)) > 0", name="ck_partner_product_mapping__name"),
    )
    mapping_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    partner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("partner.partner_id", ondelete="RESTRICT"), nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("product.product_id", ondelete="RESTRICT"), nullable=False)
    erp_product_code: Mapped[str] = mapped_column(String(60), nullable=False)
    customer_product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_product_spec: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    deactivated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
