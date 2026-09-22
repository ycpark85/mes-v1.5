"""Saved inspection views must retain the LOT balances at their own posting boundary."""
from datetime import date, datetime, timedelta
import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy import select
from fastapi import FastAPI

from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.services.inspection_result_query import get_inspection_result_detail
from app.schemas.inspection_result import InspectionResultGetOut
from tests import test_inspection_corrections as fixtures


class SavedInventoryTests(unittest.TestCase):
    setUp = fixtures.InspectionCorrectionsTests.setUp
    tearDown = fixtures.InspectionCorrectionsTests.tearDown
    _seed_base_data = fixtures.InspectionCorrectionsTests._seed_base_data
    _cleanup_pg = fixtures.InspectionCorrectionsTests._cleanup_pg
    _sync_sequences = fixtures.InspectionCorrectionsTests._sync_sequences
    _stock = fixtures.InspectionCorrectionsTests._stock
    _save = fixtures.InspectionCorrectionsTests._save

    def _first_round(self):
        self._stock(39500, own=39500)
        self.db.add(ProductInventoryMovement(product_id=1, product_inventory_lot_id=1,
            stock_lot_no="OLD", movement_type="INITIAL_STOCK", qty=39500, balance_after=39500,
            created_at=datetime(2026, 1, 1)))
        self.db.get(OrderLine, 1).order_qty = 300000
        self.db.get(OrderLine, 1).decision_made = True
        self.db.get(Lot, 1).lot_qty = 260500
        self.db.add(OrderLinePlanHistory(order_line_id=1, plan_type="PARTIAL_STOCK_PLUS_PRODUCTION",
            ship_target_qty=300000, stock_ship_qty=39500, production_qty=260500))
        self.db.commit()
        self._save(good_qty=100000, result_ship_qty=0, stock_in_qty=100000,
            is_partial=True, next_inspection_date=date(2026, 7, 11), partial_reason="next round")
        self.db.commit()

    def _second_round(self):
        schedule = self.db.execute(select(InspectionSchedule).where(
            InspectionSchedule.inspection_schedule_id != 1)).scalar_one()
        schedule.status = "IN_PROGRESS"
        self.db.commit()
        self._save(schedule_id=schedule.inspection_schedule_id, good_qty=300000,
            stock_ship_qty=139500, result_ship_qty=160500, stock_in_qty=139500)
        self.db.commit()
        return schedule.inspection_schedule_id

    def _view(self, schedule_id=1):
        return get_inspection_result_detail(self.db, schedule_id, view_mode="saved").inventory

    def test_first_round_keeps_two_lots_after_second_round_ships(self):
        self._first_round()
        before = self._view()
        second_id = self._second_round()
        after = self._view()
        self.assertEqual(before, after)
        self.assertEqual({"OLD": 39500, "LOT-A": 100000},
            {row.lot_no: row.physical_qty for row in after.stock_lots})
        self.assertEqual(139500, after.current_stock_qty)
        self.assertEqual(100000, after.current_result_stock_in_qty)
        self.assertEqual(0, after.prior_shipped_qty)
        self.assertEqual(0, after.already_shipped_qty)
        self.assertEqual(300000, after.remaining_ship_target_qty)
        second = self._view(second_id)
        self.assertEqual({"OLD": 0, "LOT-A": 139500},
            {row.lot_no: row.physical_qty for row in second.stock_lots})
        self.assertEqual(139500, second.current_result_stock_ship_qty)
        self.assertEqual(160500, second.current_result_result_ship_qty)
        self.assertEqual(139500, second.current_result_stock_in_qty)
        self.assertEqual(0, second.prior_shipped_qty)
        self.assertEqual(300000, second.already_shipped_qty)
        self.assertEqual(0, second.remaining_ship_target_qty)
        # Saving/editing still excludes only the current result from ALL current postings.
        edit = get_inspection_result_detail(self.db, 1).inventory
        self.assertEqual(39500, edit.current_stock_qty)
        self.assertEqual(300000, edit.prior_shipped_qty)
        self.assertEqual("edit", edit.view_mode)

    def test_later_adjustments_and_new_lots_do_not_change_saved_view(self):
        self._first_round()
        expected = self._view()
        self.db.get(ProductInventoryLot, 1).current_qty += 10
        self.db.execute(select(ProductInventory)).scalar_one().current_qty += 30
        self.db.add(ProductInventoryLot(product_inventory_lot_id=99, product_id=1,
            lot_no="LATER", current_qty=20))
        self.db.add_all([
            ProductInventoryMovement(product_id=1, product_inventory_lot_id=1, stock_lot_no="OLD",
                movement_type="ADJUST_IN", qty=10, balance_after=139510),
            ProductInventoryMovement(product_id=1, product_inventory_lot_id=99, stock_lot_no="LATER",
                movement_type="INITIAL_STOCK", qty=20, balance_after=139530),
        ])
        self.db.commit()
        self.assertEqual(expected, self._view())

    def test_quantity_correction_uses_latest_posting_but_memo_edit_does_not_move_boundary(self):
        self._first_round()
        second_id = self._second_round()
        self._save(schedule_id=second_id, good_qty=310000, stock_ship_qty=139500,
            result_ship_qty=160500, stock_in_qty=149500)
        self.db.commit()
        corrected = self._view(second_id)
        self.assertEqual(149500, corrected.current_stock_qty)
        self.assertEqual(149500, corrected.current_result_stock_in_qty)
        self._save(schedule_id=second_id, good_qty=310000, stock_ship_qty=139500,
            result_ship_qty=160500, stock_in_qty=149500, memo="metadata only")
        self.db.commit()
        self.assertEqual(corrected, self._view(second_id))
        self._save(schedule_id=second_id, good_qty=300000, stock_ship_qty=139500,
            result_ship_qty=150500, stock_in_qty=149500)
        self.db.commit()
        reduced = self._view(second_id)
        self.assertEqual(149500, reduced.current_stock_qty)
        self.assertEqual(290000, reduced.already_shipped_qty)
        self.assertEqual(10000, reduced.remaining_ship_target_qty)
        self.assertEqual(100000, next(row.physical_qty for row in self._view().stock_lots
            if row.lot_no == "LOT-A"))

    def test_posting_boundary_uses_ids_even_when_timestamps_are_equal(self):
        self._first_round()
        before = self._view()
        self._second_round()
        # PostgreSQL transaction timestamps need not reflect lock acquisition order.
        for movement in self.db.execute(select(ProductInventoryMovement).where(
            ProductInventoryMovement.inspection_schedule_id != 1)).scalars():
            movement.created_at = before.stock_as_of
        self.db.commit()
        self.assertEqual(before, self._view())

    def test_missing_inventory_history_is_reported_without_current_stock_fallback(self):
        self._first_round()
        self.db.get(ProductInventoryLot, 1).current_qty += 1
        self.db.execute(select(ProductInventory)).scalar_one().current_qty += 1
        self.db.commit()
        inventory = self._view()
        self.assertIsNotNone(inventory.stock_error)
        self.assertEqual([], inventory.stock_lots)
        self.assertEqual("saved", inventory.view_mode)

    def test_zero_inventory_result_uses_save_time_and_does_not_guess_timestamp_ties(self):
        result = self._save(good_qty=0, result_ship_qty=0, stock_in_qty=0,
            defect_qty=80, shortage_reason="actual quantity")
        self.db.commit()
        inventory = self._view()
        self.assertIsNone(inventory.stock_error)
        self.assertEqual([], inventory.stock_lots)
        self.db.execute(select(ProductInventory)).scalar_one().current_qty = 10
        lot = self.db.execute(select(ProductInventoryLot)).scalar_one_or_none()
        if lot is None:
            lot = ProductInventoryLot(product_id=1, lot_no="LATER", current_qty=10)
            self.db.add(lot)
            self.db.flush()
        else:
            lot.current_qty = 10
        movement = ProductInventoryMovement(product_id=1,
            product_inventory_lot_id=lot.product_inventory_lot_id, stock_lot_no=lot.lot_no,
            movement_type="INITIAL_STOCK", qty=10, balance_after=10,
            created_at=result.created_at + timedelta(days=1))
        self.db.add(movement)
        self.db.commit()
        self.assertEqual(inventory, self._view())
        movement.created_at = result.created_at
        self.db.commit()
        self.assertIsNotNone(self._view().stock_error)


def test_saved_view_api_contract_is_explicit_and_preserves_default_edit_mode():
    from app.api.v1 import inspection_results as endpoint
    app = FastAPI()
    app.include_router(endpoint.router)
    sentinel_db = object()
    app.dependency_overrides[endpoint.get_inspection_read_db] = lambda: sentinel_db
    app.dependency_overrides[endpoint.get_current_user] = lambda: object()
    async def request(query_string=b""):
        messages = []
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(message):
            messages.append(message)
        await app({"type": "http", "http_version": "1.1", "method": "GET",
            "scheme": "http", "path": "/inspection-schedules/1/result", "root_path": "",
            "query_string": query_string, "headers": [], "server": ("test", 80),
            "client": ("test", 123)}, receive, send)
        return next(message["status"] for message in messages if message["type"] == "http.response.start")
    with patch.object(endpoint, "get_inspection_result_detail", return_value=InspectionResultGetOut()) as query:
        assert asyncio.run(request()) == 200
        query.assert_called_with(sentinel_db, 1, view_mode="edit")
        assert asyncio.run(request(b"view_mode=saved")) == 200
        query.assert_called_with(sentinel_db, 1, view_mode="saved")
        assert asyncio.run(request(b"view_mode=invalid")) == 422
