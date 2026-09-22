"""Inventory tabs operate on the original stock LOT, including after split inspection."""
import asyncio
import json
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from sqlalchemy import event, select
from sqlalchemy.orm import sessionmaker

from app.api.v1 import inventories as endpoint
from app.models.product_inventory_lot import ProductInventoryLot
from app.schemas.inventory import ProductInventoryAdjustmentIn, ProductInventoryLotListOut, ProductInventoryMovementListOut
from app.services.product_inventory_adjustment_service import adjust_product_inventory_in_session
from app.services.product_inventory_query import list_product_inventory_lots, list_product_inventory_movements
from tests import test_inspection_saved_inventory as fixtures


class InventoryLotFlowTests(unittest.TestCase):
    setUp = fixtures.SavedInventoryTests.setUp
    tearDown = fixtures.SavedInventoryTests.tearDown
    _seed_base_data = fixtures.SavedInventoryTests._seed_base_data
    _cleanup_pg = fixtures.SavedInventoryTests._cleanup_pg
    _sync_sequences = fixtures.SavedInventoryTests._sync_sequences
    _stock = fixtures.SavedInventoryTests._stock
    _save = fixtures.SavedInventoryTests._save
    _first_round = fixtures.SavedInventoryTests._first_round
    _second_round = fixtures.SavedInventoryTests._second_round

    def test_inventory_history_and_stock_snapshot_share_repeatable_read(self):
        if not self.pg_url:
            self.skipTest("requires dedicated PostgreSQL instance")
        self._first_round()
        factory = sessionmaker(self.engine, autoflush=False)
        production_id = self.db.execute(select(ProductInventoryLot.product_inventory_lot_id).where(
            ProductInventoryLot.lot_no == "LOT-A")).scalar_one()
        changed = False

        def change_after_lot_read(conn, cursor, statement, parameters, context, executemany):
            nonlocal changed
            if not changed and "from product_inventory_lot" in statement.lower():
                changed = True
                with factory() as writer:
                    adjust_product_inventory_in_session(writer, product_id=1,
                        payload=ProductInventoryAdjustmentIn(qty=500, product_inventory_lot_id=production_id,
                            memo="concurrent snapshot test"), direction="OUT")
                    writer.commit()

        with patch("app.db.inspection_read.SessionLocal", factory):
            reader = endpoint.get_inventory_read_db()
            db = next(reader)
            connection = db.connection()
            event.listen(connection, "after_cursor_execute", change_after_lot_read)
            try:
                result = list_product_inventory_movements(db, product_inventory_lot_id=production_id,
                    stock_page=1, stock_include_zero=True)
                self.assertTrue(changed)
                self.assertEqual(100000, result.current_qty)
                self.assertEqual(100000, result.items[0].lot_balance_after)
                self.assertEqual(139500, result.stock_snapshot.product_current_qty)
                self.assertEqual(139500, result.stock_snapshot.total_qty)
                self.assertEqual({"OLD": 39500, "LOT-A": 100000},
                    {row.lot_no: row.current_qty for row in result.stock_snapshot.items})
                self.assertIsNone(result.history_warning)
                self.assertIsNone(result.stock_snapshot.stock_warning)
            finally:
                event.remove(connection, "after_cursor_execute", change_after_lot_read)
                reader.close()
            reader = endpoint.get_inventory_read_db()
            try:
                fresh = list_product_inventory_movements(next(reader), product_inventory_lot_id=production_id,
                    stock_page=1)
                self.assertEqual(99500, fresh.current_qty)
                self.assertEqual(99500, fresh.items[0].lot_balance_after)
                self.assertEqual(139000, fresh.stock_snapshot.product_current_qty)
                self.assertEqual(139000, fresh.stock_snapshot.total_qty)
            finally:
                reader.close()

    def test_split_inspection_stock_and_history_keep_original_lot_identity(self):
        self._first_round()
        first = list_product_inventory_lots(self.db, product_id=1, include_zero=True)
        self.assertEqual({"OLD": 39500, "LOT-A": 100000}, {x.lot_no: x.current_qty for x in first.items})
        self._second_round()
        current = list_product_inventory_lots(self.db, product_id=1, include_zero=True)
        self.assertEqual({"OLD": 0, "LOT-A": 139500}, {x.lot_no: x.current_qty for x in current.items})
        self.assertEqual(139500, current.product_current_qty)
        self.assertIsNone(current.stock_warning)
        old = next(x for x in current.items if x.lot_no == "OLD")
        history = list_product_inventory_movements(self.db, product_id=1,
            product_inventory_lot_id=old.product_inventory_lot_id, size=1)
        self.assertEqual((0, -39500), (history.items[0].lot_balance_after, history.items[0].qty))
        self.assertEqual(0, history.current_qty)
        self.assertIsNone(history.history_warning)
        first_page_balance = list_product_inventory_movements(self.db, product_id=1,
            product_inventory_lot_id=old.product_inventory_lot_id, size=1, page=2).items[0].lot_balance_after
        self.assertEqual(39500, first_page_balance)
        production = next(x for x in current.items if x.lot_no == "LOT-A")
        rows = list_product_inventory_movements(self.db, product_id=1,
            product_inventory_lot_id=production.product_inventory_lot_id)
        self.assertEqual(139500, rows.current_qty)
        self.assertEqual(139500, rows.items[0].lot_balance_after)
        self.assertEqual(100000, rows.items[-1].lot_balance_after)
        self.assertIsNone(rows.history_warning)

    def test_selected_lot_adjustment_preserves_reserved_stock_and_other_lot(self):
        self._first_round()
        production = self.db.execute(select(ProductInventoryLot).where(ProductInventoryLot.lot_no == "LOT-A")).scalar_one()
        with self.assertRaises(HTTPException) as blocked:
            adjust_product_inventory_in_session(self.db, product_id=1,
                payload=ProductInventoryAdjustmentIn(qty=1, product_inventory_lot_id=1, memo="count"),
                direction="OUT")
        self.assertEqual(409, blocked.exception.status_code)
        self.db.rollback()
        result = adjust_product_inventory_in_session(self.db, product_id=1,
            payload=ProductInventoryAdjustmentIn(qty=500, product_inventory_lot_id=production.product_inventory_lot_id, memo="count"),
            direction="OUT")
        self.db.commit()
        self.assertEqual(production.product_inventory_lot_id, result.movement.product_inventory_lot_id)
        self.assertEqual(39500, self.db.get(ProductInventoryLot, 1).current_qty)
        history = list_product_inventory_movements(self.db, product_inventory_lot_id=production.product_inventory_lot_id)
        self.assertEqual((99500, 139000), (history.items[0].lot_balance_after, history.items[0].balance_after))
        self.assertIsNone(history.history_warning)

    def test_korean_date_filter_keeps_balance_from_prior_postings(self):
        self._first_round()
        production = self.db.execute(select(ProductInventoryLot).where(ProductInventoryLot.lot_no == "LOT-A")).scalar_one()
        adjusted = adjust_product_inventory_in_session(self.db, product_id=1,
            payload=ProductInventoryAdjustmentIn(qty=500, product_inventory_lot_id=production.product_inventory_lot_id, memo="count"),
            direction="IN")
        adjusted.movement.created_at = datetime(2026, 9, 13, 15, 0, tzinfo=timezone.utc)
        self.db.commit()
        included = list_product_inventory_movements(self.db, product_inventory_lot_id=production.product_inventory_lot_id,
            movement_type="ADJUST_IN", date_from=date(2026, 9, 14), date_to=date(2026, 9, 14))
        self.assertEqual(1, included.total)
        self.assertEqual(100500, included.items[0].lot_balance_after)
        excluded = list_product_inventory_movements(self.db, product_inventory_lot_id=production.product_inventory_lot_id,
            movement_type="ADJUST_IN", date_from=date(2026, 9, 13), date_to=date(2026, 9, 13))
        self.assertEqual(0, excluded.total)


