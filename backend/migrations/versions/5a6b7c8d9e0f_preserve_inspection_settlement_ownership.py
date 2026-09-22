"""Preserve inspection settlement sources and final shortage reasons.

Revision ID: 5a6b7c8d9e0f
Revises: 4f5a6b7c8d9e

Additive migration. Backfill only reconciled, unambiguous ownership; do not alter
quantities, shipments, inventory balances, or unresolved historical records.
"""
from alembic import op
import sqlalchemy as sa

revision = "5a6b7c8d9e0f"
down_revision = "4f5a6b7c8d9e"
branch_labels = None
depends_on = None


def backfill_settlement_owners(connection) -> None:
    connection.execute(sa.text("""
        WITH input_qty AS (
            SELECT inspection_result_id, SUM(qty) AS qty
            FROM product_inventory_movement WHERE movement_type = 'INSPECTION_IN'
            GROUP BY inspection_result_id
        ), candidates AS (
            SELECT source.inspection_result_id AS source_id,
                   owner.inspection_result_id AS owner_id,
                   source.good_qty + source.defect_ship_qty AS source_qty,
                   own_input.qty + owner.discard_qty - owner.good_qty - owner.defect_ship_qty AS carry_qty
            FROM inspection_result owner
            JOIN inspection_schedule own_schedule ON own_schedule.inspection_schedule_id = owner.inspection_schedule_id
            JOIN input_qty own_input ON own_input.inspection_result_id = owner.inspection_result_id
            JOIN inspection_schedule prior_schedule ON prior_schedule.lot_id = own_schedule.lot_id
                AND prior_schedule.status = 'PARTIAL_DONE'
                AND (prior_schedule.inspection_date < own_schedule.inspection_date
                     OR (prior_schedule.inspection_date = own_schedule.inspection_date
                         AND prior_schedule.inspection_schedule_id < own_schedule.inspection_schedule_id))
            JOIN inspection_result source ON source.inspection_schedule_id = prior_schedule.inspection_schedule_id
            WHERE owner.settlement_owner_id IS NULL AND source.settlement_owner_id IS NULL
              AND own_schedule.status IN ('DONE', 'PARTIAL_DONE')
              AND owner.settled_at IS NOT NULL AND source.settled_at = owner.settled_at
              AND source.settled_by = owner.settled_by
              AND source.good_qty + source.defect_ship_qty > 0 AND source.discard_qty = 0
              AND own_input.qty + owner.discard_qty > owner.good_qty + owner.defect_ship_qty
              AND NOT EXISTS (SELECT 1 FROM product_inventory_movement m
                              WHERE m.inspection_result_id = source.inspection_result_id)
        ), unique_sources AS (
            SELECT source_id FROM candidates GROUP BY source_id HAVING COUNT(*) = 1
        ), valid_owners AS (
            SELECT owner_id FROM candidates
            GROUP BY owner_id HAVING SUM(source_qty) = MAX(carry_qty)
              AND COUNT(*) = SUM(CASE WHEN source_id IN (SELECT source_id FROM unique_sources) THEN 1 ELSE 0 END)
        ), mappings AS (
            SELECT source_id, owner_id FROM candidates WHERE owner_id IN (SELECT owner_id FROM valid_owners)
            UNION ALL SELECT owner_id, owner_id FROM valid_owners
        )
        UPDATE inspection_result SET settlement_owner_id = mappings.owner_id,
            settled_sellable_qty = inspection_result.good_qty + inspection_result.defect_ship_qty
        FROM mappings WHERE inspection_result.inspection_result_id = mappings.source_id
          AND inspection_result.settlement_owner_id IS NULL
    """))
    connection.execute(sa.text("""
        UPDATE inspection_result AS result
        SET settlement_owner_id = result.inspection_result_id,
            settled_sellable_qty = result.good_qty + result.defect_ship_qty
        WHERE result.settlement_owner_id IS NULL AND result.settled_at IS NOT NULL
          AND result.good_qty + result.defect_ship_qty - result.discard_qty >= 0
          AND COALESCE((SELECT SUM(m.qty) FROM product_inventory_movement m
              WHERE m.inspection_result_id = result.inspection_result_id
                AND m.movement_type = 'INSPECTION_IN'), 0)
              = result.good_qty + result.defect_ship_qty - result.discard_qty
    """))


def upgrade() -> None:
    op.add_column("inspection_result", sa.Column("shortage_reason", sa.Text(), nullable=True))
    op.add_column("inspection_result", sa.Column("settlement_owner_id", sa.BigInteger(), nullable=True))
    op.add_column("inspection_result", sa.Column("settled_sellable_qty", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_inspection_result__settlement_owner", "inspection_result", "inspection_result",
                          ["settlement_owner_id"], ["inspection_result_id"], ondelete="RESTRICT")
    op.create_index("ix_inspection_result__settlement_owner", "inspection_result", ["settlement_owner_id"])
    op.create_check_constraint("ck_inspection_result__settlement_owner_pair", "inspection_result",
        "(settlement_owner_id IS NULL AND settled_sellable_qty IS NULL) OR "
        "(settlement_owner_id IS NOT NULL AND settled_sellable_qty IS NOT NULL "
        "AND settled_sellable_qty >= 0 AND settled_at IS NOT NULL)")
    op.create_table("inspection_result_revision",
        sa.Column("revision_id", sa.BigInteger(), primary_key=True),
        sa.Column("inspection_result_id", sa.BigInteger(), sa.ForeignKey(
            "inspection_result.inspection_result_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("before_values", sa.JSON(), nullable=False),
        sa.Column("after_values", sa.JSON(), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inspection_result_revision__result", "inspection_result_revision", ["inspection_result_id"])
    backfill_settlement_owners(op.get_bind())


def downgrade() -> None:
    # Never silently remove production correction history or newly entered reasons.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM inspection_result_revision) OR "
        "EXISTS (SELECT 1 FROM inspection_result WHERE shortage_reason IS NOT NULL)")).scalar():
        raise RuntimeError("새 검수 이력/미달 사유가 존재합니다. 호환 롤백 계획 없이 삭제할 수 없습니다.")
    op.drop_table("inspection_result_revision")
    op.drop_constraint("ck_inspection_result__settlement_owner_pair", "inspection_result", type_="check")
    op.drop_index("ix_inspection_result__settlement_owner", table_name="inspection_result")
    op.drop_constraint("fk_inspection_result__settlement_owner", "inspection_result", type_="foreignkey")
    op.drop_column("inspection_result", "settled_sellable_qty")
    op.drop_column("inspection_result", "settlement_owner_id")
    op.drop_column("inspection_result", "shortage_reason")
