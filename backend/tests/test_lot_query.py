from __future__ import annotations

import unittest
from datetime import date

from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.drawing import Drawing
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.lot_step import LotStep
from app.models.order_line import OrderLine
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction import OutsourceWorkInstruction
from app.models.partner import Partner
from app.models.process import Process
from app.models.product import Product
from app.models.routing_template import RoutingTemplate
from app.services.lot_query import get_lot_detail, list_lots


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, compiler, **kw):
    return "INTEGER"


TEST_TABLE_NAMES = [
    "partner",
    "drawing",
    "routing_template",
    "process",
    "product",
    "order_line",
    "lot",
    "lot_step",
    "outsource_work_instruction",
    "outsource_work_group",
    "outsource_work_group_item",
    "inspection_schedule",
]


class LotQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        tables = [Base.metadata.tables[name] for name in TEST_TABLE_NAMES]
        Base.metadata.create_all(self.engine, tables=tables)

        SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = SessionLocal()
        self._seed_lot_data()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_list_lots_builds_display_fields_and_latest_inspection_status(self) -> None:
        result = list_lots(self.db, page=1, size=20, sort="latest")

        self.assertEqual(4, result.meta.total)
        self.assertEqual(4, len(result.items))

        rework = next(item for item in result.items if item.lot_id == 2)
        self.assertEqual(2, rework.lot_id)
        self.assertEqual("REWORK", rework.lot_type)
        self.assertEqual("SO-1", rework.order_no)
        self.assertEqual("Customer A", rework.partner_name)
        self.assertEqual("PRD-A", rework.product_code)
        self.assertEqual("DONE", rework.inspection_status)
        self.assertEqual("INSPECTION_DONE", rework.list_status)

    def test_list_lots_treats_active_outsource_work_as_in_progress(self) -> None:
        result = list_lots(self.db, page=1, size=20, status="IN_PROGRESS")

        self.assertEqual(1, result.meta.total)
        self.assertEqual(3, result.items[0].lot_id)
        self.assertEqual("WAITING", result.items[0].status)
        self.assertEqual("IN_PROGRESS", result.items[0].list_status)

    def test_created_filter_excludes_active_outsource_work_lots(self) -> None:
        result = list_lots(self.db, page=1, size=20, status="CREATED")

        self.assertEqual(1, result.meta.total)
        self.assertEqual(4, result.items[0].lot_id)

    def test_list_lots_applies_keyword_filter(self) -> None:
        result = list_lots(self.db, page=1, size=20, q="LOT-PARENT")

        self.assertEqual(1, result.meta.total)
        self.assertEqual("LOT-PARENT", result.items[0].lot_no)

    def test_lot_status_constraint_accepts_workflow_states_and_rejects_unknown_state(self) -> None:
        lot = self.db.get(Lot, 1)

        for status in (
            "WAITING",
            "RECEIVED",
            "IN_PROGRESS",
            "PARTIAL_DONE",
            "DONE",
            "CANCELED",
        ):
            lot.status = status
            self.db.flush()

        lot.status = "UNKNOWN"
        with self.assertRaises(IntegrityError):
            self.db.flush()
        self.db.rollback()

    def test_list_lots_requires_full_order_number_but_keeps_partial_product_search(self) -> None:
        partial_order_result = list_lots(self.db, page=1, size=20, q="SO-")
        exact_order_result = list_lots(self.db, page=1, size=20, q=" so-1 ")
        partial_product_result = list_lots(self.db, page=1, size=20, q="RD-A")

        self.assertEqual(0, partial_order_result.meta.total)
        self.assertEqual(4, exact_order_result.meta.total)
        self.assertEqual(4, partial_product_result.meta.total)

    def test_get_lot_detail_builds_order_product_partner_and_steps(self) -> None:
        result = get_lot_detail(self.db, 1)

        self.assertEqual("LOT-PARENT", result.lot_no)
        self.assertEqual("SO-1", result.order_no)
        self.assertEqual(1, result.line_no)
        self.assertEqual("Customer A", result.partner_name)
        self.assertEqual("PRD-A", result.product_code)
        self.assertEqual("Product A", result.product_name)
        self.assertEqual(1, len(result.steps))
        self.assertEqual("CUT", result.steps[0].process_code)

    def test_get_lot_detail_rejects_missing_lot(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            get_lot_detail(self.db, 404)

        self.assertEqual(404, ctx.exception.status_code)

    def _seed_lot_data(self) -> None:
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
                Process(
                    process_id=1,
                    process_code="CUT",
                    process_name="Cutting",
                    process_type="OUTSOURCE",
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
                    order_qty=10,
                    uom="EA",
                    status="CLOSED",
                    is_active=True,
                ),
                Lot(
                    lot_id=1,
                    lot_no="LOT-PARENT",
                    order_line_id=1,
                    product_id=1,
                    lot_qty=10,
                    uom="EA",
                    created_date=date(2026, 7, 1),
                    due_date=date(2026, 7, 20),
                    status="DONE",
                ),
                Lot(
                    lot_id=2,
                    lot_no="LOT-REWORK",
                    order_line_id=1,
                    product_id=1,
                    parent_lot_id=1,
                    memo="test rework reason",
                    lot_qty=3,
                    uom="EA",
                    created_date=date(2026, 7, 11),
                    due_date=date(2026, 7, 20),
                    status="WAITING",
                ),
                Lot(
                    lot_id=3,
                    lot_no="LOT-OUTSOURCE",
                    order_line_id=1,
                    product_id=1,
                    lot_qty=4,
                    uom="EA",
                    created_date=date(2026, 7, 12),
                    due_date=date(2026, 7, 20),
                    status="WAITING",
                ),
                Lot(
                    lot_id=4,
                    lot_no="LOT-CREATED",
                    order_line_id=1,
                    product_id=1,
                    lot_qty=2,
                    uom="EA",
                    created_date=date(2026, 7, 13),
                    due_date=date(2026, 7, 20),
                    status="WAITING",
                ),
                LotStep(
                    lot_step_id=1,
                    lot_id=1,
                    step_seq=10,
                    process_id=1,
                    process_code="CUT",
                    process_name="Cutting",
                    process_type="OUTSOURCE",
                    status="WAITING",
                ),
                OutsourceWorkInstruction(
                    outsource_work_instruction_id=1,
                    instruction_no="OWI-1",
                    instruction_date=date(2026, 7, 12),
                    process_type="CUT",
                    partner_id=2,
                    is_bundle=False,
                ),
                OutsourceWorkGroup(
                    outsource_work_group_id=1,
                    outsource_work_instruction_id=1,
                    group_seq="A001",
                    process_type="CUT",
                    is_bundle=False,
                    sheet_qty=2,
                    sheet_cut_count=2,
                    representative_lot_id=3,
                    status=None,
                ),
                OutsourceWorkGroupItem(
                    outsource_work_group_item_id=1,
                    outsource_work_group_id=1,
                    lot_id=3,
                    cuts_per_sheet=2,
                    expected_output_qty=4,
                ),
                InspectionSchedule(
                    inspection_schedule_id=1,
                    lot_id=2,
                    inspection_date=date(2026, 7, 12),
                    status="WAITING",
                    day_seq=1,
                ),
                InspectionSchedule(
                    inspection_schedule_id=2,
                    lot_id=2,
                    inspection_date=date(2026, 7, 13),
                    status="DONE",
                    day_seq=1,
                ),
            ]
        )
        self.db.commit()


if __name__ == "__main__":
    unittest.main()
