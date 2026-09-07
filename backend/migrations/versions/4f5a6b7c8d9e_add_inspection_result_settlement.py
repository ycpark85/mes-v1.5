"""add inspection result settlement marker

Revision ID: 4f5a6b7c8d9e
Revises: 3e4f5a6b7c8d
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f5a6b7c8d9e"
down_revision: Union[str, Sequence[str], None] = "3e4f5a6b7c8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inspection_result",
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "inspection_result",
        sa.Column("settled_by", sa.String(length=100), nullable=True),
    )

    # Completed historical results were already settled by the legacy flow.
    # A zero-sellable partial result also has nothing left to settle. Positive
    # historical partial results intentionally remain NULL and are carried into
    # the next inspection round for an explicit operator allocation.
    op.execute(
        """
        UPDATE inspection_result AS result
        SET settled_at = COALESCE(result.updated_at, result.created_at, CURRENT_TIMESTAMP),
            settled_by = COALESCE(NULLIF(result.created_by, ''), 'MIGRATION')
        FROM inspection_schedule AS schedule
        WHERE schedule.inspection_schedule_id = result.inspection_schedule_id
          AND (
              schedule.status = 'DONE'
              OR (result.good_qty + result.defect_ship_qty) = 0
          )
        """
    )

    op.create_check_constraint(
        "ck_inspection_result__settlement_pair",
        "inspection_result",
        "(settled_at IS NULL AND settled_by IS NULL) OR "
        "(settled_at IS NOT NULL AND settled_by IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_inspection_result__settlement_pair",
        "inspection_result",
        type_="check",
    )
    op.drop_column("inspection_result", "settled_by")
    op.drop_column("inspection_result", "settled_at")
