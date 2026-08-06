"""add order line change log

Revision ID: 3e4f5a6b7c8d
Revises: 29d3e4f5a6b7
Create Date: 2026-08-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "3e4f5a6b7c8d"
down_revision: Union[str, Sequence[str], None] = "29d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_line_change_log",
        sa.Column("order_line_change_log_id", sa.BigInteger(), nullable=False),
        sa.Column("order_line_id", sa.BigInteger(), nullable=False),
        sa.Column("lot_id", sa.BigInteger(), nullable=True),
        sa.Column("change_type", sa.String(length=30), nullable=False),
        sa.Column(
            "before_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "after_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "change_type IN ('QUANTITY_CHANGE','DUE_DATE_CHANGE','MEMO_CHANGE')",
            name="ck_order_line_change_log__change_type",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["lot.lot_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_line_id"],
            ["order_line.order_line_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("order_line_change_log_id"),
    )
    op.create_index(
        "ix_order_line_change_log__order_line_created_at",
        "order_line_change_log",
        ["order_line_id", "created_at", "order_line_change_log_id"],
    )
    op.create_index(
        "ix_order_line_change_log__lot_created_at",
        "order_line_change_log",
        ["lot_id", "created_at"],
    )
    op.create_check_constraint(
        "ck_outsource_work_group_change_log__action_type",
        "outsource_work_group_change_log",
        "action_type IN ('UPDATE','CANCEL')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_outsource_work_group_change_log__action_type",
        "outsource_work_group_change_log",
        type_="check",
    )
    op.drop_index(
        "ix_order_line_change_log__lot_created_at",
        table_name="order_line_change_log",
    )
    op.drop_index(
        "ix_order_line_change_log__order_line_created_at",
        table_name="order_line_change_log",
    )
    op.drop_table("order_line_change_log")
