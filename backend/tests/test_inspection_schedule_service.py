from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.drawing import Drawing
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.outsource_purchase_order import OutsourcePurchaseOrder
from app.models.outsource_purchase_order_item import OutsourcePurchaseOrderItem
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction import OutsourceWorkInstruction
from app.models.partner import Partner
from app.models.product import Product
from app.models.routing_template import RoutingTemplate
from app.schemas.inspection_schedule import (
    InspectionScheduleCreate,
    InspectionScheduleReorderIn,
    InspectionScheduleUpdate,
)
from app.services import inspection_schedule_service
from app.services.inspection_schedule_service import (
    cancel_inspection_schedule,
    create_inspection_schedule,
    receive_inspection_schedule,
    reorder_inspection_schedules,
    start_inspection_schedule,
    update_inspection_schedule,
)


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, compiler, **kw):
    return "JSON"


TEST_TABLE_NAMES = [
    "partner",
    "drawing",
    "routing_template",
    "product",
    "order_line",
    "lot",
    "outsource_purchase_order",
    "outsource_purchase_order_item",
    "outsource_work_instruction",
    "outsource_work_group",
    "outsource_work_group_item",
    "inspection_schedule",
]


class InspectionScheduleServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        tables = [Base.metadata.tables[name] for name in TEST_TABLE_NAMES]
        Base.metadata.create_all(self.engine, tables=tables)

        SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = SessionLocal()
        self._seed_data()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_start_inspection_schedule_sets_in_progress_and_syncs_lot(self) -> None:
        with patch.object(
            inspection_schedule_service,
            "refresh_order_line_snapshots_for_lots",
        ) as refresh:
            schedule = start_inspection_schedule(
                self.db,
                1,
                today=date(2026, 1, 5),
            )

        self.assertEqual("IN_PROGRESS", schedule.status)
        self.assertIsNotNone(schedule.started_at)
        self.assertEqual("IN_PROGRESS", self.db.get(Lot, 1).status)
        refresh.assert_called_once_with(self.db, {1})

    def test_start_inspection_schedule_rejects_non_today_schedule(self) -> None:
        context_token = inspection_schedule_service.request_id_context.set(
            "inspection-date-test"
        )
        try:
            with self.assertLogs("mes.inspection", level="WARNING") as logs:
                with self.assertRaises(HTTPException) as ctx:
                    start_inspection_schedule(
                        self.db,
                        1,
                        today=date(2026, 1, 6),
                    )
        finally:
            inspection_schedule_service.request_id_context.reset(context_token)

        self.assertEqual(409, ctx.exception.status_code)
        self.assertEqual(
            (
                "오늘 스케줄만 검수를 시작할 수 있습니다. "
                "선택 검수일: 2026-01-05, 서버 기준일: 2026-01-06"
            ),
            ctx.exception.detail,
        )
        self.assertIn("request_id=inspection-date-test", logs.output[0])
        self.assertIn("schedule_id=1", logs.output[0])
        self.assertIn("inspection_date=2026-01-05", logs.output[0])
        self.assertIn("business_date=2026-01-06", logs.output[0])

    def test_inspection_start_uses_database_korea_date_for_postgresql(self) -> None:
        db = Mock()
        db.get_bind.return_value.dialect.name = "postgresql"
        db.execute.return_value.scalar_one.return_value = date(2026, 8, 19)

        with patch.object(
            inspection_schedule_service,
            "korea_today",
            return_value=date(2026, 8, 20),
        ):
            with self.assertLogs("mes.inspection", level="ERROR") as logs:
                business_date = (
                    inspection_schedule_service._resolve_inspection_start_business_date(
                        db,
                        today=None,
                    )
                )

        self.assertEqual(date(2026, 8, 19), business_date)
        db.execute.assert_called_once_with(
            inspection_schedule_service._KOREA_BUSINESS_DATE_SQL
        )
        self.assertIn("database_date=2026-08-19", logs.output[0])
        self.assertIn("application_date=2026-08-20", logs.output[0])
        self.assertIn("selected_source=database", logs.output[0])

    def test_inspection_start_uses_application_korea_date_for_non_postgresql(self) -> None:
        with patch.object(
            inspection_schedule_service,
            "korea_today",
            return_value=date(2026, 8, 19),
        ):
            business_date = (
                inspection_schedule_service._resolve_inspection_start_business_date(
                    self.db,
                    today=None,
                )
            )

        self.assertEqual(date(2026, 8, 19), business_date)

    def test_create_inspection_schedule_creates_single_schedule(self) -> None:
        payload = InspectionScheduleCreate(
            lot_id=4,
            inspection_date=date(2026, 1, 7),
            memo="single",
        )

        schedule = create_inspection_schedule(self.db, payload)

        self.assertEqual(4, schedule.lot_id)
        self.assertEqual(date(2026, 1, 7), schedule.inspection_date)
        self.assertEqual("single", schedule.memo)
        self.assertEqual("WAITING", schedule.status)

    def test_create_inspection_schedule_creates_outsource_work_group_schedule(self) -> None:
        payload = InspectionScheduleCreate(
            lot_id=2,
            inspection_date=date(2026, 1, 7),
            outsource_work_group_id=1,
        )

        schedule = create_inspection_schedule(self.db, payload)

        self.assertEqual(2, schedule.lot_id)
        self.assertEqual(1, schedule.outsource_work_group_id)
        self.assertEqual(1, schedule.outsource_work_group_item_id)

    def test_update_inspection_schedule_changes_date_without_changing_memo(self) -> None:
        original_memo = self.db.get(InspectionSchedule, 2).memo
        payload = InspectionScheduleUpdate(
            inspection_date=date(2026, 1, 7),
        )

        schedule = update_inspection_schedule(
            self.db,
            2,
            payload,
            today=date(2026, 1, 1),
        )

        self.assertEqual(date(2026, 1, 7), schedule.inspection_date)
        self.assertEqual(original_memo, schedule.memo)
        self.assertEqual(1, schedule.day_seq)

    def test_receive_inspection_only_schedule_sets_received(self) -> None:
        with patch.object(
            inspection_schedule_service,
            "refresh_order_line_snapshots_for_lots",
        ) as refresh:
            schedule = receive_inspection_schedule(self.db, 4)

        self.assertEqual("RECEIVED", schedule.status)
        self.assertIsNotNone(schedule.received_at)
        self.assertEqual("RECEIVED", self.db.get(Lot, 3).status)
        refresh.assert_called_once_with(self.db, {3})

    def test_receive_outsource_work_group_schedule_sets_group_waiting_schedules_received(self) -> None:
        with patch.object(
            inspection_schedule_service,
            "refresh_order_line_snapshots_for_lots",
        ) as refresh:
            schedule = receive_inspection_schedule(self.db, 2)

        self.assertEqual("RECEIVED", schedule.status)
        self.assertEqual("RECEIVED", self.db.get(Lot, 2).status)
        refresh.assert_called_once_with(self.db, {2})

    def test_receive_purchase_order_item_schedule_sets_received(self) -> None:
        with patch.object(
            inspection_schedule_service,
            "refresh_order_line_snapshots_for_lots",
        ) as refresh:
            schedule = receive_inspection_schedule(self.db, 5)

        self.assertEqual("RECEIVED", schedule.status)
        self.assertEqual("RECEIVED", self.db.get(Lot, 4).status)
        refresh.assert_called_once_with(self.db, {4})

    def test_cancel_inspection_schedule_sets_canceled_and_syncs_lot(self) -> None:
        with patch.object(
            inspection_schedule_service,
            "refresh_order_line_snapshots_for_lots",
        ) as refresh:
            schedule = cancel_inspection_schedule(self.db, 1)

        self.assertEqual("CANCELED", schedule.status)
        self.assertEqual("WAITING", self.db.get(Lot, 1).status)
        refresh.assert_called_once_with(self.db, {1})

    def test_reorder_inspection_schedules_updates_day_seq(self) -> None:
        payload = InspectionScheduleReorderIn(
            inspection_date=date(2026, 1, 5),
            ordered_ids=[2, 1],
        )

        rows = reorder_inspection_schedules(self.db, payload)

        self.assertEqual([2, 1], [row.inspection_schedule_id for row in rows])
        self.assertEqual(2, self.db.get(InspectionSchedule, 1).day_seq)
        self.assertEqual(1, self.db.get(InspectionSchedule, 2).day_seq)

    def _seed_data(self) -> None:
        self.db.add_all(
            [
                Partner(
                    partner_id=1,
                    partner_type="CUSTOMER",
                    name="Customer",
                    business_no="C-001",
                    is_active=True,
                ),
                Partner(
                    partner_id=2,
                    partner_type="VENDOR",
                    name="Vendor",
                    business_no="V-001",
                    is_active=True,
                ),
                Drawing(
                    drawing_id=1,
                    drawing_no="D-001",
                    is_active=True,
                ),
                Drawing(
                    drawing_id=2,
                    drawing_no="D-002",
                    is_active=True,
                ),
                Drawing(
                    drawing_id=3,
                    drawing_no="D-003",
                    is_active=True,
                ),
                Drawing(
                    drawing_id=4,
                    drawing_no="D-004",
                    is_active=True,
                ),
                RoutingTemplate(
                    routing_template_id=1,
                    template_code="CUT",
                    template_name="CUT",
                    is_active=True,
                ),
                RoutingTemplate(
                    routing_template_id=2,
                    template_code="INSPECTION_ONLY",
                    template_name="\uac80\uc218\ub9cc\uc9c4\ud589",
                    is_active=True,
                ),
                Product(
                    product_id=1,
                    product_code="P-001",
                    product_name="Product 1",
                    uom="EA",
                    drawing_id=1,
                    routing_template_id=1,
                    is_active=True,
                ),
                Product(
                    product_id=2,
                    product_code="P-002",
                    product_name="Product 2",
                    uom="EA",
                    drawing_id=2,
                    routing_template_id=1,
                    is_active=True,
                ),
                Product(
                    product_id=3,
                    product_code="P-003",
                    product_name="Product 3",
                    uom="EA",
                    drawing_id=3,
                    routing_template_id=2,
                    is_active=True,
                ),
                Product(
                    product_id=4,
                    product_code="P-004",
                    product_name="Product 4",
                    uom="EA",
                    drawing_id=4,
                    routing_template_id=1,
                    is_active=True,
                ),
                OrderLine(
                    order_line_id=1,
                    order_no="SO-001",
                    line_no=1,
                    partner_id=1,
                    product_id=1,
                    order_date=date(2026, 1, 1),
                    due_date=date(2026, 1, 10),
                    order_qty=100,
                    uom="EA",
                    status="OPEN",
                    is_active=True,
                ),
                OrderLine(
                    order_line_id=2,
                    order_no="SO-002",
                    line_no=1,
                    partner_id=1,
                    product_id=2,
                    order_date=date(2026, 1, 1),
                    due_date=date(2026, 1, 10),
                    order_qty=100,
                    uom="EA",
                    status="OPEN",
                    is_active=True,
                ),
                OrderLine(
                    order_line_id=3,
                    order_no="SO-003",
                    line_no=1,
                    partner_id=1,
                    product_id=3,
                    order_date=date(2026, 1, 1),
                    due_date=date(2026, 1, 10),
                    order_qty=100,
                    uom="EA",
                    status="OPEN",
                    is_active=True,
                ),
                OrderLine(
                    order_line_id=4,
                    order_no="SO-004",
                    line_no=1,
                    partner_id=1,
                    product_id=4,
                    order_date=date(2026, 1, 1),
                    due_date=date(2026, 1, 10),
                    order_qty=100,
                    uom="EA",
                    status="OPEN",
                    is_active=True,
                ),
                Lot(
                    lot_id=1,
                    lot_no="LOT-001",
                    order_line_id=1,
                    product_id=1,
                    lot_qty=100,
                    uom="EA",
                    created_date=date(2026, 1, 2),
                    due_date=date(2026, 1, 10),
                    status="RECEIVED",
                ),
                Lot(
                    lot_id=2,
                    lot_no="LOT-002",
                    order_line_id=2,
                    product_id=2,
                    lot_qty=100,
                    uom="EA",
                    created_date=date(2026, 1, 2),
                    due_date=date(2026, 1, 10),
                    status="WAITING",
                ),
                Lot(
                    lot_id=3,
                    lot_no="LOT-003",
                    order_line_id=3,
                    product_id=3,
                    lot_qty=100,
                    uom="EA",
                    created_date=date(2026, 1, 2),
                    due_date=date(2026, 1, 10),
                    status="WAITING",
                ),
                Lot(
                    lot_id=4,
                    lot_no="LOT-004",
                    order_line_id=4,
                    product_id=4,
                    lot_qty=100,
                    uom="EA",
                    created_date=date(2026, 1, 2),
                    due_date=date(2026, 1, 10),
                    status="WAITING",
                ),
                OutsourcePurchaseOrder(
                    outsource_purchase_order_id=1,
                    purchase_order_no="OPO-001",
                    purchase_order_date=date(2026, 1, 3),
                    process_type="CUT",
                    outsource_partner_id=2,
                    inbound_partner_id=2,
                    qty=100,
                ),
                OutsourcePurchaseOrderItem(
                    outsource_purchase_order_item_id=1,
                    outsource_purchase_order_id=1,
                    lot_id=4,
                    item_seq=1,
                    qty=100,
                    status="SHIPPED",
                ),
                OutsourceWorkInstruction(
                    outsource_work_instruction_id=1,
                    instruction_no="OWI-001",
                    instruction_date=date(2026, 1, 3),
                    process_type="CUT",
                    partner_id=2,
                    is_bundle=False,
                ),
                OutsourceWorkGroup(
                    outsource_work_group_id=1,
                    outsource_work_instruction_id=1,
                    group_seq="G-001",
                    process_type="CUT",
                    is_bundle=False,
                    sheet_qty=100,
                    sheet_cut_count=1,
                    status="SHIPPED",
                    representative_lot_id=2,
                ),
                OutsourceWorkGroupItem(
                    outsource_work_group_item_id=1,
                    outsource_work_group_id=1,
                    lot_id=2,
                    cuts_per_sheet=1,
                    expected_output_qty=100,
                ),
                InspectionSchedule(
                    inspection_schedule_id=1,
                    lot_id=1,
                    inspection_date=date(2026, 1, 5),
                    status="RECEIVED",
                    day_seq=1,
                ),
                InspectionSchedule(
                    inspection_schedule_id=2,
                    lot_id=2,
                    outsource_work_group_id=1,
                    outsource_work_group_item_id=1,
                    inspection_date=date(2026, 1, 5),
                    status="WAITING",
                    day_seq=2,
                ),
                InspectionSchedule(
                    inspection_schedule_id=3,
                    lot_id=1,
                    inspection_date=date(2026, 1, 6),
                    status="WAITING",
                    day_seq=1,
                ),
                InspectionSchedule(
                    inspection_schedule_id=4,
                    lot_id=3,
                    inspection_date=date(2026, 1, 6),
                    status="WAITING",
                    day_seq=3,
                ),
                InspectionSchedule(
                    inspection_schedule_id=5,
                    lot_id=4,
                    inspection_date=date(2026, 1, 6),
                    status="WAITING",
                    day_seq=4,
                ),
            ]
        )
        self.db.commit()


if __name__ == "__main__":
    unittest.main()
