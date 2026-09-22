"""Separate current short-close decisions from editable memo text.

Revision ID: 6b7c8d9e0f1a
Revises: 5a6b7c8d9e0f
See docs/priority-refactoring-implementation-2026-09-14.md before applying.
"""
from alembic import op
import sqlalchemy as sa

revision = "6b7c8d9e0f1a"
down_revision = "5a6b7c8d9e0f"
branch_labels = None
depends_on = None


def backfill_short_close_state(connection) -> None:
    # Only a structured, latest confirmed plan establishes a confirmed decision.
    connection.execute(sa.text("""
        UPDATE order_line SET short_close_state = 'CONFIRMED'
        WHERE status = 'DONE' AND decision_made = true AND short_close_state = 'NONE'
          AND (SELECT h.is_short_close FROM order_line_plan_history h
               WHERE h.order_line_id = order_line.order_line_id
               ORDER BY h.created_at DESC, h.plan_history_id DESC LIMIT 1) = true
    """))
    # A historical memo is evidence to review, not authorization to invent an audit record.
    connection.execute(sa.text("""
        UPDATE order_line SET short_close_state = 'REVIEW_REQUIRED'
        WHERE status = 'DONE' AND short_close_state = 'NONE'
          AND REPLACE(memo, '[SHORT_CLOSE]', '') <> memo
    """))


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("order_line", sa.Column("short_close_state", sa.String(20),
        nullable=False, server_default="NONE"))
    op.create_check_constraint("ck_order_line__short_close_state", "order_line",
        "short_close_state IN ('NONE','CONFIRMED','REVIEW_REQUIRED')")
    op.drop_constraint("ck_order_line_change_log__change_type", "order_line_change_log", type_="check")
    op.create_check_constraint("ck_order_line_change_log__change_type", "order_line_change_log",
        "change_type IN ('QUANTITY_CHANGE','DUE_DATE_CHANGE','MEMO_CHANGE','SHORT_CLOSE')")
    backfill_short_close_state(op.get_bind())


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if op.get_bind().execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM order_line_change_log WHERE change_type = 'SHORT_CLOSE')"
    )).scalar():
        raise RuntimeError("새 부족종료 이력이 존재합니다. 이력을 보존하는 호환 롤백 계획이 필요합니다.")
    op.drop_constraint("ck_order_line_change_log__change_type", "order_line_change_log", type_="check")
    op.create_check_constraint("ck_order_line_change_log__change_type", "order_line_change_log",
        "change_type IN ('QUANTITY_CHANGE','DUE_DATE_CHANGE','MEMO_CHANGE')")
    op.drop_constraint("ck_order_line__short_close_state", "order_line", type_="check")
    op.drop_column("order_line", "short_close_state")