def test_inventory_route_validation_and_explicit_lot_adjustment_contract():
    app = FastAPI()
    app.include_router(endpoint.router)
    sentinel = object()
    app.dependency_overrides[endpoint.get_db] = lambda: sentinel
    app.dependency_overrides[endpoint.get_inventory_read_db] = lambda: sentinel

    async def request(path, method="GET", query="", payload=None):
        messages = []
        async def receive():
            return {"type": "http.request", "body": json.dumps(payload).encode() if payload is not None else b"", "more_body": False}
        async def send(message):
            messages.append(message)
        await app({"type": "http", "http_version": "1.1", "method": method, "scheme": "http",
            "path": path, "root_path": "", "query_string": query.encode(), "headers": [(b"content-type", b"application/json")],
            "server": ("test", 80), "client": ("test", 123)}, receive, send)
        return next(x["status"] for x in messages if x["type"] == "http.response.start")

    with patch.object(endpoint, "list_product_inventory_lots", return_value=ProductInventoryLotListOut(
        items=[], product_id=1, product_current_qty=0, total_qty=0, total=0, page=1, size=50)) as query:
        assert asyncio.run(request("/inventories/1/lots", query="include_zero=true&size=50")) == 200
        query.assert_called_once_with(sentinel, product_id=1, q=None, include_zero=True, page=1, size=50)
        assert asyncio.run(request("/inventories/0/lots")) == 422
        assert asyncio.run(request("/inventories/1/lots", query="size=201")) == 422
    with patch.object(endpoint, "list_product_inventory_movements", return_value=ProductInventoryMovementListOut(
        items=[], total=0, page=1, size=50)) as query:
        assert asyncio.run(request("/inventories/movements", query=
            "product_inventory_lot_id=12&stock_page=2&stock_size=50&stock_q=CT26&stock_include_zero=true")) == 200
        query.assert_called_once_with(sentinel, product_id=None, product_inventory_lot_id=12,
            movement_type=None, date_from=None, date_to=None, page=1, size=100,
            stock_page=2, stock_size=50, stock_q="CT26", stock_include_zero=True)
        query.reset_mock()
        for invalid in ("stock_page=0", "stock_size=0", "stock_size=201"):
            assert asyncio.run(request("/inventories/movements", query=invalid)) == 422
        query.assert_not_called()
    with patch.object(endpoint, "adjust_product_inventory_in_session") as adjust:
        for route in ("/inventories/1/adjust", "/inventories/1/lots/12/adjust"):
            for direction in ("IN", "OUT"):
                for payload in ({"qty": 1}, {"qty": 1, "memo": None}, {"qty": 1, "memo": " "},
                                {"qty": 1, "memo": "x" * 1001}):
                    assert asyncio.run(request(route, "POST", f"direction={direction}", payload)) == 422
        adjust.assert_not_called()
    with patch.object(endpoint, "adjust_inventory", return_value=dict(inventory_movement_id=1,
        product_id=1, product_inventory_lot_id=12, movement_type="ADJUST_OUT", qty=-5,
        balance_after=100, created_at=datetime.now(timezone.utc))) as adjust:
        assert asyncio.run(request("/inventories/1/lots/12/adjust", "POST", "direction=OUT",
            {"qty": 5, "memo": " count "})) == 201
        args = adjust.call_args.args
        assert args[0] == 1 and args[1].product_inventory_lot_id == 12 and args[1].memo == "count"
        adjust.reset_mock()
        for lot, payload in [("0", {"qty": 5, "memo": "count"}), ("12", {"qty": 0, "memo": "count"}),
                             ("12", {"qty": 5, "memo": " "}), ("12", {"qty": 5})]:
            assert asyncio.run(request(f"/inventories/1/lots/{lot}/adjust", "POST", "direction=OUT", payload)) == 422
        adjust.assert_not_called()
