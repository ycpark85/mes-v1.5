"""Opt-in real locking checks on the isolated local test database only."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

import app.models  # noqa: F401
from app.db.base import Base
from app.models.drawing import Drawing
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.routing_template import RoutingTemplate
from app.schemas.order_line import (
    OrderLineBulkCommitRequest, OrderLineBulkCommitRowChoice,
    OrderLineBulkImportRowIn, OrderLineBulkValidateRequest,
)
from app.schemas.partner_product_mapping import PartnerProductMappingCreate
from app.services.bulk.order_line_bulk_service import order_line_bulk_service
from app.services.partner_product_mapping_service import create_mapping


TEST_URL = os.environ.get("MES_UNPRINTED_TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_URL, reason="Isolated PostgreSQL test URL is required")
@pytest.mark.parametrize("managed", [False, True])
def test_concurrent_imports_preserve_history_and_each_order_snapshot(managed):
    url = make_url(TEST_URL)
    assert (url.host, url.port, url.database, url.username) == (
        "127.0.0.1", 55440, "mes_unprinted_test", "mes_unprinted_test",
    )
    schema = "test_order_names_" + uuid4().hex
    admin = create_engine(url, connect_args={"connect_timeout": 5})
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(url.update_query_dict({
        "options": f"-csearch_path={schema},public -cstatement_timeout=10000", "connect_timeout": "5",
    }), execution_options={"schema_translate_map": {None: schema}})
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add_all([
                Partner(partner_id=1, partner_type="CUSTOMER", name="Customer", business_no="TEST-A", is_active=True),
                Partner(partner_id=2, partner_type="CUSTOMER", name="Customer B", business_no="TEST-B", is_active=True),
                Drawing(drawing_id=1, drawing_no="TEST-D", is_active=True),
                RoutingTemplate(routing_template_id=1, template_code="TEST-RT", template_name="Test", is_active=True),
            ])
            db.flush()
            db.add(Product(product_id=1, product_code="P-001", product_name="제품",
                           product_spec="MASTER-SPEC", is_unprinted_managed=managed, uom="EA",
                           drawing_id=1, routing_template_id=1, is_active=True))
            db.flush()
            legacy = OrderLine(order_no="OLD", line_no=1, partner_id=1, product_id=1,
                               order_date=date(2026, 1, 1), due_date=date(2026, 1, 31),
                               order_qty=10, uom="EA", status="OPEN")
            db.add_all([legacy, ProductInventory(product_id=1, current_qty=1000),
                        ProductInventoryLot(product_id=1, lot_no="STOCK", current_qty=1000)])
            db.flush()
            if managed:
                for partner_id in (1, 2):
                    create_mapping(db, 1, PartnerProductMappingCreate(
                        partner_id=partner_id, erp_product_code="P-001",
                        customer_product_name="Linked name",
                    ), actor="test")
            db.commit()
            legacy_id, legacy_updated_at = legacy.order_line_id, legacy.updated_at

        barrier = Barrier(2)

        def register(index):
            with Session(engine) as db:
                item = OrderLineBulkImportRowIn(
                    row_number=1, erp_order_no=f"2026/10/20-{index + 1}", product_code="P-001",
                    partner_name="Customer" if index == 0 else "Customer B",
                    erp_product_display_name=f"Customer name {index} [ORDER-SPEC]",
                    order_qty_text="10", due_date_text="2026-10-31",
                )
                preview = order_line_bulk_service.validate_bulk(db, OrderLineBulkValidateRequest(items=[item]))
                reviewed = preview.groups[0].rows[0]
                barrier.wait(timeout=10)
                result = order_line_bulk_service.commit_bulk(db, OrderLineBulkCommitRequest(
                    items=[item], row_choices=[OrderLineBulkCommitRowChoice(
                        row_number=1, expected_product_id=reviewed.product_id,
                        expected_mapping_id=reviewed.mapping_id, apply_product_name_change=True,
                    )],
                ))
                assert result.success_group_count == 1, result
                db.commit()

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(register, range(2)))

        with Session(engine) as db:
            old = db.get(OrderLine, legacy_id)
            assert (old.source_product_name, old.source_product_spec) == ("제품", "MASTER-SPEC")
            assert old.updated_at == legacy_updated_at
            orders = db.scalars(select(OrderLine).where(OrderLine.order_line_id != legacy_id)
                                .order_by(OrderLine.order_no)).all()
            assert [o.source_product_name for o in orders] == ["Customer name 0", "Customer name 1"]
            assert all(o.source_product_spec == "ORDER-SPEC" and o.product_id == 1 for o in orders)
            product = db.get(Product, 1)
            assert product.product_spec == "MASTER-SPEC" and product.drawing_id == 1
            assert product.product_name in {"Customer name 0", "Customer name 1"}
            assert db.execute(text("SELECT current_schema()")).scalar_one() == schema
    finally:
        engine.dispose()
        # Remove only the random schema this test created on the guarded test DB.
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()
