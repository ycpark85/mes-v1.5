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
from app.models.partner_product_mapping import PartnerProductMapping
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.routing_template import RoutingTemplate
from app.services.product_query import list_products_for_grid


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, compiler, **kw):
    return "INTEGER"


TEST_TABLE_NAMES = [
    "partner_product_mapping",
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

    def test_management_filter_uses_flag_and_combines_with_activity(self) -> None:
        # Explicit conversion retains the legacy code; the prefix is not the filter.
        self.db.get(Product, 1).is_unprinted_managed = True
        for product_id, code, managed, active in [
            (3, "MES-U000001", True, True),
            (4, "MES-U000002", True, False),
            (5, "PRD-005", False, False),
        ]:
            self.db.add(Drawing(drawing_id=product_id, drawing_no=f"DWG-{product_id}", is_active=True))
            self.db.add(Product(product_id=product_id, product_code=code, product_name="공용 무지",
                uom="EA", drawing_id=product_id, routing_template_id=1,
                is_unprinted_managed=managed, is_active=active))
        self.db.commit()

        for managed, active, expected_ids in [
            (None, None, [5, 4, 3, 2, 1]), (None, True, [3, 2, 1]), (None, False, [5, 4]),
            (False, None, [5, 2]), (False, True, [2]), (False, False, [5]),
            (True, None, [4, 3, 1]), (True, True, [3, 1]), (True, False, [4]),
        ]:
            with self.subTest(managed=managed, active=active):
                items, total = list_products_for_grid(self.db, page=1, size=100, q=None,
                    partner_q=None, is_active=active, is_unprinted_managed=managed)
                self.assertEqual(expected_ids, [item.product_id for item in items])
                self.assertEqual(len(expected_ids), total)

    def test_management_filter_preserves_mapped_search_and_paging(self) -> None:
        for product_id in (1, 2):
            self.db.get(Product, product_id).is_unprinted_managed = True
            self.db.add(PartnerProductMapping(partner_id=1, product_id=product_id,
                erp_product_code=f"SHARED-{product_id}", customer_product_name="거래처용 공용 무지",
                is_active=True, created_by="tester"))
        self.db.commit()

        for page, expected_ids in [(1, [2]), (2, [1]), (3, [])]:
            with self.subTest(page=page):
                items, total = list_products_for_grid(self.db, page=page, size=1, q="공용 무지",
                    partner_q="고객사", is_active=True, is_unprinted_managed=True)
                self.assertEqual(expected_ids, [item.product_id for item in items])
                self.assertEqual(2, total)

        items, total = list_products_for_grid(self.db, page=1, size=100, q="SHARED-1",
            partner_q="고객사", is_active=True, is_unprinted_managed=True)
        self.assertEqual([1], [item.product_id for item in items])
        self.assertEqual(1, total)
        items, total = list_products_for_grid(self.db, page=1, size=100, q="공용 무지",
            partner_q="고객사", is_active=True, is_unprinted_managed=False)
        self.assertEqual([], items)
        self.assertEqual(0, total)

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
