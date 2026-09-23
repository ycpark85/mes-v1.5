"""Track stock-deferred LOT creation and explicit manual completion.

Revision ID: 7c8d9e0f1a2b
Revises: 6b7c8d9e0f1a
See docs/order-work-queues-2026-09-22.md before applying.
"""
from alembic import op
import sqlalchemy as sa

revision = "7c8d9e0f1a2b"
down_revision = "6b7c8d9e0f1a"
branch_labels = None
depends_on = None


def backfill_deferred_orders(connection):
    # Saved inventory-first/hybrid intent, not today's changing stock balance.
    connection.execute(sa.text("""
        UPDATE order_line SET lot_creation_deferred = true
        WHERE is_active = true AND status = 'OPEN'
          AND fulfillment_mode IN ('INVENTORY_FIRST', 'HYBRID')
          AND COALESCE(production_policy, '') <> 'INVENTORY_ONLY_CLOSE'
          AND NOT EXISTS (SELECT 1 FROM lot WHERE lot.order_line_id = order_line.order_line_id)
    """))


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("order_line", sa.Column("lot_creation_deferred", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("order_line", sa.Column("manual_closed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_check_constraint("ck_order_line__manual_closed", "order_line",
        "NOT manual_closed OR (status = 'DONE' AND short_close_state = 'CONFIRMED')")
    backfill_deferred_orders(op.get_bind())


def downgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    if op.get_bind().execute(sa.text("""
        SELECT EXISTS (SELECT 1 FROM order_line WHERE manual_closed = true)
            OR EXISTS (SELECT 1 FROM order_line_change_log
                WHERE after_data->>'action' IN ('MANUAL_CLOSE', 'MANUAL_REOPEN', 'REWORK_REOPEN'))
    """)).scalar():
        raise RuntimeError("수동완료 또는 재개 이력이 있어 호환 롤백 계획이 필요합니다.")
    op.drop_constraint("ck_order_line__manual_closed", "order_line", type_="check")
    op.drop_column("order_line", "manual_closed")
    op.drop_column("order_line", "lot_creation_deferred")
