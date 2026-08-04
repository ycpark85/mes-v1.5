from __future__ import annotations

import unittest
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.defect_type import DefectType
from app.models.drawing import Drawing
from app.models.inspection_defect import InspectionDefect
from app.models.inspection_defect_attachment import InspectionDefectAttachment
from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction import OutsourceWorkInstruction
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.routing_template import RoutingTemplate
from app.services.lot_trace_query import get_lot_trace_detail_for_lot


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, compiler, **kw):
    return "INTEGER"


TEST_TABLE_NAMES = [
    "partner",
    "drawing",
    "routing_template",
    "product",
    "order_line",
    "order_line_plan_history",
    "lot",
    "product_inventory",
    "outsource_work_instruction",
    "outsource_work_group",
    "outsource_work_group_item",
    "inspection_schedule",
    "inspection_result",
    "defect_type",
    "inspection_defect",
    "inspection_defect_attachment",
]


class LotTraceQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        tables = [Base.metadata.tables[name] for name in TEST_TABLE_NAMES]
        Base.metadata.create_all(self.engine, tables=tables)

        SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_lot_trace_detail_builds_order_outsource_inspection_and_attachment_url(self) -> None:
        self._seed_full_trace()

        result = get_lot_trace_detail_for_lot(
            self.db,
            1,
            attachment_content_url_builder=lambda attachment_id: f"/attachments/{attachment_id}",
        )

        self.assertEqual("LOT-A", result.lot_basic.lot_no)
        self.assertFalse(result.lot_basic.is_rework)
        self.assertEqual("Customer A", result.product_order.partner_name)
        self.assertEqual("Product A", result.product_order.product_name)
        self.assertEqual(33, result.product_order.current_stock_qty)
        self.assertEqual("PARTIAL_STOCK_PLUS_PRODUCTION", result.product_order.plan_type)
        self.assertEqual("부분재고 + 부족분 생산", result.product_order.plan_type_display)
        self.assertEqual(1, len(result.outsource_works))
        self.assertEqual(10, result.outsource_works[0].group_expected_output_qty)
        self.assertEqual(8, result.outsource_works[0].confirmed_outsource_qty)
        self.assertTrue(result.progress.outsource_instruction_created)
        self.assertTrue(result.progress.outsource_work_done)
        self.assertTrue(result.progress.inspection_done)

        inspection = result.inspection
        self.assertIsNotNone(inspection)
        self.assertEqual(2, inspection.inspection_schedule_id)
        self.assertEqual(2, inspection.inspection_result_id)
        self.assertEqual(21, inspection.inspected_qty)
        self.assertEqual(15, inspection.good_qty)
        self.assertEqual(3, inspection.defect_ship_qty)
        self.assertEqual(3, inspection.defect_qty)
        self.assertEqual(2, len(inspection.defects))
        partial_defect = next(
            defect for defect in inspection.defects if defect.inspection_round == 1
        )
        final_defect = next(
            defect for defect in inspection.defects if defect.inspection_round == 2
        )
        self.assertTrue(partial_defect.is_partial)
        self.assertEqual(date(2026, 7, 9), partial_defect.inspection_date)
        self.assertEqual(2, partial_defect.defect_qty)
        self.assertFalse(final_defect.is_partial)
        self.assertEqual("Print / Blur", final_defect.defect_type_name)
        self.assertEqual("/attachments/1", final_defect.attachments[0].image_url)
        self.assertEqual(2, len(result.inspection_rounds))
        self.assertTrue(result.inspection_rounds[0].is_partial)
        self.assertFalse(result.inspection_rounds[1].is_partial)

        event_types = [item.event_type for item in result.timeline]
        self.assertIn("LOT_CREATED", event_types)
        self.assertIn("OUTSOURCE_INSTRUCTION_CREATED", event_types)
        self.assertIn("OUTSOURCE_VENDOR_RECEIVED", event_types)
        self.assertIn("OUTSOURCE_WORK_DONE", event_types)
        self.assertIn("INSPECTION_PARTIAL_DONE", event_types)
        self.assertIn("INSPECTION_FINAL_DONE", event_types)
        self.assertEqual("LOT_DONE", event_types[-1])

    def test_rework_lot_timeline_includes_parent_and_reason(self) -> None:
        self._seed_full_trace()
        self.db.add(
            Lot(
                lot_id=2,
                lot_no="LOT-A-R01",
                order_line_id=1,
                product_id=1,
                parent_lot_id=1,
                lot_qty=10,
                uom="EA",
                created_date=date(2026, 7, 11),
                created_at=datetime(2026, 7, 11, 9, 0, 0),
                due_date=date(2026, 7, 20),
                status="WAITING",
                memo="표면 주름 재작업",
            )
        )
        self.db.commit()

        result = get_lot_trace_detail_for_lot(self.db, 2)

        created = next(
            item for item in result.timeline if item.event_type == "LOT_CREATED"
        )
        self.assertEqual("재작업 LOT 생성", created.title)
        self.assertIn("부모 LOT-A", created.summary)
        self.assertEqual("표면 주름 재작업", created.memo)

    def test_lot_trace_detail_rejects_missing_lot(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            get_lot_trace_detail_for_lot(self.db, 404)

        self.assertEqual(404, ctx.exception.status_code)

    def _seed_full_trace(self) -> None:
        self.db.add_all(
            [
                Partner(
                    partner_id=1,
                    partner_type="CUSTOMER",
                    name="Customer A",
                    business_no="100-00-00001",
                    is_active=True,
                ),
                Partner(
                    partner_id=2,
                    partner_type="VENDOR",
                    name="Vendor A",
                    business_no="200-00-00001",
                    is_active=True,
                ),
                Drawing(drawing_id=1, drawing_no="DWG-A", is_active=True),
                RoutingTemplate(
                    routing_template_id=1,
                    template_code="RT-A",
                    template_name="Default",
                    is_active=True,
                ),
                Product(
                    product_id=1,
                    product_code="PRD-A",
                    product_name="Product A",
                    product_spec="Spec A",
                    uom="EA",
                    drawing_id=1,
                    routing_template_id=1,
                    panel_width_mm=100,
                    panel_length_mm=200,
                    cut_qty_per_panel=2,
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
                    memo="order memo",
                ),
                OrderLinePlanHistory(
                    plan_history_id=1,
                    order_line_id=1,
                    plan_type="AUTO_PRODUCTION",
                    ship_target_qty=80,
                    available_inventory_qty=0,
                    stock_ship_qty=0,
                    production_qty=80,
                    is_short_close=False,
                    created_at=datetime(2026, 7, 1, 8, 0, 0),
                ),
                OrderLinePlanHistory(
                    plan_history_id=2,
                    order_line_id=1,
                    plan_type="PARTIAL_STOCK_PLUS_PRODUCTION",
                    ship_target_qty=100,
                    available_inventory_qty=20,
                    stock_ship_qty=20,
                    production_qty=80,
                    is_short_close=False,
                    created_at=datetime(2026, 7, 1, 9, 0, 0),
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
                    created_at=datetime(2026, 7, 1, 10, 0, 0),
                    updated_at=datetime(2026, 7, 10, 16, 0, 0),
                ),
                ProductInventory(
                    product_inventory_id=1,
                    product_id=1,
                    current_qty=33,
                ),
                OutsourceWorkInstruction(
                    outsource_work_instruction_id=1,
                    instruction_no="OWI-1",
                    instruction_date=date(2026, 7, 2),
                    process_type="CUT",
                    partner_id=2,
                    is_bundle=False,
                    created_at=datetime(2026, 7, 2, 8, 0, 0),
                ),
                OutsourceWorkGroup(
                    outsource_work_group_id=1,
                    outsource_work_instruction_id=1,
                    group_seq="A001",
                    process_type="CUT",
                    is_bundle=False,
                    sheet_qty=5,
                    sheet_cut_count=2,
                    status="WORK_DONE",
                    work_done_sheet_qty=4,
                    remark="work memo",
                    vendor_received_at=datetime(2026, 7, 3, 8, 30, 0),
                    work_done_at=datetime(2026, 7, 4, 16, 0, 0),
                ),
                OutsourceWorkGroupItem(
                    outsource_work_group_item_id=1,
                    outsource_work_group_id=1,
                    lot_id=1,
                    cuts_per_sheet=2,
                    expected_output_qty=10,
                ),
                InspectionSchedule(
                    inspection_schedule_id=1,
                    lot_id=1,
                    inspection_date=date(2026, 7, 9),
                    status="PARTIAL_DONE",
                    day_seq=1,
                    created_at=datetime(2026, 7, 9, 8, 0, 0),
                    finished_at=datetime(2026, 7, 9, 15, 0, 0),
                ),
                InspectionSchedule(
                    inspection_schedule_id=2,
                    lot_id=1,
                    inspection_date=date(2026, 7, 10),
                    status="DONE",
                    day_seq=1,
                    created_at=datetime(2026, 7, 10, 8, 0, 0),
                    finished_at=datetime(2026, 7, 10, 15, 0, 0),
                ),
                InspectionResult(
                    inspection_result_id=1,
                    inspection_schedule_id=1,
                    good_qty=5,
                    defect_ship_qty=1,
                    defect_qty=2,
                    inspected_qty=8,
                    uninspected_qty=0,
                    discard_qty=0,
                    is_partial=True,
                    next_inspection_date=date(2026, 7, 10),
                    partial_reason="partial",
                    created_by="tester",
                    created_at=datetime(2026, 7, 9, 15, 0, 0),
                ),
                InspectionResult(
                    inspection_result_id=2,
                    inspection_schedule_id=2,
                    good_qty=10,
                    defect_ship_qty=2,
                    defect_qty=1,
                    inspected_qty=13,
                    uninspected_qty=0,
                    discard_qty=0,
                    is_partial=False,
                    memo="done",
                    created_by="tester",
                    created_at=datetime(2026, 7, 10, 15, 0, 0),
                ),
                DefectType(
                    defect_type_id=1,
                    code="PRINT_BLUR",
                    category1_name="Print",
                    category2_name="Blur",
                    is_active=True,
                ),
                InspectionDefect(
                    inspection_defect_id=1,
                    inspection_result_id=2,
                    defect_type_id=1,
                    defect_qty=1,
                    disposition="NOT_SHIPPABLE",
                    memo="defect memo",
                ),
                InspectionDefect(
                    inspection_defect_id=2,
                    inspection_result_id=1,
                    defect_type_id=1,
                    defect_qty=2,
                    disposition="NOT_SHIPPABLE",
                    memo="partial defect memo",
                ),
                InspectionDefectAttachment(
                    inspection_defect_attachment_id=1,
                    inspection_defect_id=1,
                    file_uri="defect_photos/2/photo.png",
                    file_name="photo.png",
                    mime_type="image/png",
                ),
            ]
        )
        self.db.commit()


if __name__ == "__main__":
    unittest.main()
