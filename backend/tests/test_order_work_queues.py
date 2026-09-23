"""Queue membership and completion operate on real settlement records and stock movements."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import importlib.util
import os
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, literal, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.time import utc_now
from app.db.base import Base
from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.order_line_change_log import OrderLineChangeLog
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.partner import Partner
from app.models.process import Process
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.routing_template_step import RoutingTemplateStep
from app.models.shipment_line import ShipmentLine
from app.schemas.lot import LotCreate
from app.schemas.order_line import OrderLinePlanConfirmRequest, OrderLineShortCloseRequest
from app.services.inspection_result_service import upsert_inspection_result
from app.services.lot_rework_service import create_rework_lot
from app.services.order_line_base_lot_service import create_base_lot_from_plan
from app.services.order_line_creation_service import create_order_line_with_policy
from app.services.order_line_list_query import list_order_lines_for_grid
from app.services.order_line_manual_close_service import manual_close_order_line, reopen_manual_order_line
from app.services.order_line_plan_service import confirm_order_line_plan_decision
from app.services.order_line_work_queue import get_work_queue_counts, is_close_decision_pending
from app.services.ship_qty_policy import calculate_ship_qty, ship_target_sql
from scripts.inspection_regression_gate import validate_test_url
from tests import test_order_line_services as fixtures
from tests import test_inspection_result_service as inspection_fixtures


class OrderWorkQueueTests(unittest.TestCase):
    _payload = fixtures.OrderLineServicesTests._payload

    def setUp(self):
        self.pg_url = os.environ.get("MES_INSPECTION_TEST_PG_URL")
        self.schema = None
        if self.pg_url:
            validate_test_url(self.pg_url)
            self.schema = "queue_test_" + uuid4().hex
            self.admin = create_engine(self.pg_url, isolation_level="AUTOCOMMIT")
            with self.admin.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public"))
                conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            self.engine = create_engine(self.pg_url, connect_args={"options": f"-csearch_path={self.schema},public"})
            self.addCleanup(self._cleanup_pg)
            Base.metadata.create_all(self.engine)
        else:
            self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
            names = set(fixtures.TEST_TABLE_NAMES + ["inspection_result_revision"])
            Base.metadata.create_all(self.engine, tables=[Base.metadata.tables[n] for n in names])
        self.db = sessionmaker(self.engine, autoflush=False)()
        # This fixture has no revision-cycle dependency and works with PostgreSQL FKs enabled.
        inspection_fixtures.InspectionResultServiceTests._seed_base_data(self)
        self.db.add(Process(process_id=1, process_code="CUT", process_name="Cut", process_type="INTERNAL", is_active=True))
        self.db.flush()
        self.db.add(RoutingTemplateStep(routing_template_id=1, process_id=1, step_seq=10, default_process_type="INTERNAL", is_active=True))
        # The fixture's initial order is reserved for settlement tests; use a direct target of 100.
        self.db.get(Partner, 1).name = "덴티움"
        self.db.commit()
        if self.pg_url:
            for name in ("order_line", "lot", "inspection_schedule"):
                key = name + "_id"
                self.db.execute(text(f"SELECT setval(pg_get_serial_sequence(:name, :key), MAX({key}), true) FROM {name}"), {"name": name, "key": key})
            self.db.commit()
        for module, names in (
            ("order_line_creation_service", ["refresh_order_line_snapshot"]),
            ("order_line_plan_service", ["refresh_order_line_snapshot", "refresh_order_line_snapshots_for_product"]),
            ("shipment_confirm_service", ["refresh_order_line_snapshot", "refresh_order_line_snapshots_for_product"]),
            ("inspection_result_service", ["refresh_order_line_snapshots_for_lots", "refresh_order_line_snapshots_for_product"]),
            ("lot_rework_service", ["refresh_order_line_snapshot"]),
        ):
            for name in names:
                p = patch(f"app.services.{module}.{name}", return_value=0)
                p.start()
                self.addCleanup(p.stop)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _cleanup_pg(self):
        with self.admin.connect() as conn:
            conn.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        self.admin.dispose()

    def _stock(self, qty):
        self.db.add(ProductInventory(product_id=1, current_qty=qty))
        self.db.add(ProductInventoryLot(product_id=1, lot_no="OLD-STOCK", current_qty=qty))
        self.db.commit()

    def _final(self, **changes):
        values = dict(good_qty=80, defect_ship_qty=0, defect_qty=0, uninspected_qty=0,
            stock_ship_qty=0, result_ship_qty=80, stock_in_qty=0, discard_qty=0,
            is_partial=False, next_inspection_date=None, partial_reason=None, memo=None,
            defects=[], actor="tester")
        values.update(changes)
        result = upsert_inspection_result(self.db, 1, **values)[0]
        self.db.commit()
        return result

    def _close(self, order_id=1, db=None, **expected):
        return manual_close_order_line(db or self.db, order_id, OrderLineShortCloseRequest(**expected), actor="operator")

    def _rework(self, db=None):
        return create_rework_lot(db or self.db, LotCreate(order_line_id=1, parent_lot_id=1,
            lot_qty=20, created_date=date(2026, 9, 22)), actor="operator")

    def test_stock_origin_queue_survives_stock_depletion_and_plan_confirmation(self):
        self._stock(20)
        order = create_order_line_with_policy(self.db, self._payload("DEFERRED", 100))
        self.db.commit()
        self.assertTrue(order.lot_creation_deferred)
        self.db.execute(text("UPDATE product_inventory SET current_qty = 0"))
        self.db.execute(text("UPDATE product_inventory_lot SET current_qty = 0"))
        self.db.commit()
        rows, total, _ = list_order_lines_for_grid(self.db, page=1, size=1, work_queue="LOT_CREATION")
        self.assertEqual(1, total)
        self.assertEqual(["AUTO_PRODUCTION"], rows[0]["allowed_plan_types"])
        confirm_order_line_plan_decision(self.db, order_line_id=order.order_line_id,
            payload=OrderLinePlanConfirmRequest(plan_type="AUTO_PRODUCTION"))
        self.db.commit()
        self.assertEqual(1, get_work_queue_counts(self.db)["lot_creation"])
        create_base_lot_from_plan(self.db, order.order_line_id)
        self.db.commit()
        self.assertEqual(0, get_work_queue_counts(self.db)["lot_creation"])

    def test_global_counts_and_pagination_use_same_membership(self):
        self._stock(20)
        ids = [create_order_line_with_policy(self.db, self._payload(f"DEFER-{i}", 100)).order_line_id for i in range(3)]
        self.db.commit()
        page1, total, _ = list_order_lines_for_grid(self.db, page=1, size=2, work_queue="LOT_CREATION")
        page2, total2, _ = list_order_lines_for_grid(self.db, page=2, size=2, work_queue="LOT_CREATION")
        self.assertEqual((3, 3), (total, total2))
        self.assertEqual(set(ids), {x["order_line_id"] for x in page1 + page2})
        self.assertEqual(3, get_work_queue_counts(self.db)["lot_creation"])
        none, total, _ = list_order_lines_for_grid(self.db, page=1, size=20, q="NO-MATCH", work_queue="LOT_CREATION")
        self.assertEqual(([], 0), (none, total))
        self.assertEqual(3, get_work_queue_counts(self.db)["lot_creation"])

    def test_list_counts_remain_global_when_search_or_page_has_no_rows(self):
        self._stock(20)
        for i in range(3):
            create_order_line_with_policy(self.db, self._payload(f"GLOBAL-{i}", 100))
        self._final()
        self.db.commit()
        for queue, search, page, expected_total, expected_rows in (
            ("LOT_CREATION", "GLOBAL-1", 1, 1, 1),
            ("LOT_CREATION", "NO-MATCH", 1, 0, 0),
            ("LOT_CREATION", None, 99, 3, 0),
            ("CLOSE_DECISION", None, 1, 1, 1),
            ("CLOSE_DECISION", None, 99, 1, 0),
        ):
            with self.subTest(queue=queue, search=search, page=page):
                rows, total, counts = list_order_lines_for_grid(self.db, page=page, size=1,
                    status_group="IN_PROGRESS", work_queue=queue, q=search)
                self.assertEqual((expected_total, expected_rows), (total, len(rows)))
                self.assertEqual({"lot_creation": 3, "close_decision": 1}, counts)
                self.assertTrue(all(row["work_queue"] == queue for row in rows))
                if queue == "CLOSE_DECISION" and rows:
                    self.assertEqual((100, 80, 20, True), (rows[0]["ship_target_qty"],
                        rows[0]["already_shipped_qty"], rows[0]["remaining_ship_qty"], rows[0]["needs_shortage_action"]))

    def test_completed_list_skips_queue_evaluation_and_refreshes_on_return(self):
        self._final()
        self._close()
        self.db.commit()
        statements = []
        def capture(conn, cursor, statement, parameters, context, many):
            statements.append(statement)
        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            rows, total, counts = list_order_lines_for_grid(self.db, page=1, size=20, status_group="COMPLETED")
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(1, total)
        self.assertIsNone(counts)
        self.assertEqual((True, None, 80, 20), (rows[0]["manual_closed"], rows[0]["work_queue"],
            rows[0]["already_shipped_qty"], rows[0]["remaining_ship_qty"]))
        self.assertFalse(any("inspection_result" in statement or "order_work_queues" in statement for statement in statements))
        reopen_manual_order_line(self.db, 1, OrderLineShortCloseRequest(), actor="operator")
        self.db.commit()
        rows, total, counts = list_order_lines_for_grid(self.db, page=1, size=20, status_group="IN_PROGRESS")
        self.assertEqual(1, counts["close_decision"])
        self.assertEqual("CLOSE_DECISION", rows[0]["work_queue"])
        rows, total, counts = list_order_lines_for_grid(self.db, page=1, size=20, status_group="COMPLETED")
        self.assertEqual(([], 0, None), (rows, total, counts))

    def test_empty_queue_counts_are_zero_and_inactive_rows_do_not_change_global_counts(self):
        rows, total, counts = list_order_lines_for_grid(self.db, page=1, size=20, work_queue="CLOSE_DECISION")
        self.assertEqual(([], 0, {"lot_creation": 0, "close_decision": 0}), (rows, total, counts))
        self._stock(20)
        order = create_order_line_with_policy(self.db, self._payload("INACTIVE", 100))
        order.is_active = False
        self.db.commit()
        rows, total, counts = list_order_lines_for_grid(self.db, page=1, size=20, is_active=False)
        self.assertEqual(1, total)
        self.assertIsNone(rows[0]["work_queue"])
        self.assertEqual({"lot_creation": 0, "close_decision": 0}, counts)

    def test_confirmed_plan_display_does_not_recalculate_from_changing_available_stock(self):
        self._stock(20)
        order = create_order_line_with_policy(self.db, self._payload("PLAN-SNAPSHOT", 100))
        confirm_order_line_plan_decision(self.db, order_line_id=order.order_line_id,
            payload=OrderLinePlanConfirmRequest(plan_type="PARTIAL_STOCK_PLUS_PRODUCTION"))
        self.db.commit()
        rows, _, _ = list_order_lines_for_grid(self.db, page=1, size=20, work_queue="LOT_CREATION")
        self.assertEqual(0, rows[0]["available_inventory_qty"])
        self.assertEqual((20, 80), (rows[0]["planned_stock_ship_qty"], rows[0]["planned_production_qty"]))

    def test_api_contract_counts_auth_snapshot_conflict_and_legacy_guard(self):
        import asyncio
        import json
        from types import SimpleNamespace
        from fastapi import FastAPI
        from app.api.v1.order_lines import router
        from app.core.auth import get_current_user
        from app.db.session import get_db
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db

        async def request(path, method="GET", query="", payload=None):
            messages = []
            async def receive():
                return {"type": "http.request", "body": json.dumps(payload).encode() if payload is not None else b"", "more_body": False}
            async def send(message):
                messages.append(message)
            await app({"type": "http", "http_version": "1.1", "method": method, "scheme": "http",
                "path": path, "root_path": "", "query_string": query.encode(),
                "headers": [(b"content-type", b"application/json")], "server": ("test", 80), "client": ("test", 123)}, receive, send)
            status = next(x["status"] for x in messages if x["type"] == "http.response.start")
            body = json.loads(b"".join(x.get("body", b"") for x in messages if x["type"] == "http.response.body"))
            return status, body

        self.assertIn(asyncio.run(request("/order-lines/1/manual-close", "PATCH", payload={}))[0], (401, 403))
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(login_id="operator")
        self.assertEqual(409, asyncio.run(request("/order-lines/1/short-close", "PATCH", payload={}))[0])
        self._final()
        status, body = asyncio.run(request("/order-lines", query="work_queue=CLOSE_DECISION&size=1"))
        self.assertEqual(200, status)
        self.assertEqual(1, body["queue_counts"]["close_decision"])
        row = body["items"][0]
        self.assertEqual("CLOSE_DECISION", row["work_queue"])
        self.assertEqual(422, asyncio.run(request("/order-lines", query="work_queue=INVALID"))[0])
        self.assertEqual(409, asyncio.run(request("/order-lines/1/manual-close", "PATCH", payload={"expected_shipped_qty": 0}))[0])
        status, body = asyncio.run(request("/order-lines/1/manual-close", "PATCH", payload={
            "expected_updated_at": row["updated_at"], "expected_ship_target_qty": 100, "expected_shipped_qty": 80}))
        self.assertEqual(200, status, body)
        self.assertTrue(body["manual_closed"])
        status, body = asyncio.run(request("/order-lines", query="status_group=COMPLETED"))
        self.assertEqual(200, status)
        self.assertIsNone(body["queue_counts"])
        self.assertEqual(1, body["meta"]["total"])
        self.assertEqual(200, asyncio.run(request("/order-lines/1/manual-reopen", "PATCH", payload={}))[0])

    def test_stock_shipment_completion_leaves_lot_queue(self):
        self._stock(200)
        order = create_order_line_with_policy(self.db, self._payload("STOCK-CLOSE", 100))
        confirm_order_line_plan_decision(self.db, order_line_id=order.order_line_id,
            payload=OrderLinePlanConfirmRequest(plan_type="STOCK_SHIP_COMPLETE"))
        self.db.commit()
        self.assertEqual("DONE", order.status)
        self.assertFalse(order.manual_closed)
        self.assertEqual(0, get_work_queue_counts(self.db)["lot_creation"])

    def test_uninspected_all_zero_shipment_can_close_without_reason_and_reopen(self):
        self._final(good_qty=0, uninspected_qty=80, result_ship_qty=0)
        self.assertTrue(is_close_decision_pending(self.db, 1))
        self._close(expected_ship_target_qty=100, expected_shipped_qty=0)
        self.db.commit()
        order = self.db.get(OrderLine, 1)
        self.assertEqual(("DONE", True, "CONFIRMED"), (order.status, order.manual_closed, order.short_close_state))
        self.assertEqual(0, get_work_queue_counts(self.db)["close_decision"])
        self._close()  # A retry cannot add another history or stock action.
        self.db.commit()
        log = self.db.execute(select(OrderLineChangeLog)).scalar_one()
        self.assertEqual("operator", log.created_by)
        self.assertIsNone(log.reason)
        self.assertEqual(100, log.after_data["remaining_ship_qty"])
        reopen_manual_order_line(self.db, 1, OrderLineShortCloseRequest(), actor="operator")
        self.db.commit()
        self.assertTrue(is_close_decision_pending(self.db, 1))
        self.assertFalse(order.manual_closed)
        self.assertEqual(0, self.db.scalar(select(func.count()).select_from(ProductInventoryMovement)))

    def test_close_releases_only_own_unused_reservation_without_stock_movement(self):
        self._stock(100)
        self._final(result_ship_qty=50, stock_in_qty=30)
        lot = self.db.execute(select(ProductInventoryLot).where(ProductInventoryLot.lot_no == "OLD-STOCK")).scalar_one()
        other = create_order_line_with_policy(self.db, self._payload("OTHER", 100))
        own_line = ShipmentLine(order_line_id=1, product_id=1, product_inventory_lot_id=lot.product_inventory_lot_id,
            source_type="STOCK", status="WAITING", ship_qty=10, shipped_qty=0)
        other_line = ShipmentLine(order_line_id=other.order_line_id, product_id=1, product_inventory_lot_id=lot.product_inventory_lot_id,
            source_type="STOCK", status="WAITING", ship_qty=15, shipped_qty=0)
        self.db.add_all([own_line, other_line])
        self.db.commit()
        stock = self.db.scalar(select(ProductInventory.current_qty))
        movements = self.db.scalar(select(func.count()).select_from(ProductInventoryMovement))
        self._close()
        self.db.commit()
        self.assertEqual(("CANCELED", "WAITING"), (own_line.status, other_line.status))
        reopen_manual_order_line(self.db, 1, OrderLineShortCloseRequest(), actor="operator")
        self.db.commit()
        self.assertEqual("CANCELED", own_line.status)
        self.assertEqual(stock, self.db.scalar(select(ProductInventory.current_qty)))
        self.assertEqual(movements, self.db.scalar(select(func.count()).select_from(ProductInventoryMovement)))

    def test_partial_or_unsettled_or_running_work_cannot_close(self):
        with self.assertRaises(HTTPException):
            self._close()
        result = self._final(good_qty=20, result_ship_qty=20, is_partial=True,
            next_inspection_date=date(2026, 7, 11), partial_reason="remaining")
        self.assertFalse(is_close_decision_pending(self.db, 1))
        with self.assertRaises(HTTPException):
            self._close()
        # A status label alone does not prove final settlement.
        self.db.get(Lot, 1).status = "DONE"
        self.db.get(InspectionSchedule, 1).status = "DONE"
        result.is_partial = False
        result.settled_at = None
        result.settled_by = None
        result.settlement_owner_id = None
        result.settled_sellable_qty = None
        self.db.commit()
        self.assertFalse(is_close_decision_pending(self.db, 1))

    def test_rework_reopens_manual_decision_and_returns_to_queue_after_final(self):
        self._final()
        self._close()
        self.db.commit()
        rework = self._rework()
        self.db.commit()
        order = self.db.get(OrderLine, 1)
        self.assertEqual(("CLOSED", False, "NONE"), (order.status, order.manual_closed, order.short_close_state))
        self.assertFalse(is_close_decision_pending(self.db, 1))
        with self.assertRaises(HTTPException):
            self._close()
        schedule = InspectionSchedule(lot_id=rework.lot_id, inspection_date=date(2026, 9, 23), status="DONE")
        self.db.add(schedule)
        self.db.flush()
        self.db.add(InspectionResult(inspection_schedule_id=schedule.inspection_schedule_id, good_qty=0,
            defect_qty=0, inspected_qty=0, uninspected_qty=20, is_partial=False, settled_at=utc_now(), settled_by="operator"))
        self.db.get(Lot, rework.lot_id).status = "DONE"
        self.db.commit()
        self.assertTrue(is_close_decision_pending(self.db, 1))
        logs = self.db.execute(select(OrderLineChangeLog).order_by(OrderLineChangeLog.order_line_change_log_id)).scalars().all()
        self.assertEqual(["MANUAL_CLOSE", "REWORK_REOPEN"], [x.after_data["action"] for x in logs])

    def test_stale_quantity_and_time_are_rejected_without_changes(self):
        self._final()
        for expected in ({"expected_shipped_qty": 0}, {"expected_ship_target_qty": 101},
                         {"expected_updated_at": utc_now() - timedelta(days=1)}):
            with self.subTest(expected=expected), self.assertRaises(HTTPException) as raised:
                self._close(**expected)
            self.assertEqual(409, raised.exception.status_code)
        self.assertFalse(self.db.get(OrderLine, 1).manual_closed)
        self.assertEqual(0, self.db.scalar(select(func.count()).select_from(OrderLineChangeLog)))

    def test_lot_plan_is_not_completion_target_and_over_target_still_saves(self):
        self.db.get(Lot, 1).lot_qty = 1000
        self.db.commit()
        self._final(good_qty=120, result_ship_qty=120)
        self.assertEqual("DONE", self.db.get(OrderLine, 1).status)
        self.assertFalse(is_close_decision_pending(self.db, 1))
        self.assertEqual(0, get_work_queue_counts(self.db)["close_decision"])

    def test_stock_only_production_has_no_shipping_shortage_queue(self):
        self.db.get(OrderLine, 1).decision_made = True
        self.db.add(OrderLinePlanHistory(order_line_id=1, plan_type="STOCK_REPLENISHMENT", ship_target_qty=100,
            stock_ship_qty=0, production_qty=100))
        self.db.commit()
        self._final(result_ship_qty=0, stock_in_qty=80)
        self.assertEqual("DONE", self.db.get(OrderLine, 1).status)
        self.assertFalse(is_close_decision_pending(self.db, 1))

    def test_all_canceled_and_no_final_do_not_enter_queue(self):
        self.db.get(Lot, 1).status = "CANCELED"
        self.db.commit()
        self.assertFalse(is_close_decision_pending(self.db, 1))
        self.db.get(Lot, 1).status = "DONE"
        self.db.commit()
        self.assertFalse(is_close_decision_pending(self.db, 1))

    def test_sql_target_matches_existing_quantity_policy(self):
        for partner in ("Customer", "덴 티 움", "(주)케어젠", "주식회사 오스템임플란트", "㈜제이시스메디칼", "네오\u3000바이오텍"):
            for qty in (1, 49, 50, 100, 1050, 999999):
                with self.subTest(partner=partner, qty=qty):
                    actual = self.db.scalar(select(ship_target_sql(literal(partner), literal(qty))))
                    self.assertEqual(calculate_ship_qty(partner, qty), actual)

    def test_concurrent_close_and_rework_cannot_leave_done_with_active_lot(self):
        if not self.pg_url:
            self.skipTest("Requires dedicated PostgreSQL")
        self._final()
        barrier = Barrier(2)
        def run(action):
            with sessionmaker(self.engine, autoflush=False)() as db:
                barrier.wait(timeout=10)
                try:
                    action(db)
                    db.commit()
                    return "ok"
                except HTTPException:
                    db.rollback()
                    return "conflict"
        with ThreadPoolExecutor(2) as pool:
            close = pool.submit(run, lambda db: self._close(db=db))
            rework = pool.submit(run, lambda db: self._rework(db=db))
            self.assertIn(close.result(timeout=15), ("ok", "conflict"))
            self.assertEqual("ok", rework.result(timeout=15))
        self.db.expire_all()
        order = self.db.get(OrderLine, 1)
        self.assertEqual(("CLOSED", False, "NONE"), (order.status, order.manual_closed, order.short_close_state))
        self.assertFalse(is_close_decision_pending(self.db, 1))

    def test_queue_migration_backfill_constraints_and_history_guard(self):
        if not self.pg_url:
            self.skipTest("Requires dedicated PostgreSQL")
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from alembic.autogenerate import compare_metadata
        from sqlalchemy.exc import IntegrityError
        path = Path(__file__).resolve().parents[1] / "migrations/versions/7c8d9e0f1a2b_order_work_queues.py"
        spec = importlib.util.spec_from_file_location("queue_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self._stock(50)
        order = create_order_line_with_policy(self.db, self._payload("OLD-DEFERRED", 100))
        self.db.commit()
        order_id = order.order_line_id
        self.db.rollback()  # Release the ORM refresh read before taking the migration table lock.
        with self.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
                migration.upgrade()
            flags = conn.execute(text("SELECT lot_creation_deferred, manual_closed, order_qty FROM order_line WHERE order_line_id=:id"), {"id": order_id}).one()
            self.assertEqual((True, False, 100), tuple(flags))
            self.assertEqual([], compare_metadata(MigrationContext.configure(conn), Base.metadata))
            with self.assertRaises(IntegrityError), conn.begin_nested():
                conn.execute(text("UPDATE order_line SET manual_closed = true WHERE order_line_id=1"))
        self.db.expire_all()
        self._final()
        self._close()
        self.db.commit()
        reopen_manual_order_line(self.db, 1, OrderLineShortCloseRequest(), actor="operator")
        self.db.commit()
        with self.engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            with self.assertRaises(RuntimeError):
                migration.downgrade()
