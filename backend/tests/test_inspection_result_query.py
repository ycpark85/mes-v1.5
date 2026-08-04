from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.drawing import Drawing
from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.routing_template import RoutingTemplate
from app.models.shipment_line import ShipmentLine
from app.services.inspection_result_query import (
    get_inspection_result_detail,
    list_inspection_results_for_grid,
)


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, compiler, **kw):
    return "INTEGER"


TEST_TABLE_NAMES = [
    "drawing",
    "routing_template",
    "partner",
    "product",
    "order_line",
    "lot",
    "inspection_schedule",
    "inspection_result",
    "defect_type",
    "inspection_defect",
    "inspection_defect_attachment",
    "product_inventory",
    "product_inventory_lot",
    "product_inventory_movement",
    "shipment_line",
]


class InspectionResultQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        tables = [Base.metadata.tables[name] for name in TEST_TABLE_NAMES]
        Base.metadata.create_all(self.engine, tables=tables)

        SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = SessionLocal()
        self._seed_inspection_results()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_list_inspection_results_returns_partial_and_done_rows_with_rounds(self) -> None:
        result = list_inspection_results_for_grid(self.db, q="prd-a")

        self.assertEqual(2, len(result.items))
        self.assertEqual(2, result.total_count)
        item = result.items[0]
        self.assertEqual(2, item.inspection_result_id)
        self.assertEqual("LOT-A", item.lot_no)
        self.assertEqual("DONE", item.schedule_status)
        self.assertEqual(2, item.inspection_round)
        self.assertEqual(2, item.inspection_round_count)
        self.assertFalse(item.is_partial)
        self.assertEqual(55, item.received_qty)
        self.assertEqual(20, item.result_ship_qty)
        self.assertEqual(40, item.stock_in_qty)
        self.assertEqual(4, item.defect_qty)

        partial_item = result.items[1]
        self.assertEqual(1, partial_item.inspection_result_id)
        self.assertEqual("PARTIAL_DONE", partial_item.schedule_status)
        self.assertEqual(1, partial_item.inspection_round)
        self.assertTrue(partial_item.is_partial)

    def test_list_inspection_results_filters_by_partner_product_lot_and_date(self) -> None:
        result = list_inspection_results_for_grid(
            self.db,
            date_from=date(2026, 7, 2),
            date_to=date(2026, 7, 2),
            partner_q="Customer",
            product_q="Product",
            lot_q="LOT-A",
        )

        self.assertEqual([2], [item.inspection_result_id for item in result.items])
        self.assertEqual(1, result.total_count)
        self.assertEqual(40, result.total_good_qty)
        self.assertEqual(55, result.total_received_qty)
        self.assertEqual(40, result.total_stock_in_qty)

    def test_get_inspection_result_detail_returns_accumulated_and_inventory_summary(self) -> None:
        detail = get_inspection_result_detail(self.db, 2)

        self.assertIsNotNone(detail.result)
        self.assertEqual(2, detail.result.inspection_result_id)
        self.assertEqual("done", detail.result.memo)
        self.assertEqual("DONE", detail.schedule_status)
        self.assertEqual(2, detail.inspection_round)
        self.assertEqual(2, detail.inspection_round_count)
        self.assertEqual([1, 2], [row.inspection_round for row in detail.rounds])
        self.assertEqual(30, detail.accumulated.good_qty)
        self.assertEqual(5, detail.accumulated.defect_ship_qty)
        self.assertEqual(3, detail.accumulated.defect_qty)
        self.assertEqual(38, detail.accumulated.inspected_qty)
        self.assertEqual(2, detail.accumulated.uninspected_qty)
        self.assertEqual(40, detail.accumulated.received_qty)
        self.assertEqual(1, detail.accumulated.discard_qty)

        self.assertIsNotNone(detail.inventory)
        self.assertEqual(1, detail.inventory.product_id)
        self.assertEqual(1, detail.inventory.order_line_id)
        self.assertEqual(24, detail.inventory.current_stock_qty)
        self.assertEqual(100, detail.inventory.order_qty)
        self.assertEqual(102, detail.inventory.ship_target_qty)
        self.assertEqual(10, detail.inventory.already_shipped_qty)
        self.assertEqual(92, detail.inventory.remaining_ship_target_qty)
        self.assertEqual(6, detail.inventory.current_result_stock_ship_qty)
        self.assertEqual(20, detail.inventory.current_result_result_ship_qty)
        self.assertEqual(62, detail.inventory.current_result_stock_in_qty)
        self.assertEqual(3, detail.inventory.current_result_discard_qty)

    def _seed_inspection_results(self) -> None:
        now = datetime(2026, 7, 10, 9, 30)
        self.db.add_all(
            [
                Drawing(drawing_id=1, drawing_no="DWG-A", is_active=True),
                RoutingTemplate(
                    routing_template_id=1,
                    template_code="RT-A",
                    template_name="Default",
                    is_active=True,
                ),
                Partner(
                    partner_id=1,
                    partner_type="CUSTOMER",
                    name="Customer A",
                    business_no="100-00-00002",
                    is_active=True,
                ),
                Product(
                    product_id=1,
                    product_code="PRD-A",
                    product_name="Product A",
                    uom="EA",
                    drawing_id=1,
                    routing_template_id=1,
                    is_active=True,
                ),
                OrderLine(
                    order_line_id=1,
                    order_no="SO-1",
                    line_no=1,
                    partner_id=1,
                    product_id=1,
                    order_date=date(2026, 7, 1),
                    due_date=date(2026, 7, 20),
                    order_qty=100,
                    uom="EA",
                    status="CLOSED",
                    is_active=True,
                ),
                Lot(
                    lot_id=1,
                    lot_no="LOT-A",
                    order_line_id=1,
                    product_id=1,
                    lot_qty=80,
                    uom="EA",
                    created_date=date(2026, 7, 1),
                    due_date=date(2026, 7, 20),
                    status="DONE",
                ),
                InspectionSchedule(
                    inspection_schedule_id=1,
                    lot_id=1,
                    inspection_date=date(2026, 7, 1),
                    status="PARTIAL_DONE",
                ),
                InspectionSchedule(
                    inspection_schedule_id=2,
                    lot_id=1,
                    inspection_date=date(2026, 7, 2),
                    status="DONE",
                ),
                InspectionResult(
                    inspection_result_id=1,
                    inspection_schedule_id=1,
                    good_qty=30,
                    defect_ship_qty=5,
                    defect_qty=3,
                    inspected_qty=38,
                    uninspected_qty=2,
                    discard_qty=1,
                    is_partial=True,
                    next_inspection_date=date(2026, 7, 2),
                    partial_reason="partial",
                    created_by="tester",
                    created_at=now - timedelta(days=1),
                    updated_at=now - timedelta(days=1),
                ),
                InspectionResult(
                    inspection_result_id=2,
                    inspection_schedule_id=2,
                    good_qty=40,
                    defect_ship_qty=10,
                    defect_qty=4,
                    inspected_qty=54,
                    uninspected_qty=1,
                    discard_qty=3,
                    is_partial=False,
                    memo="done",
                    created_by="tester",
                    created_at=now,
                    updated_at=now,
                ),
                ProductInventory(
                    product_inventory_id=1,
                    product_id=1,
                    current_qty=20,
                ),
                ProductInventoryLot(
                    product_inventory_lot_id=1,
                    product_id=1,
                    lot_no="STOCK-1",
                    current_qty=12,
                    created_at=now - timedelta(days=3),
                ),
                ProductInventoryLot(
                    product_inventory_lot_id=2,
                    product_id=1,
                    lot_no="LOT-A",
                    current_qty=99,
                    created_at=now - timedelta(days=2),
                ),
                ShipmentLine(
                    shipment_line_id=1,
                    order_line_id=1,
                    product_id=1,
                    product_inventory_lot_id=1,
                    stock_lot_no="STOCK-1",
                    lot_id=1,
                    inspection_result_id=2,
                    source_type="STOCK",
                    status="WAITING",
                    ship_qty=6,
                    shipped_qty=0,
                ),
                ShipmentLine(
                    shipment_line_id=2,
                    order_line_id=1,
                    product_id=1,
                    lot_id=1,
                    inspection_result_id=2,
                    source_type="INSPECTION_RESULT",
                    status="WAITING",
                    ship_qty=20,
                    shipped_qty=0,
                ),
                ProductInventoryMovement(
                    inventory_movement_id=1,
                    product_id=1,
                    product_inventory_lot_id=1,
                    stock_lot_no="STOCK-1",
                    movement_type="INSPECTION_IN",
                    qty=60,
                    balance_after=20,
                    source_type="INSPECTION_RESULT_IN",
                    inspection_schedule_id=2,
                    inspection_result_id=2,
                    order_line_id=1,
                ),
                ProductInventoryMovement(
                    inventory_movement_id=2,
                    product_id=1,
                    product_inventory_lot_id=1,
                    stock_lot_no="STOCK-1",
                    movement_type="SHIP_OUT",
                    qty=-10,
                    balance_after=10,
                    source_type="SHIPMENT",
                    order_line_id=1,
                ),
            ]
        )
        self.db.commit()
