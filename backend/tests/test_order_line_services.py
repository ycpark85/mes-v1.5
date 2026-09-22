from __future__ import annotations

import unittest
from datetime import date, datetime
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import BigInteger, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

import app.models  # noqa: F401
from app.db.base import Base
from app.models.drawing import Drawing
from app.models.drawing_revision import DrawingRevision
from app.models.drawing_rivision_file import DrawingRevisionFile
from app.models.lot import Lot
from app.models.lot_step import LotStep
from app.models.order_line import OrderLine
from app.models.order_line_change_log import OrderLineChangeLog
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_change_log import OutsourceWorkGroupChangeLog
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction import OutsourceWorkInstruction
from app.models.outsource_work_instruction_item import OutsourceWorkInstructionItem
from app.models.partner import Partner
from app.models.process import Process
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.routing_template import RoutingTemplate
from app.models.routing_template_step import RoutingTemplateStep
from app.models.shipment_line import ShipmentLine
from app.schemas.order_line import (
    OrderLineBulkCommitRequest,
    OrderLineBulkCommitRowChoice,
    OrderLineBulkImportRowIn,
    OrderLineCreate,
    OrderLinePlanConfirmRequest,
    OrderLineShortCloseRequest,
    OrderLineUpdate,
)
from app.schemas.order_line_detail import OrderLineDetailUpdate
from app.services.order_line_cancel_service import cancel_order_line_status
from app.services.order_line_base_lot_service import create_base_lot_from_plan
from app.services.order_line_creation_service import (
    create_order_line_with_policy,
    create_primary_lot_for_order_line,
)
from app.services.order_line_delete_service import delete_order_line_group
from app.services.order_line_detail_query import get_order_line_detail_dto
from app.services.order_line_detail_update_service import update_order_line_detail_fields
from app.services.order_line_lot_context_query import get_lot_create_context_dto
from app.services.order_line_list_query import list_order_lines_for_grid
from app.services.order_line_plan_service import confirm_order_line_plan_decision
from app.services.order_line_response_builder import build_order_line_out, get_order_line_out_by_id
from app.services.order_line_short_close_service import short_close_order_line_status
from app.services.order_line_update_service import update_order_line_fields
from app.services.bulk.order_line_bulk_service import order_line_bulk_service


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, compiler, **kw):
    return "JSON"


TEST_TABLE_NAMES = [
    "partner",
    "drawing",
    "drawing_revision",
    "drawing_revision_file",
    "routing_template",
    "process",
    "routing_template_step",
    "product",
    "product_inventory",
    "product_inventory_lot",
    "order_line",
    "order_line_change_log",
    "lot",
    "lot_step",
    "order_line_plan_history",
    "shipment_line",
    "inspection_schedule",
    "inspection_result",
    "defect_type",
    "inspection_defect",
    "inspection_defect_attachment",
    "product_inventory_movement",
    "shipment_coa",
    "inspection_certificate",
    "outsource_work_instruction",
    "outsource_work_instruction_item",
    "outsource_work_group",
    "outsource_work_group_item",
    "outsource_work_group_change_log",
    "outsource_purchase_order",
    "outsource_purchase_order_item",
]


class OrderLineServicesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        tables = [Base.metadata.tables[name] for name in TEST_TABLE_NAMES]
        Base.metadata.create_all(self.engine, tables=tables)

        SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = SessionLocal()
        self._seed_base_data()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_order_line_search_uses_exact_business_numbers_and_partial_product_code(self) -> None:
        order_line = self._seed_open_order_line_without_lots()
        order_line.customer_po = "PO-CUSTOMER-001"
        self.db.commit()

        partial_order_items, _ = list_order_lines_for_grid(
            self.db, page=1, size=20, q="SO-"
        )
        exact_order_items, _ = list_order_lines_for_grid(
            self.db, page=1, size=20, q=" so-open "
        )
        partial_po_items, _ = list_order_lines_for_grid(
            self.db, page=1, size=20, q="PO-CUSTOMER"
        )
        exact_po_items, _ = list_order_lines_for_grid(
            self.db, page=1, size=20, q=" po-customer-001 "
        )
        partial_product_items, _ = list_order_lines_for_grid(
            self.db, page=1, size=20, q="001"
        )

        self.assertEqual([], partial_order_items)
        self.assertEqual([200], [item["order_line_id"] for item in exact_order_items])
        self.assertEqual([], partial_po_items)
        self.assertEqual([200], [item["order_line_id"] for item in exact_po_items])
        self.assertEqual([200], [item["order_line_id"] for item in partial_product_items])

    def test_create_order_line_without_inventory_creates_primary_lot(self) -> None:
        with patch("app.services.order_line_creation_service.refresh_order_line_snapshot") as refresh:
            order_line = create_order_line_with_policy(self.db, self._payload("SO-AUTO-LOT", 100))

        lots = self.db.execute(select(Lot).where(Lot.order_line_id == order_line.order_line_id)).scalars().all()
        histories = self.db.execute(
            select(OrderLinePlanHistory).where(OrderLinePlanHistory.order_line_id == order_line.order_line_id)
        ).scalars().all()
        shipment_lines = self.db.execute(
            select(ShipmentLine).where(ShipmentLine.order_line_id == order_line.order_line_id)
        ).scalars().all()

        self.assertEqual("CLOSED", order_line.status)
        self.assertTrue(order_line.decision_made)
        self.assertEqual("AUTO_PRODUCTION", histories[0].plan_type)
        self.assertEqual(102, histories[0].production_qty)
        self.assertEqual(1, len(lots))
        self.assertEqual(102, lots[0].lot_qty)
        self.assertEqual([], shipment_lines)
        refresh.assert_called_once_with(self.db, order_line.order_line_id)

    def test_create_order_line_with_enough_inventory_waits_for_decision(self) -> None:
        self._seed_inventory(product_id=1, qty=300)

        order_line = create_order_line_with_policy(self.db, self._payload("SO-STOCK", 100))

        lots = self.db.execute(select(Lot).where(Lot.order_line_id == order_line.order_line_id)).scalars().all()
        histories = self.db.execute(
            select(OrderLinePlanHistory).where(OrderLinePlanHistory.order_line_id == order_line.order_line_id)
        ).scalars().all()
        shipment_lines = self.db.execute(
            select(ShipmentLine).where(ShipmentLine.order_line_id == order_line.order_line_id)
        ).scalars().all()
        items, _ = list_order_lines_for_grid(
            self.db,
            page=1,
            size=20,
            status_group="IN_PROGRESS",
        )
        created_item = next(item for item in items if item["order_line_id"] == order_line.order_line_id)

        self.assertEqual("OPEN", order_line.status)
        self.assertFalse(order_line.decision_made)
        self.assertEqual("INVENTORY_FIRST", order_line.fulfillment_mode)
        self.assertEqual([], histories)
        self.assertEqual([], lots)
        self.assertEqual([], shipment_lines)
        self.assertTrue(created_item["decision_required"])
        self.assertEqual(
            ["STOCK_SHIP_COMPLETE", "STOCK_REPLENISHMENT"],
            created_item["allowed_plan_types"],
        )

    def test_confirm_enough_inventory_completes_stock_shipment(self) -> None:
        self._seed_inventory(product_id=1, qty=300)
        order_line = create_order_line_with_policy(self.db, self._payload("SO-STOCK-CONFIRM", 100))

        with (
            patch("app.services.shipment_confirm_service.refresh_order_line_snapshot"),
            patch("app.services.shipment_confirm_service.refresh_order_line_snapshots_for_product"),
            patch("app.services.order_line_plan_service.refresh_order_line_snapshot"),
            patch("app.services.order_line_plan_service.refresh_order_line_snapshots_for_product"),
        ):
            confirmed, history, _, _ = confirm_order_line_plan_decision(
                self.db,
                order_line_id=order_line.order_line_id,
                payload=OrderLinePlanConfirmRequest(plan_type="STOCK_SHIP_COMPLETE"),
            )

        shipment_lines = self.db.execute(
            select(ShipmentLine).where(ShipmentLine.order_line_id == order_line.order_line_id)
        ).scalars().all()
        inventory = self.db.execute(
            select(ProductInventory).where(ProductInventory.product_id == 1)
        ).scalar_one()

        self.assertEqual("DONE", confirmed.status)
        self.assertTrue(confirmed.decision_made)
        self.assertEqual("STOCK_SHIP_COMPLETE", history.plan_type)
        self.assertEqual(102, history.stock_ship_qty)
        self.assertEqual(1, len(shipment_lines))
        self.assertEqual("DONE", shipment_lines[0].status)
        self.assertEqual(102, shipment_lines[0].shipped_qty)
        self.assertEqual(198, inventory.current_qty)

    def test_confirm_stock_replenishment_creates_order_qty_lot_without_using_inventory(self) -> None:
        self._seed_inventory(product_id=1, qty=50)
        order_line = create_order_line_with_policy(self.db, self._payload("SO-STOCK-BUILD", 100))

        with (
            patch("app.services.order_line_plan_service.refresh_order_line_snapshot"),
            patch("app.services.order_line_plan_service.refresh_order_line_snapshots_for_product"),
            patch("app.services.order_line_creation_service.refresh_order_line_snapshot"),
        ):
            confirmed, history, _, product = confirm_order_line_plan_decision(
                self.db,
                order_line_id=order_line.order_line_id,
                payload=OrderLinePlanConfirmRequest(plan_type="STOCK_REPLENISHMENT"),
            )
            lot = create_primary_lot_for_order_line(
                self.db,
                confirmed,
                product,
                lot_qty=confirmed.order_qty,
            )

        shipment_lines = self.db.execute(
            select(ShipmentLine).where(ShipmentLine.order_line_id == order_line.order_line_id)
        ).scalars().all()
        inventory = self.db.execute(
            select(ProductInventory).where(ProductInventory.product_id == 1)
        ).scalar_one()

        self.assertEqual("CLOSED", confirmed.status)
        self.assertEqual("STOCK_REPLENISHMENT", history.plan_type)
        self.assertEqual(100, history.production_qty)
        self.assertEqual(100, lot.lot_qty)
        self.assertEqual([], shipment_lines)
        self.assertEqual(50, inventory.current_qty)

    def test_create_order_line_with_partial_inventory_waits_for_decision(self) -> None:
        self._seed_inventory(product_id=1, qty=50)

        order_line = create_order_line_with_policy(self.db, self._payload("SO-PARTIAL", 100))

        lots = self.db.execute(select(Lot).where(Lot.order_line_id == order_line.order_line_id)).scalars().all()
        histories = self.db.execute(
            select(OrderLinePlanHistory).where(OrderLinePlanHistory.order_line_id == order_line.order_line_id)
        ).scalars().all()
        shipment_lines = self.db.execute(
            select(ShipmentLine).where(ShipmentLine.order_line_id == order_line.order_line_id)
        ).scalars().all()

        self.assertEqual("OPEN", order_line.status)
        self.assertFalse(order_line.decision_made)
        self.assertEqual("HYBRID", order_line.fulfillment_mode)
        self.assertEqual([], histories)
        self.assertEqual([], lots)
        self.assertEqual([], shipment_lines)

    def test_update_closed_order_line_due_date_syncs_only_not_started_lots(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()
        new_due_date = date(2026, 2, 15)

        with patch("app.services.order_line_update_service.refresh_order_line_snapshot") as refresh:
            updated = update_order_line_fields(
                self.db,
                order_line.order_line_id,
                OrderLineUpdate(due_date=new_due_date, memo="납기 조정"),
                actor="planner01",
            )

        waiting_lot = self.db.get(Lot, 101)
        started_lot = self.db.get(Lot, 102)

        self.assertEqual(new_due_date, updated.due_date)
        self.assertEqual("납기 조정", updated.memo)
        self.assertEqual(new_due_date, waiting_lot.due_date)
        self.assertEqual(date(2026, 1, 31), started_lot.due_date)
        refresh.assert_called_once_with(self.db, order_line.order_line_id)

        changes = (
            self.db.execute(
                select(OrderLineChangeLog)
                .where(OrderLineChangeLog.order_line_id == order_line.order_line_id)
                .order_by(OrderLineChangeLog.order_line_change_log_id)
            )
            .scalars()
            .all()
        )
        self.assertEqual(["DUE_DATE_CHANGE", "MEMO_CHANGE"], [item.change_type for item in changes])
        self.assertEqual(["planner01", "planner01"], [item.created_by for item in changes])

    def test_update_closed_order_line_rejects_quantity_change(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()

        with self.assertRaises(HTTPException) as ctx:
            update_order_line_fields(
                self.db,
                order_line.order_line_id,
                OrderLineUpdate(order_qty=200),
                actor="planner01",
            )

        self.assertEqual(409, ctx.exception.status_code)

    def test_update_open_order_line_quantity_uses_shared_change_policy(self) -> None:
        order_line = self._seed_open_order_line_without_lots()

        with patch("app.services.order_line_update_service.refresh_order_line_snapshot"):
            updated = update_order_line_fields(
                self.db,
                order_line.order_line_id,
                OrderLineUpdate(order_qty=125),
                actor="planner01",
            )

        change = self.db.execute(
            select(OrderLineChangeLog).where(
                OrderLineChangeLog.order_line_id == order_line.order_line_id,
                OrderLineChangeLog.change_type == "QUANTITY_CHANGE",
            )
        ).scalar_one()

        self.assertEqual(125, updated.order_qty)
        self.assertEqual({"order_qty": 100, "lot_qty": None}, change.before_data)
        self.assertEqual({"order_qty": 125, "lot_qty": None}, change.after_data)
        self.assertEqual("planner01", change.created_by)

    def test_order_line_detail_marks_flags_current_process_and_plan_timeline(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()
        self.db.add(
            OrderLinePlanHistory(
                plan_history_id=100,
                order_line_id=order_line.order_line_id,
                plan_type="AUTO_PRODUCTION",
                ship_target_qty=102,
                available_inventory_qty=0,
                stock_ship_qty=0,
                production_qty=102,
                is_short_close=False,
                memo="자동 생산",
            )
        )
        self.db.flush()

        detail = get_order_line_detail_dto(self.db, order_line.order_line_id)
        lot_map = {lot.lot_no: lot for lot in detail.lots}

        self.assertEqual("IN_PROGRESS", detail.status_display)
        self.assertTrue(detail.can_edit)
        self.assertTrue(detail.can_save)
        self.assertFalse(detail.can_cancel_order)
        self.assertFalse(detail.can_create_base_lot)
        self.assertEqual("재단", lot_map["LOT-STARTED"].current_process_name)
        self.assertTrue(lot_map["LOT-STARTED"].is_editable)
        self.assertTrue(any(item.event_type == "PLAN_CONFIRMED" for item in detail.timeline))

    def test_order_line_detail_can_exclude_plan_history_for_post_action_response(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()
        self.db.add(
            OrderLinePlanHistory(
                plan_history_id=101,
                order_line_id=order_line.order_line_id,
                plan_type="AUTO_PRODUCTION",
                ship_target_qty=102,
                available_inventory_qty=0,
                stock_ship_qty=0,
                production_qty=102,
                is_short_close=False,
            )
        )
        self.db.flush()

        detail = get_order_line_detail_dto(self.db, order_line.order_line_id, include_plan_history=False)

        self.assertFalse(any(item.event_type == "PLAN_CONFIRMED" for item in detail.timeline))

    def test_order_line_detail_marks_canceled_order_as_not_actionable(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()
        order_line.status = "CANCELED"
        for lot in self.db.execute(select(Lot).where(Lot.order_line_id == order_line.order_line_id)).scalars():
            lot.status = "CANCELED"
        self.db.flush()

        detail = get_order_line_detail_dto(self.db, order_line.order_line_id, include_plan_history=False)

        self.assertEqual("CANCELED", detail.status_display)
        self.assertFalse(detail.can_edit)
        self.assertFalse(detail.can_save)
        self.assertFalse(detail.can_cancel_order)
        self.assertFalse(detail.can_create_base_lot)
        self.assertTrue(all(not lot.is_editable for lot in detail.lots))
        self.assertTrue(all(not lot.can_cancel for lot in detail.lots))
        self.assertTrue(all(lot.can_create_rework for lot in detail.lots))
        self.assertTrue(any(item.event_type == "ORDER_CANCELED" for item in detail.timeline))

    def test_cancel_order_line_without_lots_marks_canceled(self) -> None:
        order_line = self._seed_open_order_line_without_lots()

        canceled = cancel_order_line_status(self.db, order_line.order_line_id)

        self.assertEqual("CANCELED", canceled.status)
        self.assertEqual("CANCELED", self.db.get(OrderLine, order_line.order_line_id).status)

    def test_cancel_order_line_rejects_non_canceled_lot(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()

        with self.assertRaises(HTTPException) as ctx:
            cancel_order_line_status(self.db, order_line.order_line_id)

        self.assertEqual(409, ctx.exception.status_code)
        self.assertEqual("CLOSED", self.db.get(OrderLine, order_line.order_line_id).status)

    def test_cancel_order_line_allows_when_all_lots_are_canceled(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()
        for lot in self.db.execute(select(Lot).where(Lot.order_line_id == order_line.order_line_id)).scalars():
            lot.status = "CANCELED"
        self.db.flush()

        canceled = cancel_order_line_status(self.db, order_line.order_line_id)
        detail = get_order_line_detail_dto(self.db, order_line.order_line_id, include_plan_history=False)

        self.assertEqual("CANCELED", canceled.status)
        self.assertFalse(detail.can_cancel_order)
        self.assertTrue(any(item.event_type == "ORDER_CANCELED" for item in detail.timeline))

    def test_delete_order_line_group_removes_same_order_number_rows_and_children(self) -> None:
        self._seed_deletable_order_group()

        result = delete_order_line_group(self.db, 300)

        self.assertEqual(
            {
                "success": True,
                "order_no": "SO-DELETE",
                "deleted_order_line_count": 2,
                "deleted_lot_count": 2,
                "deleted_shipment_line_count": 1,
            },
            result,
        )
        self.assertEqual(0, self._count(OrderLine, OrderLine.order_no == "SO-DELETE"))
        self.assertEqual(0, self._count(Lot, Lot.order_line_id.in_([300, 301])))
        self.assertEqual(0, self._count(LotStep, LotStep.lot_id.in_([301, 302])))
        self.assertEqual(0, self._count(OrderLinePlanHistory, OrderLinePlanHistory.order_line_id.in_([300, 301])))
        self.assertEqual(0, self._count(ShipmentLine, ShipmentLine.order_line_id.in_([300, 301])))

    def test_delete_order_line_group_rejects_progressed_lot(self) -> None:
        self._seed_deletable_order_group()
        self.db.get(Lot, 301).status = "DONE"
        self.db.flush()

        with self.assertRaises(HTTPException) as ctx:
            delete_order_line_group(self.db, 300)

        self.assertEqual(409, ctx.exception.status_code)
        self.assertIn("진행/완료 LOT 1건", str(ctx.exception.detail))
        self.assertEqual(2, self._count(OrderLine, OrderLine.order_no == "SO-DELETE"))
        self.assertEqual(2, self._count(Lot, Lot.order_line_id.in_([300, 301])))

    def test_create_base_lot_from_plan_creates_planned_lot_and_steps(self) -> None:
        order_line = self._seed_open_decision_made_order_line()
        self.db.add(
            OrderLinePlanHistory(
                plan_history_id=400,
                order_line_id=order_line.order_line_id,
                plan_type="PARTIAL_STOCK_PLUS_PRODUCTION",
                ship_target_qty=102,
                available_inventory_qty=20,
                stock_ship_qty=20,
                production_qty=82,
                is_short_close=False,
            )
        )
        self.db.flush()

        with patch("app.services.order_line_creation_service.refresh_order_line_snapshot") as refresh:
            result = create_base_lot_from_plan(self.db, order_line.order_line_id)

        created_lot = self.db.get(Lot, result.created_lot_id)
        created_steps = self.db.execute(
            select(LotStep).where(LotStep.lot_id == result.created_lot_id)
        ).scalars().all()

        self.assertEqual(order_line.order_line_id, result.order_line_id)
        self.assertEqual(82, result.planned_production_qty)
        self.assertEqual(82, result.created_lot_qty)
        self.assertEqual("CLOSED", result.order_status)
        self.assertEqual("CLOSED", order_line.status)
        self.assertEqual(82, created_lot.lot_qty)
        self.assertEqual(1, len(created_steps))
        self.assertEqual("WAITING", created_steps[0].status)
        refresh.assert_called_once_with(self.db, order_line.order_line_id)

    def test_create_base_lot_from_plan_rejects_missing_decision(self) -> None:
        order_line = self._seed_open_order_line_without_lots()

        with self.assertRaises(HTTPException) as ctx:
            create_base_lot_from_plan(self.db, order_line.order_line_id)

        self.assertEqual(409, ctx.exception.status_code)
        self.assertEqual(0, self._count(Lot, Lot.order_line_id == order_line.order_line_id))

    def test_lot_create_context_includes_drawing_files_and_primary_lot_candidates(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()
        self.db.get(Lot, 102).status = "DONE"
        self.db.flush()

        context = get_lot_create_context_dto(self.db, order_line.order_line_id)
        candidates = {candidate.lot_no: candidate for candidate in context.primary_lot_candidates}

        self.assertEqual(order_line.order_line_id, context.order_line_id)
        self.assertEqual("Customer", context.partner_name)
        self.assertEqual("P-001", context.product_code)
        self.assertEqual(1, context.drawing.drawing_id)
        self.assertEqual("D-001", context.drawing.drawing_no)
        self.assertEqual(1, context.drawing.current_revision_id)
        self.assertEqual("A", context.drawing.current_revision_no)
        self.assertEqual("drawing.pdf", context.drawing.drawing_file_name)
        self.assertEqual("original.ai", context.drawing.original_file_name)
        self.assertEqual("plate.pdf", context.drawing.plate_file_name)
        self.assertFalse(candidates["LOT-WAITING"].can_create_rework)
        self.assertTrue(candidates["LOT-STARTED"].can_create_rework)

    def test_update_order_line_detail_fields_updates_due_memo_and_syncs_waiting_lot_due_date(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()
        new_due_date = date(2026, 2, 20)

        with patch("app.services.order_line_update_service.refresh_order_line_snapshot") as refresh:
            updated = update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                OrderLineDetailUpdate(
                    due_date=new_due_date,
                    order_qty=100,
                    memo="detail memo",
                ),
                actor="tester",
            )

        waiting_lot = self.db.get(Lot, 101)
        started_lot = self.db.get(Lot, 102)

        self.assertEqual(new_due_date, updated.due_date)
        self.assertEqual(100, updated.order_qty)
        self.assertEqual("detail memo", updated.memo)
        self.assertEqual(new_due_date, waiting_lot.due_date)
        self.assertEqual(date(2026, 1, 31), started_lot.due_date)
        change_logs = (
            self.db.execute(
                select(OrderLineChangeLog)
                .where(OrderLineChangeLog.order_line_id == order_line.order_line_id)
                .order_by(OrderLineChangeLog.order_line_change_log_id.asc())
            )
            .scalars()
            .all()
        )
        self.assertEqual(
            ["DUE_DATE_CHANGE", "MEMO_CHANGE"],
            [change_log.change_type for change_log in change_logs],
        )
        self.assertTrue(
            all(change_log.created_by == "tester" for change_log in change_logs)
        )
        refresh.assert_called_once_with(self.db, order_line.order_line_id)

    def test_update_order_line_detail_fields_syncs_waiting_lot_and_plan_quantity(self) -> None:
        order_line = self._seed_closed_order_line_with_waiting_lot()

        with patch(
            "app.services.order_line_detail_update_service.refresh_order_line_snapshot"
        ) as refresh:
            updated = update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                OrderLineDetailUpdate(
                    due_date=order_line.due_date,
                    order_qty=120,
                    memo="quantity corrected",
                ),
                actor="tester",
            )

        lot = self.db.get(Lot, 501)
        plan_histories = (
            self.db.execute(
                select(OrderLinePlanHistory)
                .where(OrderLinePlanHistory.order_line_id == order_line.order_line_id)
                .order_by(OrderLinePlanHistory.plan_history_id.asc())
            )
            .scalars()
            .all()
        )

        self.assertEqual(120, updated.order_qty)
        self.assertEqual(123, lot.lot_qty)
        self.assertEqual(2, len(plan_histories))
        self.assertEqual(123, plan_histories[-1].production_qty)
        self.assertEqual("tester", plan_histories[-1].created_by)
        self.assertIn("수주수량 변경으로 처리계획 재계산", plan_histories[-1].memo)

        quantity_change_log = self.db.execute(
            select(OrderLineChangeLog).where(
                OrderLineChangeLog.order_line_id == order_line.order_line_id,
                OrderLineChangeLog.change_type == "QUANTITY_CHANGE",
            )
        ).scalar_one()
        self.assertEqual(501, quantity_change_log.lot_id)
        self.assertEqual(100, quantity_change_log.before_data["order_qty"])
        self.assertEqual(120, quantity_change_log.after_data["order_qty"])
        self.assertEqual(102, quantity_change_log.before_data["lot_qty"])
        self.assertEqual(123, quantity_change_log.after_data["lot_qty"])
        self.assertEqual("tester", quantity_change_log.created_by)

        detail = get_order_line_detail_dto(self.db, order_line.order_line_id)
        quantity_timeline_items = [
            item
            for item in detail.timeline
            if item.event_type == "ORDER_QUANTITY_CHANGED"
        ]
        self.assertEqual(1, len(quantity_timeline_items))
        timeline_item = quantity_timeline_items[0]
        self.assertEqual("수주수량 정정", timeline_item.event_label)
        self.assertIn("수주수량 100 EA → 120 EA", timeline_item.message)
        self.assertIn("LOT-QTY-CORRECTION 계획수량 102 EA → 123 EA", timeline_item.message)
        self.assertIn("처리자: tester", timeline_item.message)
        self.assertEqual("ORDER_LINE_CHANGE_LOG", timeline_item.ref_type)
        self.assertEqual(quantity_change_log.order_line_change_log_id, timeline_item.ref_id)
        refresh.assert_called_once_with(self.db, order_line.order_line_id)

    def test_update_partial_stock_order_quantity_keeps_reservation_and_recalculates_lot(self) -> None:
        order_line = self._seed_partial_stock_order_line()

        with patch(
            "app.services.order_line_detail_update_service.refresh_order_line_snapshot"
        ):
            updated = update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                OrderLineDetailUpdate(
                    due_date=order_line.due_date,
                    order_qty=120,
                    memo="partial stock quantity corrected",
                ),
                actor="tester",
            )

        lot = self.db.get(Lot, 501)
        reservation = self.db.get(ShipmentLine, 601)
        histories = (
            self.db.execute(
                select(OrderLinePlanHistory)
                .where(OrderLinePlanHistory.order_line_id == order_line.order_line_id)
                .order_by(OrderLinePlanHistory.plan_history_id.asc())
            )
            .scalars()
            .all()
        )
        quantity_change = self.db.execute(
            select(OrderLineChangeLog).where(
                OrderLineChangeLog.order_line_id == order_line.order_line_id,
                OrderLineChangeLog.change_type == "QUANTITY_CHANGE",
            )
        ).scalar_one()

        self.assertEqual(120, updated.order_qty)
        self.assertEqual(103, lot.lot_qty)
        self.assertEqual("WAITING", reservation.status)
        self.assertEqual(20, reservation.ship_qty)
        self.assertEqual(0, reservation.shipped_qty)
        self.assertEqual(2, len(histories))
        self.assertEqual("PARTIAL_STOCK_PLUS_PRODUCTION", histories[-1].plan_type)
        self.assertEqual(123, histories[-1].ship_target_qty)
        self.assertEqual(20, histories[-1].stock_ship_qty)
        self.assertEqual(103, histories[-1].production_qty)
        self.assertEqual("tester", histories[-1].created_by)
        self.assertIn("예약재고 20 유지", histories[-1].memo)
        self.assertEqual(
            {
                "ship_target_qty": 102,
                "stock_ship_qty": 20,
                "production_qty": 82,
            },
            quantity_change.before_data["plan"],
        )
        self.assertEqual(
            {
                "ship_target_qty": 123,
                "stock_ship_qty": 20,
                "production_qty": 103,
            },
            quantity_change.after_data["plan"],
        )

        detail = get_order_line_detail_dto(self.db, order_line.order_line_id)
        timeline_item = next(
            item
            for item in detail.timeline
            if item.event_type == "ORDER_QUANTITY_CHANGED"
        )
        self.assertIn("예약재고 20 EA 유지", timeline_item.message)
        self.assertIn("처리자: tester", timeline_item.message)

    def test_update_partial_stock_order_quantity_rejects_actual_inventory_movement(self) -> None:
        order_line = self._seed_partial_stock_order_line()
        self.db.add(
            ProductInventoryMovement(
                inventory_movement_id=601,
                product_id=order_line.product_id,
                movement_type="SHIP_OUT",
                qty=-1,
                balance_after=19,
                source_type="SHIPMENT_LINE",
                source_id=601,
                order_line_id=order_line.order_line_id,
            )
        )
        self.db.flush()

        with self.assertRaises(HTTPException) as ctx:
            update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                OrderLineDetailUpdate(
                    due_date=order_line.due_date,
                    order_qty=120,
                    memo="must stay blocked",
                ),
                actor="tester",
            )

        self.assertEqual(409, ctx.exception.status_code)
        self.assertIn("실제 재고 수불 이력", ctx.exception.detail)
        self.assertEqual(100, order_line.order_qty)
        self.assertEqual(82, self.db.get(Lot, 501).lot_qty)

    def test_update_partial_stock_order_quantity_rejects_started_reservation(self) -> None:
        order_line = self._seed_partial_stock_order_line()
        reservation = self.db.get(ShipmentLine, 601)
        reservation.status = "DONE"
        reservation.shipped_qty = 20
        self.db.flush()

        with self.assertRaises(HTTPException) as ctx:
            update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                OrderLineDetailUpdate(
                    due_date=order_line.due_date,
                    order_qty=120,
                    memo="must stay blocked",
                ),
                actor="tester",
            )

        self.assertEqual(409, ctx.exception.status_code)
        self.assertIn("이미 출하 처리되었거나 변경", ctx.exception.detail)
        self.assertEqual(100, order_line.order_qty)
        self.assertEqual(82, self.db.get(Lot, 501).lot_qty)

    def test_update_partial_stock_order_quantity_rejects_reservation_plan_mismatch(self) -> None:
        order_line = self._seed_partial_stock_order_line()
        self.db.get(ShipmentLine, 601).ship_qty = 19
        self.db.flush()

        with self.assertRaises(HTTPException) as ctx:
            update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                OrderLineDetailUpdate(
                    due_date=order_line.due_date,
                    order_qty=120,
                    memo="must stay blocked",
                ),
                actor="tester",
            )

        self.assertEqual(409, ctx.exception.status_code)
        self.assertIn("예약재고와 실제 출하대기 수량이 일치하지 않아", ctx.exception.detail)
        self.assertEqual(100, order_line.order_qty)
        self.assertEqual(82, self.db.get(Lot, 501).lot_qty)

    def test_update_partial_stock_order_quantity_requires_replan_when_production_becomes_zero(self) -> None:
        order_line = self._seed_partial_stock_order_line()

        with self.assertRaises(HTTPException) as ctx:
            update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                OrderLineDetailUpdate(
                    due_date=order_line.due_date,
                    order_qty=10,
                    memo="requires replan",
                ),
                actor="tester",
            )

        self.assertEqual(409, ctx.exception.status_code)
        self.assertIn("생산 LOT가 불필요", ctx.exception.detail)
        self.assertEqual(100, order_line.order_qty)
        self.assertEqual(82, self.db.get(Lot, 501).lot_qty)

    def test_order_line_detail_timeline_supports_legacy_quantity_change_history(self) -> None:
        order_line = self._seed_closed_order_line_with_waiting_lot()
        self.db.add(
            OrderLinePlanHistory(
                plan_history_id=502,
                order_line_id=order_line.order_line_id,
                plan_type="AUTO_PRODUCTION",
                ship_target_qty=30600,
                available_inventory_qty=0,
                stock_ship_qty=0,
                production_qty=30600,
                is_short_close=False,
                memo=(
                    "수주수량 정정 40,000 -> 30,000; "
                    "LOT 계획수량 정정 40,800 -> 30,600"
                ),
                created_by="system",
            )
        )
        self.db.flush()

        detail = get_order_line_detail_dto(self.db, order_line.order_line_id)

        timeline_item = next(
            item
            for item in detail.timeline
            if item.event_type == "ORDER_QUANTITY_CHANGED"
        )
        self.assertIn("수주수량 40,000 EA → 30,000 EA", timeline_item.message)
        self.assertIn(
            "LOT-QTY-CORRECTION 계획수량 40,800 EA → 30,600 EA",
            timeline_item.message,
        )

    def test_order_line_detail_timeline_includes_outsource_update_and_cancel(self) -> None:
        order_line = self._seed_closed_order_line_with_waiting_lot()
        self.db.add_all(
            [
                OutsourceWorkInstruction(
                    outsource_work_instruction_id=800,
                    instruction_no="OWI-TIMELINE",
                    instruction_date=date(2026, 1, 3),
                    process_type="CUT",
                    partner_id=1,
                    is_bundle=False,
                ),
                OutsourceWorkGroup(
                    outsource_work_group_id=800,
                    outsource_work_instruction_id=800,
                    group_seq="A001",
                    process_type="CUT",
                    is_bundle=False,
                    sheet_qty=60,
                    sheet_cut_count=2,
                    representative_lot_id=501,
                    status="CANCELED",
                    canceled_at=datetime(2026, 1, 4, 10, 0, 0),
                    canceled_reason="작업지시 오류",
                ),
                OutsourceWorkGroupItem(
                    outsource_work_group_item_id=800,
                    outsource_work_group_id=800,
                    lot_id=501,
                    cuts_per_sheet=2,
                    expected_output_qty=120,
                ),
                OutsourceWorkGroupChangeLog(
                    outsource_work_group_change_log_id=800,
                    outsource_work_group_id=800,
                    action_type="UPDATE",
                    reason="발주수량 정정",
                    before_data={
                        "sheet_qty": 51,
                        "sheet_cut_count": 2,
                        "items": [{"lot_id": 501, "expected_output_qty": 102}],
                    },
                    after_data={
                        "sheet_qty": 60,
                        "sheet_cut_count": 2,
                        "items": [{"lot_id": 501, "expected_output_qty": 120}],
                    },
                    created_at=datetime(2026, 1, 4, 9, 0, 0),
                ),
            ]
        )
        self.db.flush()

        detail = get_order_line_detail_dto(self.db, order_line.order_line_id)

        updated = next(
            item
            for item in detail.timeline
            if item.event_type == "OUTSOURCE_INSTRUCTION_UPDATED"
        )
        self.assertEqual("외주 작업지시 수정", updated.event_label)
        self.assertIn("LOT-QTY-CORRECTION / OWI-TIMELINE", updated.message)
        self.assertIn("작업수량(장) 51 → 60", updated.message)
        self.assertIn("수정사유: 발주수량 정정", updated.message)

        canceled = next(
            item
            for item in detail.timeline
            if item.event_type == "OUTSOURCE_INSTRUCTION_CANCELED"
        )
        self.assertEqual("외주 작업지시 취소", canceled.event_label)
        self.assertIn("취소사유: 작업지시 오류", canceled.message)

    def test_update_order_line_detail_fields_rejects_quantity_change_after_lot_start(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()

        with self.assertRaises(HTTPException) as ctx:
            update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                OrderLineDetailUpdate(
                    due_date=order_line.due_date,
                    order_qty=120,
                    memo="blocked",
                ),
                actor="tester",
            )

        self.assertEqual(409, ctx.exception.status_code)
        self.assertEqual(100, order_line.order_qty)

    def test_update_order_line_detail_fields_rejects_legacy_active_outsource_item(self) -> None:
        order_line = self._seed_closed_order_line_with_waiting_lot()
        self.db.add_all(
            [
                OutsourceWorkInstruction(
                    outsource_work_instruction_id=699,
                    instruction_no="OWI-LEGACY-QTY-CORRECTION",
                    instruction_date=date(2026, 1, 3),
                    process_type="CUT",
                    partner_id=1,
                    is_bundle=False,
                ),
                OutsourceWorkInstructionItem(
                    outsource_work_instruction_item_id=699,
                    outsource_work_instruction_id=699,
                    lot_id=501,
                    process_type="CUT",
                    is_active=True,
                ),
            ]
        )
        self.db.flush()

        with self.assertRaises(HTTPException) as ctx:
            update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                OrderLineDetailUpdate(
                    due_date=order_line.due_date,
                    order_qty=120,
                    memo="must remain unchanged",
                ),
                actor="tester",
            )

        self.assertEqual(409, ctx.exception.status_code)
        self.assertIn("외주 작업지시를 먼저 취소", ctx.exception.detail)
        self.assertEqual(100, order_line.order_qty)
        self.assertEqual(102, self.db.get(Lot, 501).lot_qty)
        self.assertEqual(
            0,
            self.db.scalar(
                select(func.count())
                .select_from(OrderLineChangeLog)
                .where(OrderLineChangeLog.order_line_id == order_line.order_line_id)
            ),
        )

    def test_update_order_line_detail_fields_requires_outsource_cancel_then_syncs_quantity(self) -> None:
        order_line = self._seed_closed_order_line_with_waiting_lot()
        self.db.add_all(
            [
                OutsourceWorkInstruction(
                    outsource_work_instruction_id=700,
                    instruction_no="OWI-QTY-CORRECTION",
                    instruction_date=date(2026, 1, 3),
                    process_type="CUT",
                    partner_id=1,
                    is_bundle=False,
                ),
                OutsourceWorkGroup(
                    outsource_work_group_id=700,
                    outsource_work_instruction_id=700,
                    group_seq="A001",
                    process_type="CUT",
                    is_bundle=False,
                    sheet_qty=51,
                    sheet_cut_count=2,
                    representative_lot_id=501,
                    status=None,
                ),
                OutsourceWorkGroupItem(
                    outsource_work_group_item_id=700,
                    outsource_work_group_id=700,
                    lot_id=501,
                    cuts_per_sheet=2,
                    expected_output_qty=102,
                ),
            ]
        )
        self.db.flush()

        payload = OrderLineDetailUpdate(
            due_date=order_line.due_date,
            order_qty=120,
            memo="quantity corrected",
        )
        with self.assertRaises(HTTPException) as ctx:
            update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                payload,
                actor="tester",
            )

        self.assertEqual(409, ctx.exception.status_code)
        self.assertIn("외주 작업지시를 먼저 취소", ctx.exception.detail)

        work_group = self.db.get(OutsourceWorkGroup, 700)
        work_group.status = "CANCELED"
        self.db.flush()

        with patch(
            "app.services.order_line_detail_update_service.refresh_order_line_snapshot"
        ):
            updated = update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                payload,
                actor="tester",
            )

        self.assertEqual(120, updated.order_qty)
        self.assertEqual(123, self.db.get(Lot, 501).lot_qty)

    def test_update_order_line_detail_fields_invalidates_plan_before_lot_creation(self) -> None:
        order_line = self._seed_open_decision_made_order_line()
        self.db.add(
            ShipmentLine(
                shipment_line_id=600,
                order_line_id=order_line.order_line_id,
                product_id=order_line.product_id,
                source_type="STOCK",
                status="WAITING",
                ship_qty=20,
                shipped_qty=0,
            )
        )
        self.db.flush()

        with patch(
            "app.services.order_line_detail_update_service.refresh_order_line_snapshot"
        ):
            updated = update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                OrderLineDetailUpdate(
                    due_date=order_line.due_date,
                    order_qty=120,
                    memo="quantity corrected before lot",
                ),
                actor="tester",
            )

        shipment_line = self.db.get(ShipmentLine, 600)
        self.assertEqual(120, updated.order_qty)
        self.assertFalse(updated.decision_made)
        self.assertEqual("CANCELED", shipment_line.status)
        self.assertIn("처리계획 재확정 필요", shipment_line.memo)
        quantity_change_log = self.db.execute(
            select(OrderLineChangeLog).where(
                OrderLineChangeLog.order_line_id == order_line.order_line_id,
                OrderLineChangeLog.change_type == "QUANTITY_CHANGE",
            )
        ).scalar_one()
        self.assertIsNone(quantity_change_log.lot_id)
        self.assertEqual(100, quantity_change_log.before_data["order_qty"])
        self.assertEqual(120, quantity_change_log.after_data["order_qty"])

        detail = get_order_line_detail_dto(self.db, order_line.order_line_id)
        timeline_item = next(
            item
            for item in detail.timeline
            if item.event_type == "ORDER_QUANTITY_CHANGED"
        )
        self.assertIn("수주수량 100 EA → 120 EA", timeline_item.message)
        self.assertNotIn("LOT 계획수량", timeline_item.message)

    def test_update_order_line_detail_fields_rejects_done_order_line(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()
        order_line.status = "DONE"
        self.db.flush()

        with self.assertRaises(HTTPException) as ctx:
            update_order_line_detail_fields(
                self.db,
                order_line.order_line_id,
                OrderLineDetailUpdate(
                    due_date=date(2026, 2, 20),
                    order_qty=120,
                    memo="blocked",
                ),
                actor="tester",
            )

        self.assertEqual(409, ctx.exception.status_code)

    def test_short_close_survives_memo_edit_and_records_decision(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()
        original_memo = order_line.memo

        updated = short_close_order_line_status(
            self.db,
            order_line.order_line_id,
            OrderLineShortCloseRequest(memo="customer accepted shortage"),
            actor="tester",
        )

        self.assertEqual("DONE", updated.status)
        self.assertEqual(original_memo, updated.memo)
        self.assertEqual("CONFIRMED", updated.short_close_state)
        history = self.db.execute(select(OrderLineChangeLog).where(
            OrderLineChangeLog.change_type == "SHORT_CLOSE")).scalar_one()
        self.assertEqual("tester", history.created_by)
        self.assertEqual("customer accepted shortage", history.reason)
        self.assertEqual(102, history.after_data["remaining_ship_qty"])
        from app.services.order_fulfillment_policy import sync_order_fulfillment_status
        updated.memo = "ordinary edited memo"
        sync_order_fulfillment_status(self.db, updated)
        self.assertEqual("DONE", updated.status)

    def test_memo_marker_cannot_freeze_unfulfilled_order(self) -> None:
        from app.services.order_fulfillment_policy import sync_order_fulfillment_status
        order_line = self._seed_closed_order_line_with_lots()
        order_line.status = "DONE"
        order_line.memo = "ordinary memo mentions [SHORT_CLOSE]"
        sync_order_fulfillment_status(self.db, order_line)
        self.assertEqual("CLOSED", order_line.status)

    def test_legacy_review_state_survives_memo_edit_without_fabricating_confirmation(self) -> None:
        from app.services.order_fulfillment_policy import sync_order_fulfillment_status
        order_line = self._seed_closed_order_line_with_lots()
        order_line.status = "DONE"
        order_line.short_close_state = "REVIEW_REQUIRED"
        order_line.memo = "edited ordinary memo"
        sync_order_fulfillment_status(self.db, order_line)
        self.assertEqual("DONE", order_line.status)
        output = build_order_line_out(self.db, order_line)
        self.assertEqual("REVIEW_REQUIRED", output.short_close_state)
        self.assertFalse(output.shortage_closed)

    def test_short_close_order_line_status_rejects_when_no_remaining_ship_qty(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()
        self.db.add(
            ProductInventoryMovement(
                inventory_movement_id=100,
                product_id=1,
                product_inventory_lot_id=None,
                stock_lot_no=None,
                movement_type="SHIP_OUT",
                qty=-102,
                balance_after=0,
                order_line_id=order_line.order_line_id,
            )
        )
        self.db.flush()

        with self.assertRaises(HTTPException) as ctx:
            short_close_order_line_status(
                self.db,
                order_line.order_line_id,
                OrderLineShortCloseRequest(memo="no shortage"),
                actor="tester",
            )

        self.assertEqual(409, ctx.exception.status_code)
        self.assertEqual("CLOSED", order_line.status)

    def test_commit_order_line_bulk_creates_group_and_applies_product_name_change(self) -> None:
        payload = OrderLineBulkCommitRequest(
            items=[
                OrderLineBulkImportRowIn(
                    row_number=1,
                    erp_order_no="2026/01/10 - 1",
                    product_code="P-001",
                    partner_name="Customer",
                    erp_product_display_name="Updated Product [Spec A]",
                    order_qty_text="10",
                    due_date_text="2026/01/31",
                    remark="bulk memo",
                ),
                OrderLineBulkImportRowIn(
                    row_number=2,
                    erp_order_no="2026/01/10 - 1",
                    product_code="P-001",
                    partner_name="Customer",
                    erp_product_display_name="Updated Product [Spec A]",
                    order_qty_text="20",
                    due_date_text="2026/01/31",
                    remark="bulk memo",
                ),
            ],
            row_choices=[
                OrderLineBulkCommitRowChoice(row_number=1, apply_product_name_change=True),
                OrderLineBulkCommitRowChoice(row_number=2, apply_product_name_change=True),
            ],
        )

        with patch("app.services.order_line_creation_service.refresh_order_line_snapshot"):
            result = order_line_bulk_service.commit_bulk(self.db, payload)

        created_order_lines = (
            self.db.execute(
                select(OrderLine).where(OrderLine.order_no == "2026/01/10 - 1").order_by(OrderLine.line_no.asc())
            )
            .scalars()
            .all()
        )
        product = self.db.get(Product, 1)

        self.assertEqual(1, result.success_group_count)
        self.assertEqual(0, result.failure_group_count)
        self.assertEqual(2, len(result.groups[0].created_order_line_ids))
        self.assertEqual([1, 2], [order_line.line_no for order_line in created_order_lines])
        self.assertEqual([10, 20], [order_line.order_qty for order_line in created_order_lines])
        self.assertTrue(all(order_line.memo == "bulk memo" for order_line in created_order_lines))
        self.assertEqual("Updated Product", product.product_name)
        self.assertEqual("Spec A", product.product_spec)

    def test_commit_order_line_bulk_rejects_conflicting_product_name_change_choices(self) -> None:
        payload = OrderLineBulkCommitRequest(
            items=[
                OrderLineBulkImportRowIn(
                    row_number=1,
                    erp_order_no="2026/01/11 - 1",
                    product_code="P-001",
                    partner_name="Customer",
                    erp_product_display_name="Updated Product A",
                    order_qty_text="10",
                    due_date_text="2026/01/31",
                    remark=None,
                ),
                OrderLineBulkImportRowIn(
                    row_number=2,
                    erp_order_no="2026/01/11 - 1",
                    product_code="P-001",
                    partner_name="Customer",
                    erp_product_display_name="Updated Product B",
                    order_qty_text="20",
                    due_date_text="2026/01/31",
                    remark=None,
                ),
            ],
            row_choices=[
                OrderLineBulkCommitRowChoice(row_number=1, apply_product_name_change=True),
                OrderLineBulkCommitRowChoice(row_number=2, apply_product_name_change=True),
            ],
        )

        result = order_line_bulk_service.commit_bulk(self.db, payload)

        self.assertEqual(0, result.success_group_count)
        self.assertEqual(1, result.failure_group_count)
        self.assertEqual("ERROR", result.groups[0].status)
        self.assertIn("서로 다른 품목명 변경", result.groups[0].message)
        self.assertEqual(0, self._count(OrderLine, OrderLine.order_no == "2026/01/11 - 1"))

    def test_build_order_line_out_includes_display_fields_and_plan_summary(self) -> None:
        order_line = self._seed_closed_order_line_with_lots()
        history = OrderLinePlanHistory(
            plan_history_id=500,
            order_line_id=order_line.order_line_id,
            plan_type="AUTO_PRODUCTION",
            ship_target_qty=102,
            available_inventory_qty=0,
            stock_ship_qty=0,
            production_qty=102,
            is_short_close=False,
        )
        self.db.add(history)
        self.db.flush()

        out = build_order_line_out(self.db, order_line, plan_history=history)

        self.assertEqual("Customer", out.partner_name)
        self.assertEqual("P-001", out.product_code)
        self.assertEqual(order_line.product.product_name, out.product_name)
        self.assertEqual("AUTO_PRODUCTION", out.plan_type)
        self.assertIsNotNone(out.plan_type_display)

    def test_get_order_line_out_by_id_rejects_inactive_or_missing_order_line(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            get_order_line_out_by_id(self.db, 999999)

        self.assertEqual(404, ctx.exception.status_code)

    def _payload(self, order_no: str, order_qty: int) -> OrderLineCreate:
        return OrderLineCreate(
            order_no=order_no,
            line_no=1,
            partner_id=1,
            product_id=1,
            order_date=date(2026, 1, 1),
            due_date=date(2026, 1, 31),
            order_qty=order_qty,
            uom="EA",
        )

    def _seed_base_data(self) -> None:
        self.db.add_all(
            [
                Partner(
                    partner_id=1,
                    partner_type="CUSTOMER",
                    name="Customer",
                    business_no="C-001",
                    is_active=True,
                ),
                Drawing(
                    drawing_id=1,
                    drawing_no="D-001",
                    current_revision_id=1,
                    is_active=True,
                ),
                DrawingRevision(
                    revision_id=1,
                    drawing_id=1,
                    rev_no="A",
                    file_uri="/drawings/D-001-A.pdf",
                ),
                DrawingRevisionFile(
                    revision_file_id=1,
                    revision_id=1,
                    file_kind="DRAWING",
                    file_uri="/drawings/drawing.pdf",
                    original_filename="drawing.pdf",
                    content_type="application/pdf",
                ),
                DrawingRevisionFile(
                    revision_file_id=2,
                    revision_id=1,
                    file_kind="ORIGINAL",
                    file_uri="/drawings/original.ai",
                    original_filename="original.ai",
                    content_type="application/postscript",
                ),
                DrawingRevisionFile(
                    revision_file_id=3,
                    revision_id=1,
                    file_kind="PLATE",
                    file_uri="/drawings/plate.pdf",
                    original_filename="plate.pdf",
                    content_type="application/pdf",
                ),
                RoutingTemplate(
                    routing_template_id=1,
                    template_code="RT-001",
                    template_name="기본 라우팅",
                    is_active=True,
                ),
                Process(
                    process_id=1,
                    process_code="CUT",
                    process_name="재단",
                    process_type="INTERNAL",
                    is_active=True,
                ),
                RoutingTemplateStep(
                    routing_template_step_id=1,
                    routing_template_id=1,
                    step_seq=10,
                    process_id=1,
                    default_process_type="INTERNAL",
                    is_active=True,
                ),
                Product(
                    product_id=1,
                    product_code="P-001",
                    product_name="제품",
                    uom="EA",
                    drawing_id=1,
                    routing_template_id=1,
                    is_active=True,
                ),
            ]
        )
        self.db.commit()

    def _seed_inventory(self, *, product_id: int, qty: int) -> None:
        self.db.add_all(
            [
                ProductInventory(
                    product_inventory_id=product_id,
                    product_id=product_id,
                    current_qty=qty,
                ),
                ProductInventoryLot(
                    product_inventory_lot_id=product_id,
                    product_id=product_id,
                    lot_no=f"STOCK-{product_id}",
                    current_qty=qty,
                ),
            ]
        )
        self.db.flush()

    def _seed_closed_order_line_with_lots(self) -> OrderLine:
        order_line = OrderLine(
            order_line_id=100,
            order_no="SO-CLOSED",
            line_no=1,
            partner_id=1,
            product_id=1,
            order_date=date(2026, 1, 1),
            due_date=date(2026, 1, 31),
            order_qty=100,
            uom="EA",
            status="CLOSED",
            is_active=True,
        )
        self.db.add(order_line)
        self.db.add_all(
            [
                Lot(
                    lot_id=101,
                    lot_no="LOT-WAITING",
                    order_line_id=100,
                    product_id=1,
                    lot_qty=100,
                    uom="EA",
                    created_date=date(2026, 1, 2),
                    due_date=date(2026, 1, 31),
                    status="WAITING",
                ),
                Lot(
                    lot_id=102,
                    lot_no="LOT-STARTED",
                    order_line_id=100,
                    product_id=1,
                    lot_qty=100,
                    uom="EA",
                    created_date=date(2026, 1, 2),
                    due_date=date(2026, 1, 31),
                    status="WAITING",
                ),
                LotStep(
                    lot_step_id=101,
                    lot_id=101,
                    step_seq=10,
                    process_id=1,
                    process_code="CUT",
                    process_name="재단",
                    process_type="INTERNAL",
                    status="WAITING",
                ),
                LotStep(
                    lot_step_id=102,
                    lot_id=102,
                    step_seq=10,
                    process_id=1,
                    process_code="CUT",
                    process_name="재단",
                    process_type="INTERNAL",
                    status="IN_PROGRESS",
                ),
            ]
        )
        self.db.flush()
        return order_line

    def _seed_closed_order_line_with_waiting_lot(self) -> OrderLine:
        order_line = OrderLine(
            order_line_id=500,
            order_no="SO-QTY-CORRECTION",
            line_no=1,
            partner_id=1,
            product_id=1,
            order_date=date(2026, 1, 1),
            due_date=date(2026, 1, 31),
            order_qty=100,
            uom="EA",
            status="CLOSED",
            is_active=True,
            decision_made=True,
            fulfillment_mode="PRODUCTION_FIRST",
            production_policy="ORDER_ONLY",
        )
        self.db.add_all(
            [
                order_line,
                Lot(
                    lot_id=501,
                    lot_no="LOT-QTY-CORRECTION",
                    order_line_id=500,
                    product_id=1,
                    lot_qty=102,
                    uom="EA",
                    created_date=date(2026, 1, 2),
                    due_date=date(2026, 1, 31),
                    status="WAITING",
                ),
                LotStep(
                    lot_step_id=501,
                    lot_id=501,
                    step_seq=10,
                    process_id=1,
                    process_code="CUT",
                    process_name="재단",
                    process_type="INTERNAL",
                    status="WAITING",
                ),
                OrderLinePlanHistory(
                    plan_history_id=501,
                    order_line_id=500,
                    plan_type="AUTO_PRODUCTION",
                    ship_target_qty=102,
                    available_inventory_qty=0,
                    stock_ship_qty=0,
                    production_qty=102,
                    is_short_close=False,
                    memo="initial plan",
                    created_by="system",
                ),
            ]
        )
        self.db.flush()
        return order_line

    def _seed_partial_stock_order_line(self) -> OrderLine:
        order_line = self._seed_closed_order_line_with_waiting_lot()
        order_line.fulfillment_mode = "INVENTORY_FIRST"

        lot = self.db.get(Lot, 501)
        lot.lot_qty = 82

        plan = self.db.get(OrderLinePlanHistory, 501)
        plan.plan_type = "PARTIAL_STOCK_PLUS_PRODUCTION"
        plan.available_inventory_qty = 20
        plan.stock_ship_qty = 20
        plan.production_qty = 82
        plan.memo = "initial partial-stock plan"

        self.db.add(
            ShipmentLine(
                shipment_line_id=601,
                order_line_id=order_line.order_line_id,
                product_id=order_line.product_id,
                source_type="STOCK",
                status="WAITING",
                ship_qty=20,
                shipped_qty=0,
                memo="reserved stock",
            )
        )
        self.db.flush()
        return order_line

    def _seed_open_order_line_without_lots(self) -> OrderLine:
        order_line = OrderLine(
            order_line_id=200,
            order_no="SO-OPEN",
            line_no=1,
            partner_id=1,
            product_id=1,
            order_date=date(2026, 1, 1),
            due_date=date(2026, 1, 31),
            order_qty=100,
            uom="EA",
            status="OPEN",
            is_active=True,
        )
        self.db.add(order_line)
        self.db.flush()
        return order_line

    def _seed_open_decision_made_order_line(self) -> OrderLine:
        order_line = OrderLine(
            order_line_id=400,
            order_no="SO-BASE-LOT",
            line_no=1,
            partner_id=1,
            product_id=1,
            order_date=date(2026, 1, 1),
            due_date=date(2026, 1, 31),
            order_qty=100,
            uom="EA",
            status="OPEN",
            is_active=True,
            decision_made=True,
            fulfillment_mode="INVENTORY_FIRST",
            production_policy="ORDER_ONLY",
        )
        self.db.add(order_line)
        self.db.flush()
        return order_line

    def _seed_deletable_order_group(self) -> None:
        self.db.add_all(
            [
                OrderLine(
                    order_line_id=300,
                    order_no="SO-DELETE",
                    line_no=1,
                    partner_id=1,
                    product_id=1,
                    order_date=date(2026, 1, 1),
                    due_date=date(2026, 1, 31),
                    order_qty=100,
                    uom="EA",
                    status="OPEN",
                    is_active=True,
                ),
                OrderLine(
                    order_line_id=301,
                    order_no="SO-DELETE",
                    line_no=2,
                    partner_id=1,
                    product_id=1,
                    order_date=date(2026, 1, 1),
                    due_date=date(2026, 1, 31),
                    order_qty=50,
                    uom="EA",
                    status="OPEN",
                    is_active=True,
                ),
                Lot(
                    lot_id=301,
                    lot_no="LOT-DELETE-1",
                    order_line_id=300,
                    product_id=1,
                    lot_qty=100,
                    uom="EA",
                    created_date=date(2026, 1, 2),
                    due_date=date(2026, 1, 31),
                    status="WAITING",
                ),
                Lot(
                    lot_id=302,
                    lot_no="LOT-DELETE-2",
                    order_line_id=301,
                    product_id=1,
                    lot_qty=50,
                    uom="EA",
                    created_date=date(2026, 1, 2),
                    due_date=date(2026, 1, 31),
                    status="CANCELED",
                ),
                LotStep(
                    lot_step_id=301,
                    lot_id=301,
                    step_seq=10,
                    process_id=1,
                    process_code="CUT",
                    process_name="?щ떒",
                    process_type="INTERNAL",
                    status="WAITING",
                ),
                LotStep(
                    lot_step_id=302,
                    lot_id=302,
                    step_seq=10,
                    process_id=1,
                    process_code="CUT",
                    process_name="?щ떒",
                    process_type="INTERNAL",
                    status="WAITING",
                ),
                OrderLinePlanHistory(
                    plan_history_id=300,
                    order_line_id=300,
                    plan_type="AUTO_PRODUCTION",
                    ship_target_qty=102,
                    available_inventory_qty=0,
                    stock_ship_qty=0,
                    production_qty=102,
                    is_short_close=False,
                ),
                ShipmentLine(
                    shipment_line_id=300,
                    order_line_id=300,
                    product_id=1,
                    product_inventory_lot_id=None,
                    lot_id=301,
                    inspection_result_id=None,
                    source_type="STOCK",
                    status="WAITING",
                    ship_qty=10,
                    shipped_qty=0,
                ),
            ]
        )
        self.db.flush()

    def _count(self, model, *conditions) -> int:
        stmt = select(func.count()).select_from(model)
        if conditions:
            stmt = stmt.where(*conditions)
        return int(self.db.execute(stmt).scalar_one() or 0)


if __name__ == "__main__":
    unittest.main()
