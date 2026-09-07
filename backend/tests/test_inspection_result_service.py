from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine, select
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
from app.core.time import KOREA_TIME_ZONE
from app.services.inspection_result_service import _timestamps_match, upsert_inspection_result


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


class InspectionResultServiceTests(unittest.TestCase):
    def test_concurrency_timestamp_matches_same_instant_across_client_formats(self) -> None:
        stored = datetime(
            2026,
            7,
            14,
            14,
            49,
            48,
            556403,
            tzinfo=KOREA_TIME_ZONE,
        )

        self.assertTrue(
            _timestamps_match(
                stored,
                datetime(2026, 7, 14, 14, 49, 48, 556403),
            )
        )
        self.assertTrue(
            _timestamps_match(
                stored,
                datetime(2026, 7, 14, 5, 49, 48, 556403, tzinfo=timezone.utc),
            )
        )
        self.assertFalse(
            _timestamps_match(
                stored,
                datetime(2026, 7, 14, 5, 49, 49, 556403, tzinfo=timezone.utc),
            )
        )

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        tables = [Base.metadata.tables[name] for name in TEST_TABLE_NAMES]
        Base.metadata.create_all(self.engine, tables=tables)

        SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = SessionLocal()
        self._seed_base_data()

        self.snapshot_patches = [
            patch("app.services.inspection_result_service.refresh_order_line_snapshots_for_lots", return_value=0),
            patch("app.services.inspection_result_service.refresh_order_line_snapshots_for_product", return_value=0),
        ]
        for patcher in self.snapshot_patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in self.snapshot_patches:
            patcher.stop()
        self.db.close()
        self.engine.dispose()

    def test_partial_result_settles_inventory_and_shipment_immediately(self) -> None:
        result, schedule_status, created_next_id = upsert_inspection_result(
            self.db,
            1,
            good_qty=10,
            defect_ship_qty=2,
            defect_qty=1,
            uninspected_qty=0,
            stock_ship_qty=0,
            result_ship_qty=5,
            stock_in_qty=6,
            discard_qty=1,
            is_partial=True,
            next_inspection_date=date(2026, 7, 11),
            partial_reason="partial",
            memo="first partial",
            defects=[],
            actor="tester",
        )
        self.db.commit()

        schedule = self.db.get(InspectionSchedule, 1)
        next_schedule = self.db.get(InspectionSchedule, created_next_id)
        movements = self.db.execute(select(ProductInventoryMovement)).scalars().all()
        shipments = self.db.execute(select(ShipmentLine)).scalars().all()

        self.assertEqual("PARTIAL_DONE", schedule_status)
        self.assertEqual("PARTIAL_DONE", schedule.status)
        self.assertEqual("RECEIVED", next_schedule.status)
        self.assertEqual(date(2026, 7, 11), next_schedule.inspection_date)
        self.assertEqual(0, result.uninspected_qty)
        self.assertIsNotNone(result.settled_at)
        self.assertEqual("tester", result.settled_by)
        self.assertEqual(
            ["INSPECTION_IN", "SHIP_OUT"],
            [movement.movement_type for movement in movements],
        )
        self.assertEqual([11, -5], [movement.qty for movement in movements])
        self.assertEqual(1, len(shipments))
        self.assertEqual("INSPECTION_RESULT", shipments[0].source_type)
        self.assertEqual("DONE", shipments[0].status)
        self.assertEqual(5, shipments[0].shipped_qty)

    def test_partial_result_requires_non_blank_reason(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            upsert_inspection_result(
                self.db,
                1,
                good_qty=10,
                defect_ship_qty=0,
                defect_qty=0,
                uninspected_qty=0,
                stock_ship_qty=0,
                result_ship_qty=0,
                stock_in_qty=0,
                discard_qty=0,
                is_partial=True,
                next_inspection_date=date(2026, 7, 11),
                partial_reason="   ",
                memo=None,
                defects=[],
                actor="tester",
            )

        self.assertEqual(422, raised.exception.status_code)
        self.assertEqual(
            "partial_reason is required when is_partial=true",
            raised.exception.detail,
        )

    def test_partial_result_preserves_unused_reserved_stock_quantity(self) -> None:
        self._add_stock_for_done_settlement()

        upsert_inspection_result(
            self.db,
            1,
            good_qty=10,
            defect_ship_qty=0,
            defect_qty=0,
            uninspected_qty=0,
            stock_ship_qty=4,
            result_ship_qty=0,
            stock_in_qty=10,
            discard_qty=0,
            is_partial=True,
            next_inspection_date=date(2026, 7, 11),
            partial_reason="reserved stock split",
            memo=None,
            defects=[],
            actor="tester",
        )
        self.db.commit()

        shipment_lines = (
            self.db.execute(
                select(ShipmentLine).order_by(ShipmentLine.shipment_line_id.asc())
            )
            .scalars()
            .all()
        )
        self.assertEqual(["DONE", "WAITING"], [line.status for line in shipment_lines])
        self.assertEqual([4, 2], [line.ship_qty for line in shipment_lines])
        self.assertEqual([4, 0], [line.shipped_qty for line in shipment_lines])
        self.assertIsNotNone(shipment_lines[0].inspection_result_id)
        self.assertIsNone(shipment_lines[1].inspection_result_id)

    def test_legacy_unsettled_partial_quantity_is_carried_once(self) -> None:
        first_schedule = self.db.get(InspectionSchedule, 1)
        first_schedule.status = "PARTIAL_DONE"
        first_schedule.finished_at = datetime(2026, 7, 10, 10, 0)
        prior_result = InspectionResult(
            inspection_result_id=1,
            inspection_schedule_id=1,
            good_qty=10,
            defect_ship_qty=2,
            defect_qty=1,
            inspected_qty=13,
            uninspected_qty=0,
            discard_qty=0,
            is_partial=True,
            next_inspection_date=date(2026, 7, 11),
            partial_reason="legacy partial",
            created_by="legacy",
        )
        next_schedule = InspectionSchedule(
            inspection_schedule_id=2,
            lot_id=1,
            inspection_date=date(2026, 7, 11),
            status="IN_PROGRESS",
        )
        self.db.add_all([prior_result, next_schedule])
        self.db.commit()

        current_result, schedule_status, _ = upsert_inspection_result(
            self.db,
            2,
            good_qty=40,
            defect_ship_qty=10,
            defect_qty=4,
            uninspected_qty=13,
            stock_ship_qty=0,
            result_ship_qty=20,
            stock_in_qty=39,
            discard_qty=3,
            is_partial=False,
            next_inspection_date=None,
            partial_reason=None,
            memo="legacy reconciliation",
            defects=[],
            actor="tester",
        )
        self.db.commit()

        movements = (
            self.db.execute(
                select(ProductInventoryMovement).order_by(
                    ProductInventoryMovement.inventory_movement_id.asc()
                )
            )
            .scalars()
            .all()
        )
        self.assertEqual("DONE", schedule_status)
        self.assertIsNotNone(prior_result.settled_at)
        self.assertEqual("tester", prior_result.settled_by)
        self.assertIsNotNone(current_result.settled_at)
        self.assertEqual([59, -20], [movement.qty for movement in movements])
        self.assertEqual(39, self.db.get(ProductInventory, 1).current_qty)

    def test_final_result_after_partial_completes_lot_but_not_under_shipped_order(self) -> None:
        self._add_stock_for_done_settlement()

        _, _, created_next_id = upsert_inspection_result(
            self.db,
            1,
            good_qty=10,
            defect_ship_qty=2,
            defect_qty=1,
            uninspected_qty=0,
            stock_ship_qty=0,
            result_ship_qty=12,
            stock_in_qty=0,
            discard_qty=0,
            is_partial=True,
            next_inspection_date=date(2026, 7, 11),
            partial_reason="remaining quantity",
            memo="first partial",
            defects=[],
            actor="tester",
        )

        next_schedule = self.db.get(InspectionSchedule, created_next_id)
        next_schedule.status = "IN_PROGRESS"
        self.db.flush()

        _, schedule_status, _ = upsert_inspection_result(
            self.db,
            created_next_id,
            good_qty=40,
            defect_ship_qty=10,
            defect_qty=4,
            uninspected_qty=13,
            stock_ship_qty=6,
            result_ship_qty=20,
            stock_in_qty=27,
            discard_qty=3,
            is_partial=False,
            next_inspection_date=None,
            partial_reason=None,
            memo="final",
            defects=[],
            actor="tester",
        )
        self.db.commit()

        lot = self.db.get(Lot, 1)
        order_line = self.db.get(OrderLine, 1)
        first_schedule = self.db.get(InspectionSchedule, 1)
        next_schedule = self.db.get(InspectionSchedule, created_next_id)

        self.assertEqual("DONE", schedule_status)
        self.assertEqual("PARTIAL_DONE", first_schedule.status)
        self.assertEqual("DONE", next_schedule.status)
        self.assertEqual("DONE", lot.status)
        self.assertEqual("CLOSED", order_line.status)

    def test_split_shipment_can_finish_order_before_lot_inspection_finishes(self) -> None:
        order_line = self.db.get(OrderLine, 1)
        order_line.order_qty = 50
        self.db.get(Partner, 1).name = "\ub374\ud2f0\uc6c0"
        self.db.flush()

        first_result, schedule_status, created_next_id = upsert_inspection_result(
            self.db,
            1,
            good_qty=50,
            defect_ship_qty=0,
            defect_qty=0,
            uninspected_qty=0,
            stock_ship_qty=0,
            result_ship_qty=50,
            stock_in_qty=0,
            discard_qty=0,
            is_partial=True,
            next_inspection_date=date(2026, 7, 11),
            partial_reason="잔여 30개 후속 검수",
            memo="주문수량 우선 분할 출고",
            defects=[],
            actor="tester",
        )
        self.db.commit()

        first_schedule = self.db.get(InspectionSchedule, 1)
        lot = self.db.get(Lot, 1)
        order_line = self.db.get(OrderLine, 1)
        first_shipment = self.db.execute(select(ShipmentLine)).scalar_one()

        self.assertEqual("PARTIAL_DONE", schedule_status)
        self.assertEqual("PARTIAL_DONE", first_schedule.status)
        self.assertEqual("RECEIVED", lot.status)
        self.assertEqual("CLOSED", order_line.status)
        self.assertEqual(50, first_shipment.shipped_qty)
        self.assertIsNotNone(first_result.settled_at)

        next_schedule = self.db.get(InspectionSchedule, created_next_id)
        next_schedule.status = "IN_PROGRESS"
        self.db.flush()

        _, final_status, _ = upsert_inspection_result(
            self.db,
            created_next_id,
            good_qty=30,
            defect_ship_qty=0,
            defect_qty=0,
            uninspected_qty=0,
            stock_ship_qty=0,
            result_ship_qty=0,
            stock_in_qty=30,
            discard_qty=0,
            is_partial=False,
            next_inspection_date=None,
            partial_reason=None,
            memo="잔여수량 최종검수",
            defects=[],
            actor="tester",
        )
        self.db.commit()

        inventory = self.db.get(ProductInventory, 1)
        self.assertEqual("DONE", final_status)
        self.assertEqual("DONE", self.db.get(Lot, 1).status)
        self.assertEqual("DONE", self.db.get(OrderLine, 1).status)
        self.assertEqual(30, inventory.current_qty)

    def test_done_result_applies_inventory_in_stock_ship_and_result_ship(self) -> None:
        self._add_stock_for_done_settlement()

        result, schedule_status, created_next_id = upsert_inspection_result(
            self.db,
            1,
            good_qty=40,
            defect_ship_qty=10,
            defect_qty=4,
            uninspected_qty=26,
            stock_ship_qty=6,
            result_ship_qty=20,
            stock_in_qty=27,
            discard_qty=3,
            is_partial=False,
            next_inspection_date=None,
            partial_reason=None,
            memo="done",
            defects=[],
            actor="tester",
        )
        self.db.commit()

        inventory = self.db.get(ProductInventory, 1)
        stock_lot = self.db.get(ProductInventoryLot, 1)
        result_lot = (
            self.db.execute(
                select(ProductInventoryLot).where(
                    ProductInventoryLot.product_id == 1,
                    ProductInventoryLot.lot_no == "LOT-A",
                )
            )
            .scalars()
            .one()
        )
        movements = (
            self.db.execute(
                select(ProductInventoryMovement).order_by(ProductInventoryMovement.inventory_movement_id.asc())
            )
            .scalars()
            .all()
        )
        shipments = (
            self.db.execute(select(ShipmentLine).order_by(ShipmentLine.shipment_line_id.asc()))
            .scalars()
            .all()
        )

        self.assertEqual("DONE", schedule_status)
        self.assertIsNone(created_next_id)
        self.assertEqual(1, result.inspection_result_id)
        self.assertEqual(41, inventory.current_qty)
        self.assertEqual(6, stock_lot.current_qty)
        self.assertEqual(27, result_lot.current_qty)
        self.assertEqual(["SHIP_OUT", "INSPECTION_IN", "SHIP_OUT"], [movement.movement_type for movement in movements])
        self.assertEqual([-6, 47, -20], [movement.qty for movement in movements])
        self.assertEqual(["STOCK", "INSPECTION_RESULT"], [shipment.source_type for shipment in shipments])
        self.assertEqual(["DONE", "DONE"], [shipment.status for shipment in shipments])
        self.assertEqual([6, 20], [shipment.ship_qty for shipment in shipments])

    def test_done_result_rejects_sellable_quantity_mismatch_before_creating_result(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            upsert_inspection_result(
                self.db,
                1,
                good_qty=10,
                defect_ship_qty=0,
                defect_qty=0,
                uninspected_qty=0,
                stock_ship_qty=0,
                result_ship_qty=4,
                stock_in_qty=4,
                discard_qty=1,
                is_partial=False,
                next_inspection_date=None,
                partial_reason=None,
                memo=None,
                defects=[],
                actor="tester",
            )

        result = self.db.execute(select(InspectionResult)).scalar_one_or_none()
        self.assertEqual(422, ctx.exception.status_code)
        self.assertIsNone(result)

    def test_done_result_update_rejects_stale_updated_at(self) -> None:
        self._add_stock_for_done_settlement()
        upsert_inspection_result(
            self.db,
            1,
            good_qty=40,
            defect_ship_qty=10,
            defect_qty=4,
            uninspected_qty=26,
            stock_ship_qty=6,
            result_ship_qty=20,
            stock_in_qty=27,
            discard_qty=3,
            is_partial=False,
            next_inspection_date=None,
            partial_reason=None,
            memo="done",
            defects=[],
            actor="tester",
        )
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            upsert_inspection_result(
                self.db,
                1,
                good_qty=40,
                defect_ship_qty=10,
                defect_qty=4,
                uninspected_qty=26,
                stock_ship_qty=6,
                result_ship_qty=20,
                stock_in_qty=27,
                discard_qty=3,
                is_partial=False,
                next_inspection_date=None,
                partial_reason=None,
                memo="stale update",
                defects=[],
                actor="tester",
                expected_updated_at=datetime(2000, 1, 1),
            )

        self.assertEqual(409, ctx.exception.status_code)

    def test_done_result_update_rebuilds_settlement_without_duplication(self) -> None:
        self._add_stock_for_done_settlement()
        for memo in ("first save", "approved correction"):
            upsert_inspection_result(
                self.db,
                1,
                good_qty=40,
                defect_ship_qty=10,
                defect_qty=4,
                uninspected_qty=26,
                stock_ship_qty=6,
                result_ship_qty=20,
                stock_in_qty=27,
                discard_qty=3,
                is_partial=False,
                next_inspection_date=None,
                partial_reason=None,
                memo=memo,
                defects=[],
                actor="tester",
            )
            self.db.commit()

        inventory = self.db.get(ProductInventory, 1)
        movements = self.db.execute(select(ProductInventoryMovement)).scalars().all()
        shipments = self.db.execute(select(ShipmentLine)).scalars().all()
        inventory_lots = (
            self.db.execute(
                select(ProductInventoryLot).order_by(
                    ProductInventoryLot.product_inventory_lot_id.asc()
                )
            )
            .scalars()
            .all()
        )

        self.assertEqual(41, inventory.current_qty)
        self.assertEqual([6, 27], [lot.current_qty for lot in inventory_lots])
        self.assertEqual(3, len(movements))
        self.assertEqual(2, len(shipments))
        self.assertEqual([6, 20], [line.shipped_qty for line in shipments])

    def _seed_base_data(self) -> None:
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
                    business_no="100-00-00003",
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
                    status="IN_PROGRESS",
                ),
                InspectionSchedule(
                    inspection_schedule_id=1,
                    lot_id=1,
                    inspection_date=date(2026, 7, 10),
                    status="IN_PROGRESS",
                ),
            ]
        )
        self.db.commit()

    def _add_stock_for_done_settlement(self) -> None:
        self.db.add_all(
            [
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
                ),
                ShipmentLine(
                    shipment_line_id=1,
                    order_line_id=1,
                    product_id=1,
                    product_inventory_lot_id=1,
                    stock_lot_no="STOCK-1",
                    lot_id=None,
                    inspection_result_id=None,
                    source_type="STOCK",
                    status="WAITING",
                    ship_qty=6,
                    shipped_qty=0,
                ),
            ]
        )
        self.db.commit()
