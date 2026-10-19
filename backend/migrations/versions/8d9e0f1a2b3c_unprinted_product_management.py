"""Add opt-in unprinted products and partner ERP mappings without rewriting business data.

Revision ID: 8d9e0f1a2b3c
Revises: 7c8d9e0f1a2b
See docs/unprinted-product-management-2026-10-19.md.
"""
from alembic import op
import sqlalchemy as sa

revision = "8d9e0f1a2b3c"
down_revision = "7c8d9e0f1a2b"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("product", sa.Column("is_unprinted_managed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("unprinted_product_code_counter",
        sa.Column("counter_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("next_value", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("counter_id = 1", name="ck_unprinted_counter__singleton"),
        sa.CheckConstraint("next_value > 0", name="ck_unprinted_counter__positive"))
    op.execute("INSERT INTO unprinted_product_code_counter (counter_id, next_value) VALUES (1, 1)")
    op.create_table("partner_product_mapping",
        sa.Column("mapping_id", sa.BigInteger(), primary_key=True),
        sa.Column("partner_id", sa.BigInteger(), sa.ForeignKey("partner.partner_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("product.product_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("erp_product_code", sa.String(60), nullable=False),
        sa.Column("customer_product_name", sa.String(200), nullable=False),
        sa.Column("customer_product_spec", sa.String(100)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("deactivated_by", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deactivated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("length(trim(erp_product_code)) > 0 AND erp_product_code = upper(trim(erp_product_code))", name="ck_partner_product_mapping__normalized_code"),
        sa.CheckConstraint("length(trim(customer_product_name)) > 0", name="ck_partner_product_mapping__name"))
    op.create_index("uq_partner_product_mapping__active_key", "partner_product_mapping", ["partner_id", "erp_product_code"], unique=True, postgresql_where=sa.text("is_active = true"))
    op.create_index("ix_partner_product_mapping__product_id", "partner_product_mapping", ["product_id"])
    op.create_index("ix_partner_product_mapping__erp_code", "partner_product_mapping", ["erp_product_code"])
    for name, length in (("source_erp_product_code",60),("source_product_name",200),("source_product_spec",100)):
        op.add_column("order_line", sa.Column(name, sa.String(length), nullable=True))
    op.create_check_constraint("ck_order_line__erp_source", "order_line",
        "(source_erp_product_code IS NULL AND source_product_name IS NULL AND source_product_spec IS NULL) OR "
        "(source_erp_product_code IS NOT NULL AND source_product_name IS NOT NULL AND "
        "length(trim(source_erp_product_code)) > 0 AND length(trim(source_product_name)) > 0)")


def downgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    if op.get_bind().execute(sa.text("""
        SELECT EXISTS (SELECT 1 FROM product WHERE is_unprinted_managed)
          OR EXISTS (SELECT 1 FROM partner_product_mapping)
          OR EXISTS (SELECT 1 FROM order_line WHERE source_erp_product_code IS NOT NULL)
    """)).scalar():
        raise RuntimeError("무지 품목/연결/수주 원본 정보가 있어 데이터 보존 복구 계획이 필요합니다.")
    op.drop_constraint("ck_order_line__erp_source", "order_line", type_="check")
    for name in ("source_product_spec", "source_product_name", "source_erp_product_code"):
        op.drop_column("order_line", name)
    op.drop_table("partner_product_mapping")
    op.drop_table("unprinted_product_code_counter")
    op.drop_column("product", "is_unprinted_managed")
