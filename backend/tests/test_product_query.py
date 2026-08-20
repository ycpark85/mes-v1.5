from __future__ import annotations

import unittest
from datetime import date

from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.drawing import Drawing
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.routing_template import RoutingTemplate
from app.services.product_query import list_products_for_grid


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, compiler, **kw):
    return "INTEGER"


TEST_TABLE_NAMES = [
    "drawing",
    "routing_template",
    "product",
    "partner",
    "order_line",
    "product_inventory",
]


class ProductQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[Base.metadata.tables[name] for name in TEST_TABLE_NAMES],
        )
        SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = SessionLocal()

        self.db.add_all(
            [
                Drawing(drawing_id=1, drawing_no="DWG-001", is_active=True),
                Drawing(drawing_id=2, drawing_no="DWG-002", is_active=True),
                RoutingTemplate(
                    routing_template_id=1,
                    template_code="RT-01",
                    template_name="표준 라우팅",
                    is_active=True,
                ),
                Partner(
                    partner_id=1,
                    partner_type="CUSTOMER",
                    name="고객사 A",
                    business_no="100-00-00001",
                    is_active=True,
                ),
                Product(
                    product_id=1,
                    product_code="PRD-001",
                    product_name="품목 1",
                    uom="EA",
                    drawing_id=1,
                    routing_template_id=1,
                    is_active=True,
                ),
                Product(
                    product_id=2,
                    product_code="PRD-002",
                    product_name="품목 2",
                    uom="EA",
                    drawing_id=2,
                    routing_template_id=1,
                    is_active=True,
                ),
                ProductInventory(product_id=1, current_qty=17),
                OrderLine(
                    order_line_id=1,
                    order_no="SO-001",
                    line_no=1,
                    partner_id=1,
                    product_id=1,
                    order_date=date(2026, 8, 1),
                    due_date=date(2026, 8, 31),
                    order_qty=10,
                    uom="EA",
                    status="OPEN",
                    is_active=True,
                    priority=0,
                ),
            ]
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_list_projects_related_values_and_zero_stock_in_two_queries(self) -> None:
        query_count = 0

        def count_query(*_args, **_kwargs) -> None:
            nonlocal query_count
            query_count += 1

        event.listen(self.engine, "before_cursor_execute", count_query)
        try:
            items, total = list_products_for_grid(
                self.db,
                page=1,
                size=100,
                q=None,
                partner_q=None,
                is_active=True,
            )
        finally:
            event.remove(self.engine, "before_cursor_execute", count_query)

        self.assertEqual(2, total)
        self.assertEqual([2, 1], [item.product_id for item in items])
        self.assertEqual([0, 17], [item.current_stock_qty for item in items])
        self.assertEqual(["DWG-002", "DWG-001"], [item.drawing_no for item in items])
        self.assertTrue(all(item.routing_template_name == "표준 라우팅" for item in items))
        self.assertEqual(2, query_count)

    def test_partner_filter_uses_related_active_order_lines_without_duplicates(self) -> None:
        self.db.add(
            OrderLine(
                order_line_id=2,
                order_no="SO-002",
                line_no=1,
                partner_id=1,
                product_id=1,
                order_date=date(2026, 8, 2),
                due_date=date(2026, 8, 31),
                order_qty=20,
                uom="EA",
                status="OPEN",
                is_active=True,
                priority=0,
            )
        )
        self.db.commit()

        items, total = list_products_for_grid(
            self.db,
            page=1,
            size=100,
            q=None,
            partner_q="고객사",
            is_active=True,
        )

        self.assertEqual(1, total)
        self.assertEqual([1], [item.product_id for item in items])


if __name__ == "__main__":
    unittest.main()
