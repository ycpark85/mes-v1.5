from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.drawing import Drawing
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.routing_template import RoutingTemplate
from app.models.shipment_line import ShipmentLine
from app.schemas.inventory import (
    InitialInventoryBulkIn,
    InitialInventoryBulkItemIn,
    ProductInventoryAdjustmentIn,
)
from app.services.product_inventory_adjustment_service import adjust_product_inventory_in_session
from app.services.product_inventory_initial_bulk_service import upload_initial_inventory_bulk_in_session
from app.services.product_inventory_query import (
    list_product_inventories,
    list_product_inventory_consistency,
    list_product_inventory_movements,
    list_product_inventory_lots,
)


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, compiler, **kw):
    return "JSON"


TEST_TABLE_NAMES = [
    "drawing",
    "routing_template",
    "product",
    "product_inventory",
    "product_inventory_lot",
    "product_inventory_movement",
    "shipment_line",
]


class ProductInventoryQueryTests(unittest.TestCase):
    def test_adjustment_reason_is_required_by_service_for_legacy_and_exact_lot_requests(self):
        for lot_id in (None, 2):
            for direction in ("IN", "OUT"):
                for memo in (None, "", "   ", "x" * 1001):
                    with self.subTest(lot_id=lot_id, direction=direction, memo_length=len(memo or "")):
                        with self.assertRaises(HTTPException) as blocked:
                            adjust_product_inventory_in_session(self.db, product_id=1,
                                payload=ProductInventoryAdjustmentIn.model_construct(qty=1, stock_lot_no="LOT-A2",
                                    product_inventory_lot_id=lot_id, memo=memo), direction=direction)
                        self.assertEqual(422, blocked.exception.status_code)
        self.assertEqual(10, self.db.get(ProductInventory, 1).current_qty)
        self.assertEqual(6, self.db.get(ProductInventoryLot, 2).current_qty)
        self.assertEqual(3, len(self.db.execute(select(ProductInventoryMovement)).scalars().all()))
        payload = ProductInventoryAdjustmentIn(qty=1, memo=" count ", stock_lot_no="LOT-A2")
        self.assertEqual("count", payload.memo)

    def test_history_snapshot_preserves_filtered_totals_across_stock_pages(self):
        result = list_product_inventory_movements(self.db, product_inventory_lot_id=2,
            stock_page=2, stock_size=1, stock_q="LOT-A")
        snapshot = result.stock_snapshot
        self.assertEqual((10, 10, 2, 2, 1), (snapshot.product_current_qty,
            snapshot.total_qty, snapshot.total, snapshot.page, len(snapshot.items)))
        self.assertEqual(result.current_qty, snapshot.items[0].current_qty)
        filtered = list_product_inventory_movements(self.db, product_inventory_lot_id=2,
            stock_page=1, stock_q="A2", movement_type="SHIP_OUT")
        self.assertEqual((0, 6, 10), (filtered.total, filtered.stock_snapshot.total_qty,
            filtered.stock_snapshot.product_current_qty))
        self.assertIsNone(list_product_inventory_movements(self.db, product_inventory_lot_id=2).stock_snapshot)

    def test_history_snapshot_clamps_page_after_stock_depletion_and_honors_zero_filter(self):
        adjust_product_inventory_in_session(self.db, product_id=1,
            payload=ProductInventoryAdjustmentIn(qty=6, product_inventory_lot_id=2, memo="count"), direction="OUT")
        self.db.commit()
        result = list_product_inventory_movements(self.db, product_inventory_lot_id=2,
            stock_page=2, stock_size=1)
        self.assertEqual((0, 4, 4, 1, 1), (result.current_qty, result.stock_snapshot.product_current_qty,
            result.stock_snapshot.total_qty, result.stock_snapshot.page, result.stock_snapshot.total))
        self.assertEqual(1, result.stock_snapshot.items[0].product_inventory_lot_id)
        zero = list_product_inventory_movements(self.db, product_inventory_lot_id=2,
            stock_page=1, stock_q="A2", stock_include_zero=True)
        self.assertEqual((1, 0, 4), (zero.stock_snapshot.total, zero.stock_snapshot.total_qty,
            zero.stock_snapshot.product_current_qty))
        empty = list_product_inventory_movements(self.db, product_inventory_lot_id=2,
            stock_page=2, stock_q="A2")
        self.assertEqual((1, 0, []), (empty.stock_snapshot.page, empty.stock_snapshot.total, empty.stock_snapshot.items))

    def test_history_snapshot_requires_selected_lot_and_keeps_consistency_warnings(self):
        with self.assertRaises(HTTPException) as missing:
            list_product_inventory_movements(self.db, product_id=1, stock_page=1)
        self.assertEqual(422, missing.exception.status_code)
        with self.assertRaises(HTTPException) as other_product:
            list_product_inventory_movements(self.db, product_id=1, product_inventory_lot_id=3, stock_page=1)
        self.assertEqual(404, other_product.exception.status_code)
        result = list_product_inventory_movements(self.db, product_inventory_lot_id=3, stock_page=1)
        self.assertIsNotNone(result.history_warning)
        self.assertIsNotNone(result.stock_snapshot.stock_warning)

    def test_zero_stock_inventory_preserves_update_timestamps(self):
        updated = datetime(2026, 9, 18, 3, 4, 5)
        self.db.get(ProductInventory, 2).updated_at = updated
        self.db.get(ProductInventory, 2).current_qty = 0
        self.db.commit()
        self.assertEqual(0, list_product_inventories(self.db, q="prd-b").total)
        result = list_product_inventories(self.db, q="prd-b", include_zero=True)
        self.assertEqual(1, result.total)
        self.assertEqual(updated, result.items[0].updated_at)
        lots = list_product_inventory_lots(self.db, product_id=2)
        self.assertEqual(updated, lots.product_updated_at)
        lot_updated = datetime(2026, 9, 18, 4, 5, 6)
        self.db.get(ProductInventoryLot, 3).updated_at = lot_updated
        self.db.commit()
        history = list_product_inventory_movements(self.db, product_inventory_lot_id=3)
        self.assertEqual(lot_updated, history.lot_updated_at)

    def test_lot_inventory_and_zero_stock_are_separately_searchable(self):
        self.db.add(ProductInventoryLot(product_inventory_lot_id=4, product_id=1, lot_no="ZERO", current_qty=0))
        self.db.get(ProductInventory, 2).current_qty = 0
        self.db.commit()
        self.assertEqual([1], [row.product_id for row in list_product_inventories(self.db).items])
        self.assertEqual([1, 2], [row.product_id for row in list_product_inventories(self.db, include_zero=True).items])
        lots = list_product_inventory_lots(self.db, product_id=1, include_zero=True, size=1, page=2)
        self.assertEqual((3, 10, 10, 1), (lots.total, lots.total_qty, lots.product_current_qty, len(lots.items)))
        self.assertEqual("LOT-A2", lots.items[0].lot_no)
        zero = list_product_inventory_lots(self.db, product_id=1, q="zero", include_zero=True)
        self.assertEqual(0, zero.items[0].current_qty)
        self.assertEqual(0, list_product_inventory_lots(self.db, product_id=1, q="zero").total)

    def test_lot_history_balance_is_not_product_balance_or_filtered_running_total(self):
        adjust_product_inventory_in_session(self.db, product_id=1,
            payload=ProductInventoryAdjustmentIn(qty=2, product_inventory_lot_id=2, memo="count"), direction="OUT")
        self.db.commit()
        first = list_product_inventory_movements(self.db, product_id=1, product_inventory_lot_id=2,
            movement_type="ADJUST_OUT", size=1)
        self.assertEqual(4, first.items[0].lot_balance_after)
        self.assertEqual(8, first.items[0].balance_after)
        second = list_product_inventory_movements(self.db, product_id=1, product_inventory_lot_id=2, page=2, size=1)
        self.assertEqual(6, second.items[0].lot_balance_after)
        self.assertEqual(4, second.current_qty)
        self.assertEqual(2, second.product_inventory_lot_id)
        with self.assertRaises(HTTPException):
            list_product_inventory_movements(self.db, product_id=2, product_inventory_lot_id=2)

    def test_korean_day_filter_keeps_earlier_lot_balance_and_signed_corrections(self):
        self.db.add_all([
            ProductInventoryMovement(product_id=1, product_inventory_lot_id=2, stock_lot_no="LOT-A2",
                movement_type="INSPECTION_IN", qty=-2, balance_after=8,
                created_at=datetime(2026, 1, 1, 15, 0)),  # Jan 2, midnight KST.
            ProductInventoryMovement(product_id=1, product_inventory_lot_id=2, stock_lot_no="LOT-A2",
                movement_type="SHIP_OUT", qty=1, balance_after=9,
                created_at=datetime(2026, 1, 2, 14, 59, 59)),
        ])
        self.db.get(ProductInventoryLot, 2).current_qty = 5
        self.db.get(ProductInventory, 1).current_qty = 9
        self.db.commit()
        rows = list_product_inventory_movements(self.db, product_id=1, product_inventory_lot_id=2,
            date_from=date(2026, 1, 2), date_to=date(2026, 1, 2)).items
        self.assertEqual([5, 4], [row.lot_balance_after for row in rows])
        self.assertEqual([1, -2], [row.qty for row in rows])
        self.assertEqual(0, list_product_inventory_movements(self.db, product_inventory_lot_id=2,
            date_from=date(2026, 1, 3)).total)
        with self.assertRaises(HTTPException):
            list_product_inventory_movements(self.db, date_from=date(2026, 1, 3), date_to=date(2026, 1, 2))

    def test_incomplete_lot_history_does_not_display_a_fabricated_balance(self):
        result = list_product_inventory_movements(self.db, product_id=2, product_inventory_lot_id=3)
        self.assertIsNone(result.items[0].lot_balance_after)
        self.assertIsNotNone(result.history_warning)

    def test_selected_lot_adjustment_never_falls_back_to_another_lot(self):
        adjust_product_inventory_in_session(self.db, product_id=1,
            payload=ProductInventoryAdjustmentIn(qty=2, product_inventory_lot_id=2, memo="count"), direction="OUT")
        self.db.commit()
        self.assertEqual(4, self.db.get(ProductInventoryLot, 1).current_qty)
        self.assertEqual(4, self.db.get(ProductInventoryLot, 2).current_qty)
        with self.assertRaises(HTTPException):
            adjust_product_inventory_in_session(self.db, product_id=1,
                payload=ProductInventoryAdjustmentIn(qty=5, product_inventory_lot_id=2, memo="count"), direction="OUT")
        with self.assertRaises(HTTPException):
            adjust_product_inventory_in_session(self.db, product_id=1,
                payload=ProductInventoryAdjustmentIn(qty=1, product_inventory_lot_id=3, memo="count"), direction="IN")
        self.assertEqual(4, self.db.get(ProductInventoryLot, 1).current_qty)

    def test_selected_lot_adjustment_preserves_reservations_and_requires_reason(self):
        self.db.add(ShipmentLine(product_id=1, product_inventory_lot_id=2, stock_lot_no="LOT-A2",
            order_line_id=1, source_type="STOCK", status="WAITING", ship_qty=5, shipped_qty=0))
        self.db.commit()
        for qty, memo in ((2, "count"), (1, " ")):
            with self.assertRaises(HTTPException):
                adjust_product_inventory_in_session(self.db, product_id=1,
                    payload=ProductInventoryAdjustmentIn.model_construct(qty=qty, product_inventory_lot_id=2, memo=memo), direction="OUT")
        adjust_product_inventory_in_session(self.db, product_id=1,
            payload=ProductInventoryAdjustmentIn(qty=3, product_inventory_lot_id=2, memo="count"), direction="IN")
        self.db.commit()
        self.assertEqual(9, self.db.get(ProductInventoryLot, 2).current_qty)

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        tables = [Base.metadata.tables[name] for name in TEST_TABLE_NAMES]
        Base.metadata.create_all(self.engine, tables=tables)

        SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = SessionLocal()
        self._seed_products()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_list_product_inventories_filters_positive_active_stock_and_searches(self) -> None:
        result = list_product_inventories(self.db, q="prd-a")

        self.assertEqual(1, result.total)
        self.assertEqual(1, len(result.items))
        self.assertEqual("PRD-A", result.items[0].product_code)
        self.assertEqual(10, result.items[0].current_qty)

    def test_list_product_inventory_movements_filters_and_orders_latest_first(self) -> None:
        result = list_product_inventory_movements(self.db, product_id=1, movement_type="ADJUST_IN")

        self.assertEqual(2, result.total)
        self.assertEqual([2, 1], [item.inventory_movement_id for item in result.items])
        self.assertEqual(["LOT-A2", "LOT-A1"], [item.stock_lot_no for item in result.items])

    def test_list_product_inventory_consistency_returns_only_mismatched_stock(self) -> None:
        result = list_product_inventory_consistency(self.db)

        self.assertEqual(1, result.total)
        self.assertEqual("PRD-B", result.items[0].product_code)
        self.assertEqual(5, result.items[0].current_qty)
        self.assertEqual(3, result.items[0].lot_qty)
        self.assertEqual(5, result.items[0].movement_qty)
        self.assertEqual(2, result.items[0].diff_qty)

    def test_adjust_product_inventory_in_adds_lot_inventory_and_movement(self) -> None:
        result = adjust_product_inventory_in_session(
            self.db,
            product_id=1,
            payload=ProductInventoryAdjustmentIn(qty=7, stock_lot_no=" lot-a3 ", memo="manual in"),
            direction="in",
        )
        self.db.commit()

        inventory = self.db.get(ProductInventory, 1)
        inventory_lot = (
            self.db.execute(select(ProductInventoryLot).where(ProductInventoryLot.lot_no == "LOT-A3"))
            .scalar_one()
        )

        self.assertEqual(17, inventory.current_qty)
        self.assertEqual(7, inventory_lot.current_qty)
        self.assertEqual("ADJUST_IN", result.movement.movement_type)
        self.assertEqual(7, result.movement.qty)
        self.assertEqual(17, result.movement.balance_after)

    def test_adjust_product_inventory_out_consumes_lots_fifo(self) -> None:
        result = adjust_product_inventory_in_session(
            self.db,
            product_id=1,
            payload=ProductInventoryAdjustmentIn(qty=6, memo="manual out"),
            direction="OUT",
        )
        self.db.commit()

        inventory = self.db.get(ProductInventory, 1)
        lot_a1 = self.db.get(ProductInventoryLot, 1)
        lot_a2 = self.db.get(ProductInventoryLot, 2)
        movements = (
            self.db.execute(
                select(ProductInventoryMovement)
                .where(ProductInventoryMovement.product_id == 1)
                .order_by(ProductInventoryMovement.inventory_movement_id.asc())
            )
            .scalars()
            .all()
        )

        self.assertEqual(4, inventory.current_qty)
        self.assertEqual(0, lot_a1.current_qty)
        self.assertEqual(4, lot_a2.current_qty)
        self.assertEqual("ADJUST_OUT", result.movement.movement_type)
        self.assertEqual("LOT-A2", result.movement.stock_lot_no)
        self.assertEqual([-4, -2], [movement.qty for movement in movements[-2:]])

    def test_adjust_product_inventory_out_rejects_insufficient_stock(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            adjust_product_inventory_in_session(
                self.db,
                product_id=1,
                payload=ProductInventoryAdjustmentIn(qty=11, memo="too much"),
                direction="OUT",
            )

        self.assertEqual(409, ctx.exception.status_code)
        self.assertEqual(10, self.db.get(ProductInventory, 1).current_qty)

    def test_upload_initial_inventory_bulk_creates_inventory_lot_and_movement(self) -> None:
        result = upload_initial_inventory_bulk_in_session(
            self.db,
            InitialInventoryBulkIn(
                items=[
                    InitialInventoryBulkItemIn(
                        row_number=2,
                        product_code=" prd-d ",
                        lot_no=" lot-d1 ",
                        initial_qty=8,
                        memo="opening",
                    ),
                    InitialInventoryBulkItemIn(
                        row_number=3,
                        product_code="PRD-D",
                        lot_no="LOT-D0",
                        initial_qty=0,
                    ),
                ]
            ),
        )
        self.db.commit()

        inventory = (
            self.db.execute(select(ProductInventory).where(ProductInventory.product_id == 4))
            .scalar_one()
        )
        inventory_lot = (
            self.db.execute(select(ProductInventoryLot).where(ProductInventoryLot.product_id == 4))
            .scalar_one()
        )
        movement = (
            self.db.execute(select(ProductInventoryMovement).where(ProductInventoryMovement.product_id == 4))
            .scalar_one()
        )

        self.assertEqual(2, result.total_count)
        self.assertEqual(1, result.success_count)
        self.assertEqual(1, result.skipped_count)
        self.assertEqual(0, result.failure_count)
        self.assertEqual(8, inventory.current_qty)
        self.assertEqual("LOT-D1", inventory_lot.lot_no)
        self.assertEqual(8, inventory_lot.current_qty)
        self.assertEqual("INITIAL_STOCK", movement.movement_type)
        self.assertEqual(8, movement.balance_after)

    def test_upload_initial_inventory_bulk_reports_row_errors_and_keeps_valid_rows(self) -> None:
        result = upload_initial_inventory_bulk_in_session(
            self.db,
            InitialInventoryBulkIn(
                items=[
                    InitialInventoryBulkItemIn(row_number=2, product_code="PRD-D", lot_no="LOT-D2", initial_qty=3),
                    InitialInventoryBulkItemIn(row_number=3, product_code="UNKNOWN", lot_no="LOT-X", initial_qty=4),
                    InitialInventoryBulkItemIn(row_number=4, product_code="PRD-D", lot_no="LOT-D2", initial_qty=5),
                    InitialInventoryBulkItemIn(row_number=5, product_code="PRD-A", lot_no="LOT-A9", initial_qty=1),
                ]
            ),
        )
        self.db.commit()

        inventory = (
            self.db.execute(select(ProductInventory).where(ProductInventory.product_id == 4))
            .scalar_one()
        )
        created_lots = (
            self.db.execute(select(ProductInventoryLot).where(ProductInventoryLot.product_id == 4))
            .scalars()
            .all()
        )

        self.assertEqual(4, result.total_count)
        self.assertEqual(1, result.success_count)
        self.assertEqual(0, result.skipped_count)
        self.assertEqual(3, result.failure_count)
        self.assertEqual([3, 4, 5], sorted(error.row_number for error in result.errors))
        self.assertEqual(3, inventory.current_qty)
        self.assertEqual(["LOT-D2"], [lot.lot_no for lot in created_lots])

    def _seed_products(self) -> None:
        self.db.add_all(
            [
                Drawing(drawing_id=1, drawing_no="DWG-A", is_active=True),
                Drawing(drawing_id=2, drawing_no="DWG-B", is_active=True),
                Drawing(drawing_id=3, drawing_no="DWG-C", is_active=True),
                Drawing(drawing_id=4, drawing_no="DWG-D", is_active=True),
                RoutingTemplate(routing_template_id=1, template_code="RT-A", template_name="Default", is_active=True),
                RoutingTemplate(routing_template_id=2, template_code="RT-B", template_name="Sub", is_active=True),
                RoutingTemplate(routing_template_id=3, template_code="RT-C", template_name="Inactive", is_active=True),
                RoutingTemplate(routing_template_id=4, template_code="RT-D", template_name="Opening", is_active=True),
                Product(
                    product_id=1,
                    product_code="PRD-A",
                    product_name="Product A",
                    uom="EA",
                    drawing_id=1,
                    routing_template_id=1,
                    is_active=True,
                ),
                Product(
                    product_id=2,
                    product_code="PRD-B",
                    product_name="Product B",
                    uom="EA",
                    drawing_id=2,
                    routing_template_id=2,
                    is_active=True,
                ),
                Product(
                    product_id=3,
                    product_code="PRD-C",
                    product_name="Inactive Product",
                    uom="EA",
                    drawing_id=3,
                    routing_template_id=3,
                    is_active=False,
                ),
                Product(
                    product_id=4,
                    product_code="PRD-D",
                    product_name="Product D",
                    uom="EA",
                    drawing_id=4,
                    routing_template_id=4,
                    is_active=True,
                ),
                ProductInventory(product_inventory_id=1, product_id=1, current_qty=10),
                ProductInventory(product_inventory_id=2, product_id=2, current_qty=5),
                ProductInventory(product_inventory_id=3, product_id=3, current_qty=99),
                ProductInventoryLot(product_inventory_lot_id=1, product_id=1, lot_no="LOT-A1", current_qty=4),
                ProductInventoryLot(product_inventory_lot_id=2, product_id=1, lot_no="LOT-A2", current_qty=6),
                ProductInventoryLot(product_inventory_lot_id=3, product_id=2, lot_no="LOT-B1", current_qty=3),
            ]
        )
        self.db.flush()

        base_time = datetime(2026, 1, 1, 9, 0, 0)
        self.db.add_all(
            [
                ProductInventoryMovement(
                    inventory_movement_id=1,
                    product_id=1,
                    product_inventory_lot_id=1,
                    stock_lot_no="LOT-A1",
                    movement_type="ADJUST_IN",
                    qty=4,
                    balance_after=4,
                    source_type="MANUAL_ADJUST",
                    created_at=base_time,
                ),
                ProductInventoryMovement(
                    inventory_movement_id=2,
                    product_id=1,
                    product_inventory_lot_id=2,
                    stock_lot_no="LOT-A2",
                    movement_type="ADJUST_IN",
                    qty=6,
                    balance_after=10,
                    source_type="MANUAL_ADJUST",
                    created_at=base_time + timedelta(minutes=1),
                ),
                ProductInventoryMovement(
                    inventory_movement_id=3,
                    product_id=2,
                    product_inventory_lot_id=3,
                    stock_lot_no="LOT-B1",
                    movement_type="INITIAL_STOCK",
                    qty=5,
                    balance_after=5,
                    source_type="INITIAL_STOCK_BULK",
                    created_at=base_time + timedelta(minutes=2),
                ),
            ]
        )
        self.db.commit()

        product_count = self.db.execute(select(Product)).scalars().all()
        self.assertEqual(4, len(product_count))


if __name__ == "__main__":
    unittest.main()
