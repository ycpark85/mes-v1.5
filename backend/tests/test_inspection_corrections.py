"""Regression scenarios use synthetic data only, optionally on a dedicated local PostgreSQL instance."""
from __future__ import annotations

import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.inspection_result import InspectionResult
from app.models.inspection_result_revision import InspectionResultRevision
from app.models.inspection_certificate import InspectionCertificate
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.shipment_line import ShipmentLine
from app.schemas.inventory import ProductInventoryAdjustmentIn
from app.schemas.order_line import OrderLineShortCloseRequest
from app.services.inspection_result_query import get_inspection_inventory_summary
from app.services.inspection_result_service import upsert_inspection_result
from app.services.inspection_schedule_query import list_inspection_stock_lots
from app.services.order_line_cancel_service import cancel_order_line_status
from app.services.order_line_short_close_service import short_close_order_line_status
from app.services.order_line_plan_service import add_stock_shipment_lines_by_inventory_lot
from app.services.product_inventory_adjustment_service import adjust_product_inventory_in_session
from app.services.shipment_confirm_service import confirm_shipment_lines_in_session
from tests import test_inspection_result_service as fixtures
from scripts.inspection_regression_gate import validate_test_url


class InspectionCorrectionsTests(unittest.TestCase):
    _seed_base_data = fixtures.InspectionResultServiceTests._seed_base_data

    def setUp(self):
        self.pg_url = os.environ.get("MES_INSPECTION_TEST_PG_URL")
        self.schema = None
        if not self.pg_url:
            fixtures.InspectionResultServiceTests.setUp(self)
        else:
            validate_test_url(self.pg_url)
            self.schema = "inspection_test_" + uuid4().hex
            self.admin_engine = create_engine(self.pg_url, isolation_level="AUTOCOMMIT")
            with self.admin_engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public"))
                conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            self.engine = create_engine(self.pg_url, connect_args={"options": f"-csearch_path={self.schema},public"})
            self.addCleanup(self._cleanup_pg)
            Base.metadata.create_all(self.engine)
            self.db = sessionmaker(self.engine, autoflush=False)()
            self._seed_base_data()
            self._sync_sequences()
            self.snapshot_patches = [
                patch("app.services.inspection_result_service.refresh_order_line_snapshots_for_lots", return_value=0),
                patch("app.services.inspection_result_service.refresh_order_line_snapshots_for_product", return_value=0),
            ]
            for item in self.snapshot_patches:
                item.start()
        for name in ("refresh_order_line_snapshot", "refresh_order_line_snapshots_for_product"):
            item = patch("app.services.shipment_confirm_service." + name, return_value=0)
            item.start()
            self.snapshot_patches.append(item)

    def tearDown(self):
        fixtures.InspectionResultServiceTests.tearDown(self)

    def _cleanup_pg(self):
        if self.schema:
            if hasattr(self, "db"):
                self.db.close()
            self.engine.dispose()
            with self.admin_engine.connect() as conn:
                conn.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
            self.admin_engine.dispose()

    def _save(self, db=None, schedule_id=1, **changes):
        db = db or self.db
        existing = db.execute(select(InspectionResult).where(
            InspectionResult.inspection_schedule_id == schedule_id)).scalar_one_or_none()
        values = dict(good_qty=80, defect_ship_qty=0, defect_qty=0, uninspected_qty=0,
            stock_ship_qty=0, result_ship_qty=50, stock_in_qty=30, discard_qty=0,
            is_partial=False, next_inspection_date=None, partial_reason=None,
            memo=None, defects=[], actor="regression",
            expected_updated_at=existing.updated_at if existing else None)
        values.update(changes)
        return upsert_inspection_result(db, schedule_id, **values)[0]

    def _sync_sequences(self):
        if self.pg_url:
            for table in ("inspection_schedule", "inspection_result", "order_line", "lot",
                          "product_inventory", "product_inventory_lot"):
                key = table + "_id"
                self.db.execute(text(f"SELECT setval(pg_get_serial_sequence(:table, :key), "
                    f"COALESCE(MAX({key}), 1), MAX({key}) IS NOT NULL) FROM {table}"),
                    {"table": table, "key": key})
            self.db.commit()

    def _stock(self, qty=65, own=0, other=0):
        self.db.add_all([
            ProductInventory(product_id=1, current_qty=qty),
            ProductInventoryLot(product_inventory_lot_id=1, product_id=1, lot_no="OLD", current_qty=qty),
        ])
        if other:
            self.db.add(OrderLine(order_line_id=2, order_no="SO-2", line_no=1, partner_id=1,
                product_id=1, order_date=date(2026, 7, 1), due_date=date(2026, 7, 20),
                order_qty=100, uom="EA", status="CLOSED", is_active=True))
        self.db.flush()
        for order_id, reserved in ((1, own), (2, other)):
            if reserved:
                self.db.add(ShipmentLine(order_line_id=order_id, product_id=1,
                    product_inventory_lot_id=1, stock_lot_no="OLD", source_type="STOCK",
                    status="WAITING", ship_qty=reserved, shipped_qty=0))
        self.db.commit()

        self._sync_sequences()

    def test_summary_detail_and_save_use_own_reservation(self):
        self._stock(65, own=65)
        summary = get_inspection_inventory_summary(self.db, inspection_schedule_id=1, current_result_id=None)
        detail = list_inspection_stock_lots(self.db, 1)
        self.assertEqual(65, summary.current_stock_qty)
        self.assertEqual(summary.current_stock_qty, detail.total_stock_qty)
        self._save(stock_ship_qty=65, result_ship_qty=20, stock_in_qty=60)
        self.db.commit()
        self.assertEqual(60, self.db.execute(select(ProductInventory)).scalar_one().current_qty)

    def test_new_result_does_not_prefill_shipments_from_confirmed_plan(self):
        self._stock(65, own=65)
        self.db.get(OrderLine, 1).decision_made = True
        self.db.add(OrderLinePlanHistory(order_line_id=1, plan_type="PARTIAL_STOCK_PLUS_PRODUCTION",
            ship_target_qty=100, stock_ship_qty=65, production_qty=35))
        self.db.commit()
        summary = get_inspection_inventory_summary(self.db, inspection_schedule_id=1, current_result_id=None)
        self.assertEqual(65, summary.current_stock_qty)
        self.assertEqual(0, summary.current_result_stock_ship_qty)
        self.assertEqual(0, summary.current_result_result_ship_qty)
        self.assertEqual(65, list_inspection_stock_lots(self.db, 1).items[0].reserved_qty)

    def test_oversubscribed_reservations_show_physical_stock_and_block_write(self):
        self._stock(65, own=65, other=540)
        detail = list_inspection_stock_lots(self.db, 1)
        self.assertEqual(65, detail.items[0].physical_qty)
        self.assertEqual(540, detail.items[0].other_reserved_qty)
        self.assertIsNotNone(detail.stock_error)
        with self.assertRaises(HTTPException):
            self._save(stock_ship_qty=65, result_ship_qty=20, stock_in_qty=60)
        self.db.rollback()
        self.assertIsNone(self.db.execute(select(InspectionResult)).scalar_one_or_none())
        self.assertEqual(65, self.db.execute(select(ProductInventory)).scalar_one().current_qty)

    def test_manual_decrease_cannot_consume_reserved_stock(self):
        self._stock(65, own=60)
        with self.assertRaises(HTTPException):
            adjust_product_inventory_in_session(self.db, product_id=1,
                payload=ProductInventoryAdjustmentIn(qty=6, memo="count"), direction="OUT")
        self.db.rollback()
        self.assertEqual(65, self.db.execute(select(ProductInventory)).scalar_one().current_qty)
        adjust_product_inventory_in_session(self.db, product_id=1,
            payload=ProductInventoryAdjustmentIn(qty=5, memo="count"), direction="OUT")
        self.db.commit()
        self.assertEqual(60, self.db.get(ProductInventoryLot, 1).current_qty)

    def test_stock_replenishment_target_zero_and_completion(self):
        self._stock(65)
        self.db.get(OrderLine, 1).decision_made = True
        self.db.add(OrderLinePlanHistory(order_line_id=1, plan_type="STOCK_REPLENISHMENT",
            ship_target_qty=0, stock_ship_qty=0, production_qty=100))
        self.db.commit()
        summary = get_inspection_inventory_summary(self.db, inspection_schedule_id=1, current_result_id=None)
        self.assertEqual(0, summary.ship_target_qty)
        self.assertEqual(0, summary.current_result_stock_ship_qty)
        self._save(good_qty=100, result_ship_qty=0, stock_in_qty=100)
        self.db.commit()
        self.assertEqual("DONE", self.db.get(OrderLine, 1).status)
        self.assertEqual(165, self.db.execute(select(ProductInventory)).scalar_one().current_qty)
        self.assertEqual([], self.db.execute(select(ShipmentLine)).scalars().all())

    def test_consumed_production_cannot_be_removed_by_edit(self):
        result = self._save()
        self.db.commit()
        inv = self.db.execute(select(ProductInventory)).scalar_one()
        lot = self.db.execute(select(ProductInventoryLot)).scalar_one()
        inv.current_qty = lot.current_qty = 5  # 25 consumed by a later transaction.
        self.db.commit()
        with self.assertRaises(HTTPException):
            self._save(good_qty=70, stock_in_qty=20, shortage_reason="actual correction")
        self.db.rollback()
        self.assertEqual(80, self.db.get(InspectionResult, result.inspection_result_id).good_qty)
        self.assertEqual(5, self.db.execute(select(ProductInventory)).scalar_one().current_qty)

    def test_quantity_decrease_is_audited_delta_and_reopens_order(self):
        self._save(good_qty=102, result_ship_qty=102, stock_in_qty=0)
        self.db.commit()
        old_movements = self.db.execute(select(ProductInventoryMovement)).scalars().all()
        old_ids = {row.inventory_movement_id for row in old_movements}
        self.assertEqual("DONE", self.db.get(OrderLine, 1).status)
        self._save(good_qty=100, result_ship_qty=95, stock_in_qty=5)
        self.db.commit()
        self.assertEqual("CLOSED", self.db.get(OrderLine, 1).status)
        movements = self.db.execute(select(ProductInventoryMovement)).scalars().all()
        self.assertTrue(old_ids.issubset({row.inventory_movement_id for row in movements}))
        self.assertEqual(5, sum(row.qty for row in movements))
        self.assertEqual(2, self.db.query(InspectionResultRevision).count())
        self.assertEqual(95, sum(row.shipped_qty for row in self.db.execute(select(ShipmentLine)).scalars()))

    def test_meta_only_edit_preserves_ids_despite_unrelated_stock_discrepancy(self):
        result = self._save()
        self.db.commit()
        self.db.execute(select(ProductInventory)).scalar_one().current_qty = 25
        self.db.commit()
        old_ids = list(self.db.execute(select(ProductInventoryMovement.inventory_movement_id)).scalars())
        self._save(memo="metadata only")
        self.db.commit()
        self.assertEqual(old_ids, list(self.db.execute(select(ProductInventoryMovement.inventory_movement_id)).scalars()))
        self.assertEqual(25, self.db.execute(select(ProductInventory)).scalar_one().current_qty)

    def test_missing_edit_version_is_rejected(self):
        self._save()
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            self._save(expected_updated_at=None)
        self.assertEqual(409, error.exception.status_code)

    def test_legacy_waiting_shipment_blocks_duplicate_settlement(self):
        result = self._save()
        self.db.commit()
        self.db.add(ShipmentLine(order_line_id=1, product_id=1,
            inspection_result_id=result.inspection_result_id,
            source_type="INSPECTION_RESULT", status="WAITING", ship_qty=50, shipped_qty=0))
        self.db.commit()
        old_ids = list(self.db.execute(select(ProductInventoryMovement.inventory_movement_id)).scalars())
        summary = get_inspection_inventory_summary(self.db, inspection_schedule_id=1,
            current_result_id=result.inspection_result_id)
        self.assertIn("미완료 출고", summary.settlement_error)
        with self.assertRaises(HTTPException) as error:
            self._save()
        self.assertEqual(409, error.exception.status_code)
        self.db.rollback()
        self.assertEqual(old_ids, list(self.db.execute(select(ProductInventoryMovement.inventory_movement_id)).scalars()))
        self.assertEqual(30, self.db.execute(select(ProductInventory)).scalar_one().current_qty)

    def test_stock_and_production_allocation_edits_preserve_net_balances(self):
        self._stock(65, own=20)
        for stock_qty, production_qty in ((20, 50), (10, 40), (30, 60), (0, 0), (30, 60), (30, 60)):
            self._save(stock_ship_qty=stock_qty, result_ship_qty=production_qty, stock_in_qty=80 - production_qty)
            self.db.commit()
            expected = 65 + 80 - stock_qty - production_qty
            self.assertEqual(expected, self.db.execute(select(ProductInventory)).scalar_one().current_qty)
            self.assertEqual(expected, self.db.execute(select(func.sum(ProductInventoryLot.current_qty))).scalar_one())
            self.assertEqual(expected - 65, self.db.execute(select(func.sum(ProductInventoryMovement.qty))).scalar_one())
            self.assertEqual(stock_qty + production_qty, self.db.execute(select(func.coalesce(func.sum(ShipmentLine.shipped_qty), 0))).scalar_one())

    def test_issued_certificate_blocks_quantity_change_but_allows_memo(self):
        result = self._save()
        self.db.commit()
        self.db.add(InspectionCertificate(lot_id=1, basis_inspection_result_id=result.inspection_result_id,
                                         issued_by="tester"))
        self.db.commit()
        self._save(memo="metadata")
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            self._save(good_qty=85, stock_in_qty=35)
        self.assertEqual(409, error.exception.status_code)
        self.db.rollback()
        self.assertEqual(80, self.db.get(InspectionResult, result.inspection_result_id).good_qty)

    def test_cancel_and_short_close_release_only_own_waiting_reservations(self):
        self._stock(65, own=20, other=10)
        self.db.get(Lot, 1).status = "CANCELED"
        cancel_order_line_status(self.db, 1)
        self.db.commit()
        lines = self.db.execute(select(ShipmentLine).order_by(ShipmentLine.order_line_id)).scalars().all()
        self.assertEqual(["CANCELED", "WAITING"], [line.status for line in lines])
        short_close_order_line_status(self.db, 2, OrderLineShortCloseRequest(memo="closed short"), actor="tester")
        self.db.commit()
        self.assertEqual("CANCELED", lines[1].status)
        self.assertEqual(65, self.db.execute(select(ProductInventory)).scalar_one().current_qty)

    def test_shipment_confirmation_cannot_bypass_customer_target(self):
        self._stock(200, own=103)
        shipment_id = self.db.execute(select(ShipmentLine.shipment_line_id)).scalar_one()
        with self.assertRaises(HTTPException) as error:
            confirm_shipment_lines_in_session(self.db, [shipment_id])
        self.assertEqual(422, error.exception.status_code)
        self.db.rollback()
        self.assertEqual(200, self.db.execute(select(ProductInventory)).scalar_one().current_qty)

    def test_same_lot_previous_round_inventory_is_visible_and_can_be_shipped_manually(self):
        first = self._save(good_qty=30, result_ship_qty=0, stock_in_qty=30,
            is_partial=True, next_inspection_date=date(2026, 7, 11), partial_reason="continue")
        self.db.commit()
        next_id = self.db.execute(select(InspectionSchedule.inspection_schedule_id).where(
            InspectionSchedule.inspection_schedule_id != 1)).scalar_one()
        detail = list_inspection_stock_lots(self.db, next_id)
        self.assertEqual(30, detail.total_stock_qty)
        self.assertEqual("LOT-A", detail.items[0].lot_no)
        self.assertEqual(30, detail.items[0].physical_qty)
        self.assertEqual([], self.db.execute(select(ShipmentLine)).scalars().all())
        summary = get_inspection_inventory_summary(self.db, inspection_schedule_id=next_id, current_result_id=None)
        self.assertEqual(0, summary.current_result_stock_ship_qty)
        self.assertEqual(0, summary.prior_unsettled_sellable_qty)
        self.db.get(InspectionSchedule, next_id).status = "IN_PROGRESS"  # Operator starts round two.
        self.db.commit()
        second = self._save(schedule_id=next_id, good_qty=50, stock_ship_qty=30,
            result_ship_qty=50, stock_in_qty=0)
        self.db.commit()
        self.assertEqual(0, self.db.execute(select(ProductInventory)).scalar_one().current_qty)
        self.assertEqual(0, self.db.execute(select(ProductInventoryLot)).scalar_one().current_qty)
        self.assertEqual(80, self.db.execute(select(func.sum(InspectionResult.good_qty))).scalar_one())
        movements = self.db.execute(select(ProductInventoryMovement)).scalars().all()
        self.assertEqual(80, sum(m.qty for m in movements if m.movement_type == "INSPECTION_IN"))
        self.assertEqual(-80, sum(m.qty for m in movements if m.movement_type == "SHIP_OUT"))
        lines = self.db.execute(select(ShipmentLine)).scalars().all()
        self.assertEqual({("STOCK", 30), ("INSPECTION_RESULT", 50)},
            {(line.source_type, line.shipped_qty) for line in lines})
        self.assertTrue(all(line.inspection_result_id == second.inspection_result_id for line in lines))
        self.assertEqual(first.inspection_result_id, first.settlement_owner_id)

    def test_migration_maps_612_carry_once_without_changing_balances(self):
        migration_path = Path(__file__).resolve().parents[1] / "migrations/versions/5a6b7c8d9e0f_preserve_inspection_settlement_ownership.py"
        spec = importlib.util.spec_from_file_location("inspection_ownership_migration", migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        first = self.db.get(InspectionSchedule, 1)
        first.status = "PARTIAL_DONE"
        stamp = datetime(2026, 9, 8, 7, 56, 6, tzinfo=timezone.utc)
        for sid, qty in ((1, 19500), (2, 20000), (3, 50000)):
            if sid != 1:
                self.db.add(InspectionSchedule(inspection_schedule_id=sid, lot_id=1,
                    inspection_date=date(2026, 7, 9 + sid), status="DONE" if sid == 3 else "PARTIAL_DONE"))
                self.db.flush()
            self.db.add(InspectionResult(inspection_result_id=sid, inspection_schedule_id=sid,
                good_qty=qty, defect_qty=0, defect_ship_qty=0, inspected_qty=qty,
                is_partial=sid != 3, settled_at=stamp, settled_by="tester"))
        self.db.flush()
        self.db.add(ProductInventoryMovement(product_id=1, movement_type="INSPECTION_IN", qty=89500,
            balance_after=89500, inspection_result_id=3, source_type="INSPECTION_RESULT_IN"))
        self.db.commit()
        for _ in range(2):
            migration.backfill_settlement_owners(self.db.connection())
            self.db.commit()
        self.db.expire_all()
        rows = self.db.execute(select(InspectionResult).order_by(InspectionResult.inspection_result_id)).scalars().all()
        self.assertEqual([3, 3, 3], [row.settlement_owner_id for row in rows])
        self.assertEqual([19500, 20000, 50000], [row.settled_sellable_qty for row in rows])
        self.assertEqual(89500, self.db.execute(select(ProductInventoryMovement.qty)).scalar_one())

    def test_concurrent_result_edit_has_one_winner(self):
        if not self.pg_url:
            self.skipTest("requires dedicated PostgreSQL instance")
        result = self._save()
        self.db.commit()
        expected = result.updated_at
        barrier = Barrier(2)
        def worker(good):
            with sessionmaker(self.engine, autoflush=False)() as db:
                barrier.wait(timeout=10)
                try:
                    self._save(db, good_qty=good, stock_in_qty=good - 50, expected_updated_at=expected)
                    db.commit()
                    return "OK"
                except HTTPException as error:
                    db.rollback()
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(worker, (85, 90)))
        self.assertCountEqual(["OK", 409], outcomes)
        self.db.expire_all()
        current = self.db.get(InspectionResult, result.inspection_result_id)
        self.assertEqual(current.good_qty - 50, self.db.execute(select(ProductInventory)).scalar_one().current_qty)

    def test_inspection_read_snapshot_stays_consistent_during_stock_change(self):
        if not self.pg_url:
            self.skipTest("requires dedicated PostgreSQL instance")
        from app.db.inspection_read import get_inspection_read_db
        from app.services.inspection_result_query import get_inspection_result_detail
        self._stock(65)
        factory = sessionmaker(self.engine, autoflush=False)
        changed = False
        def change_after_lot_read(conn, cursor, statement, parameters, context, executemany):
            nonlocal changed
            if not changed and "from product_inventory_lot" in statement.lower():
                changed = True
                with factory() as writer:
                    adjust_product_inventory_in_session(writer, product_id=1,
                        payload=ProductInventoryAdjustmentIn(qty=5, stock_lot_no="OLD", memo="concurrent test"),
                        direction="OUT")
                    writer.commit()

        with patch("app.db.inspection_read.SessionLocal", factory):
            reader = get_inspection_read_db()
            db = next(reader)
            connection = db.connection()
            event.listen(connection, "after_cursor_execute", change_after_lot_read)
            try:
                detail = get_inspection_result_detail(db, 1)
                self.assertTrue(changed)
                self.assertEqual(65, detail.inventory.current_stock_qty)
                self.assertEqual(65, detail.inventory.physical_stock_qty)
                self.assertEqual(65, detail.inventory.stock_lots[0].physical_qty)
                self.assertIsNone(detail.inventory.stock_error)
            finally:
                event.remove(connection, "after_cursor_execute", change_after_lot_read)
                reader.close()
            refreshed_reader = get_inspection_read_db()
            try:
                fresh = get_inspection_result_detail(next(refreshed_reader), 1)
                self.assertEqual(60, fresh.inventory.current_stock_qty)
                self.assertEqual(60, fresh.inventory.stock_lots[0].physical_qty)
            finally:
                refreshed_reader.close()

    def test_inspection_read_session_is_read_only_and_resets_on_close(self):
        if not self.pg_url:
            self.skipTest("requires dedicated PostgreSQL instance")
        from app.db.inspection_read import get_inspection_read_db
        from app.services.inspection_result_query import get_inspection_result_detail
        self._save()
        self.db.commit()
        factory = sessionmaker(self.engine, autoflush=False)
        with patch("app.db.inspection_read.SessionLocal", factory):
            reader = get_inspection_read_db()
            db = next(reader)
            try:
                detail = get_inspection_result_detail(db, 1)
                self.assertEqual(80, detail.result.good_qty)
                self.assertIsNone(detail.inventory.settlement_error)
                self.assertEqual("repeatable read", db.execute(text("SHOW transaction_isolation")).scalar_one())
                self.assertEqual("on", db.execute(text("SHOW transaction_read_only")).scalar_one())
                with self.assertRaises(DBAPIError):
                    db.execute(text("UPDATE lot SET memo = 'must not write' WHERE lot_id = 1"))
            finally:
                reader.close()
        with factory() as ordinary:
            self.assertEqual("read committed", ordinary.execute(text("SHOW transaction_isolation")).scalar_one())
            self.assertEqual("off", ordinary.execute(text("SHOW transaction_read_only")).scalar_one())
            self.assertNotEqual("must not write", ordinary.get(Lot, 1).memo)

    def test_stock_change_after_preview_is_revalidated_on_save(self):
        self._stock(65)
        summary = get_inspection_inventory_summary(self.db, inspection_schedule_id=1, current_result_id=None)
        self.assertEqual(65, summary.current_stock_qty)
        adjust_product_inventory_in_session(self.db, product_id=1,
            payload=ProductInventoryAdjustmentIn(qty=50, stock_lot_no="OLD", memo="consumed after preview"),
            direction="OUT")
        self.db.commit()
        before = self._business_snapshot()
        with self.assertRaises(HTTPException) as error:
            self._save(stock_ship_qty=20)
        self.assertEqual(422, error.exception.status_code)
        self.db.rollback()
        self.assertEqual(before, self._business_snapshot())

    def test_concurrent_reservations_cannot_reserve_same_stock_twice(self):
        if not self.pg_url:
            self.skipTest("requires dedicated PostgreSQL instance")
        self._stock(65, other=1)
        old = self.db.execute(select(ShipmentLine)).scalar_one()
        old.status = "CANCELED"
        self.db.commit()
        barrier = Barrier(2)
        def reserve(order_id):
            with sessionmaker(self.engine, autoflush=False)() as db:
                order = db.execute(select(OrderLine).where(OrderLine.order_line_id == order_id).with_for_update()).scalar_one()
                barrier.wait(timeout=10)
                try:
                    add_stock_shipment_lines_by_inventory_lot(db, order_line=order, ship_qty=60, memo="concurrent")
                    db.commit()
                    return "OK"
                except HTTPException as error:
                    db.rollback()
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(reserve, (1, 2)))
        self.assertCountEqual(["OK", 409], outcomes)
        self.assertEqual(60, self.db.execute(select(func.sum(ShipmentLine.ship_qty)).where(
            ShipmentLine.status == "WAITING")).scalar_one())

    def test_postgres_migration_upgrade_downgrade_and_history_guard(self):
        if not self.pg_url:
            self.skipTest("requires dedicated PostgreSQL instance")
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from alembic.autogenerate import compare_metadata
        migration_path = Path(__file__).resolve().parents[1] / "migrations/versions/5a6b7c8d9e0f_preserve_inspection_settlement_ownership.py"
        spec = importlib.util.spec_from_file_location("inspection_schema_migration", migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with self.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
                migration.upgrade()
            differences = compare_metadata(MigrationContext.configure(conn), Base.metadata)
            self.assertEqual([], differences)
        self._save()
        self.db.commit()
        with self.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                with self.assertRaises(RuntimeError):
                    migration.downgrade()

    def test_failure_after_inventory_write_rolls_back_entire_settlement(self):
        with patch("app.services.inspection_result_service.sync_lot_status_from_inspection_schedules",
                   side_effect=RuntimeError("injected downstream failure")):
            with self.assertRaises(RuntimeError):
                self._save()
        self.db.rollback()
        self.assertIsNone(self.db.execute(select(InspectionResult)).scalar_one_or_none())
        self.assertEqual([], self.db.execute(select(ProductInventoryMovement)).scalars().all())
        self.assertEqual([], self.db.execute(select(ShipmentLine)).scalars().all())
        self.assertEqual("IN_PROGRESS", self.db.get(InspectionSchedule, 1).status)

    def _business_snapshot(self):
        names = ("order_line", "lot", "inspection_schedule", "inspection_result", "inspection_result_revision",
            "product_inventory", "product_inventory_lot", "product_inventory_movement", "shipment_line")
        return {name: self.db.execute(select(Base.metadata.tables[name]).order_by(
            *Base.metadata.tables[name].primary_key.columns)).all() for name in names}

    def test_failure_inside_posting_restores_all_business_rows_and_reservations(self):
        from app.services.inspection_inventory_service import _post_inventory_movements
        self._stock(65, own=40)
        before = self._business_snapshot()
        def post_then_fail(*args, **kwargs):
            _post_inventory_movements(*args, **kwargs)
            raise RuntimeError("injected after ledger flush")
        with patch("app.services.inspection_inventory_service._post_inventory_movements", side_effect=post_then_fail):
            with self.assertRaises(RuntimeError):
                self._save(stock_ship_qty=20)
        self.db.rollback()
        self.assertEqual(before, self._business_snapshot())

    def test_identical_repeat_does_not_recreate_movements_allocations_or_history(self):
        self._stock(65, own=40)
        self._save(stock_ship_qty=20)
        self.db.commit()
        before = self._business_snapshot()
        self._save(stock_ship_qty=20)
        self.db.commit()
        self.assertEqual(before, self._business_snapshot())

    def test_duplicate_split_request_cannot_create_another_round(self):
        self._save(is_partial=True, next_inspection_date=date(2026, 7, 11), partial_reason="remaining")
        self.db.commit()
        before = self._business_snapshot()
        with self.assertRaises(HTTPException) as caught:
            self._save(is_partial=True, next_inspection_date=date(2026, 7, 11), partial_reason="remaining")
        self.assertEqual(409, caught.exception.status_code)
        self.db.rollback()
        self.assertEqual(before, self._business_snapshot())

    def test_short_close_migration_constraints_backfill_and_history_guard(self):
        if not self.pg_url:
            self.skipTest("requires dedicated PostgreSQL instance")
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from alembic.autogenerate import compare_metadata
        from sqlalchemy.exc import IntegrityError
        from tests.test_short_close_migration import load_migration
        migration = load_migration()
        order = self.db.get(OrderLine, 1)
        order.status = "DONE"
        order.memo = "[SHORT_CLOSE] legacy decision"
        self.db.commit()
        with self.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
                migration.upgrade()
            self.assertEqual("REVIEW_REQUIRED", conn.execute(text("SELECT short_close_state FROM order_line WHERE order_line_id=1")).scalar_one())
            self.assertEqual("[SHORT_CLOSE] legacy decision", conn.execute(text("SELECT memo FROM order_line WHERE order_line_id=1")).scalar_one())
            self.assertEqual([], compare_metadata(MigrationContext.configure(conn), Base.metadata))
            with self.assertRaises(IntegrityError):
                with conn.begin_nested():
                    conn.execute(text("UPDATE order_line SET short_close_state='INVALID' WHERE order_line_id=1"))
        self.db.expire_all()
        order = self.db.get(OrderLine, 1)
        order.status = "CLOSED"
        order.short_close_state = "NONE"
        self.db.commit()
        short_close_order_line_status(self.db, 1, OrderLineShortCloseRequest(memo="accepted"), actor="tester")
        self.db.commit()
        with self.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                with self.assertRaises(RuntimeError):
                    migration.downgrade()


if __name__ == "__main__":
    unittest.main()
