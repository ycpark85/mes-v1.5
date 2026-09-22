from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InspectionResultRevision(Base):
    __tablename__ = "inspection_result_revision"
    __table_args__ = (Index("ix_inspection_result_revision__result", "inspection_result_id"),)

    revision_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inspection_result_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("inspection_result.inspection_result_id", ondelete="RESTRICT"),
        nullable=False,
    )
    before_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    after_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
