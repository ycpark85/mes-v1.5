from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_change_log import OutsourceWorkGroupChangeLog
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction import OutsourceWorkInstruction
from app.models.outsource_work_instruction_item import OutsourceWorkInstructionItem
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.routing_template import RoutingTemplate
from app.schemas.inspection_schedule import InspectionScheduleCreate
from app.schemas.outsource_work_instruction import (
    OutsourceWorkGroupCancelIn,
    OutsourceWorkGroupUpdateIn,
)
from app.services.inspection_schedule_service import create_inspection_schedule
from scripts.cleanup_legacy_canceled_inspection_schedules import (
    _write_backup,
    cleanup_legacy_canceled_outsource_schedules,
)
from app.services.outsource_work_group_service import cancel_work_group, update_work_group


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, compiler, **kw):
    return "JSON"


TEST_TABLE_NAMES = [
    "partner",
    "routing_template",
    "product",
    "order_line",
    "lot",
    "outsource_purchase_order",
    "outsource_purchase_order_item",
    "outsource_purchase_order_group",
    "outsource_work_instruction",
    "outsource_work_instruction_item",
    "outsource_work_group",
    "outsource_work_group_item",
    "inspection_schedule",
    "inspection_result",
    "product_inventory_movement",
    "outsource_work_group_change_log",
    "raw_material",
    "raw_material_location",
    "raw_material_inventory",
    "raw_material_inventory_lot",
    "raw_material_inventory_movement",
    "outsource_work_group_raw_material_allocation",
]


class OutsourceWorkGroupServiceTests(unittest.TestCase):
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

    def test_update_work_group_updates_group_items_and_writes_change_log(self) -> None:
        payload = OutsourceWorkGroupUpdateIn(
            sheet_qty=120,
            length_m=None,
            sheet_cut_count=3,
            fabric_lot_no=" FAB-001 ",
            remark=" updated ",
            reason="adjust qty",
        )

        with patch(
            "app.services.outsource_work_group_service.refresh_order_line_snapshots_for_work_groups"
        ) as refresh:
            work_group = update_work_group(
                self.db,
                1,
                payload,
                actor="tester",
            )

        self.assertEqual(120, work_group.sheet_qty)
        self.assertEqual(3, work_group.sheet_cut_count)
        self.assertEqual("FAB-001", work_group.fabric_lot_no)
        self.assertEqual("updated", work_group.remark)

        group_item = self.db.get(OutsourceWorkGroupItem, 1)
        self.assertEqual(3, group_item.cuts_per_sheet)
        self.assertEqual(360, group_item.expected_output_qty)

        change_logs = self.db.execute(select(OutsourceWorkGroupChangeLog)).scalars().all()
        self.assertEqual(1, len(change_logs))
        self.assertEqual("UPDATE", change_logs[0].action_type)
        self.assertEqual("tester", change_logs[0].created_by)
        refresh.assert_called_once_with(self.db, [1])

    def test_cancel_work_group_deletes_schedule_and_deactivates_instruction_item(self) -> None:
        lot = self.db.get(Lot, 1)
        lot.status = "RECEIVED"
        self.db.flush()

        payload = OutsourceWorkGroupCancelIn(reason="no longer needed")

        with patch(
            "app.services.outsource_work_group_service.refresh_order_line_snapshots_for_work_groups"
        ) as refresh:
            work_group = cancel_work_group(
                self.db,
                1,
                payload,
                actor="tester",
            )

        self.assertEqual("CANCELED", work_group.status)
        self.assertEqual("no longer needed", work_group.canceled_reason)
        self.assertIsNotNone(work_group.canceled_at)

        instruction_item = self.db.get(OutsourceWorkInstructionItem, 1)
        self.assertFalse(instruction_item.is_active)

        self.assertIsNone(self.db.get(InspectionSchedule, 1))
        self.assertEqual("WAITING", lot.status)
        change_logs = self.db.execute(select(OutsourceWorkGroupChangeLog)).scalars().all()
        self.assertEqual(1, len(change_logs))
        self.assertEqual("CANCEL", change_logs[0].action_type)
        self.assertEqual("tester", change_logs[0].created_by)
        refresh.assert_called_once_with(self.db, [1])

    def test_cancel_work_group_rejects_progressed_inspection_schedule(self) -> None:
        inspection_schedule = self.db.get(InspectionSchedule, 1)
        inspection_schedule.status = "IN_PROGRESS"
        self.db.flush()

        payload = OutsourceWorkGroupCancelIn(reason="no longer needed")

        with self.assertRaises(HTTPException) as ctx:
            cancel_work_group(
                self.db,
                1,
                payload,
                actor="tester",
            )

        self.assertEqual(409, ctx.exception.status_code)

    def test_cancel_work_group_blocks_when_inspection_result_exists(self) -> None:
        self.db.add(
            InspectionResult(
                inspection_result_id=1,
                inspection_schedule_id=1,
                good_qty=0,
                defect_ship_qty=0,
                defect_qty=0,
                inspected_qty=0,
                uninspected_qty=100,
                discard_qty=0,
                is_partial=False,
            )
        )
        self.db.commit()

        payload = OutsourceWorkGroupCancelIn(reason="no longer needed")

        with self.assertRaises(HTTPException) as ctx:
            cancel_work_group(self.db, 1, payload, actor="tester")

        self.assertEqual(409, ctx.exception.status_code)
        self.assertIsNone(self.db.get(OutsourceWorkGroup, 1).status)
        self.assertIsNotNone(self.db.get(InspectionSchedule, 1))
        self.assertIsNotNone(self.db.get(InspectionResult, 1))

    def test_cancel_work_group_blocks_when_inventory_movement_exists(self) -> None:
        self.db.add(
            ProductInventoryMovement(
                inventory_movement_id=1,
                product_id=1,
                movement_type="ADJUST_IN",
                qty=1,
                balance_after=1,
                inspection_schedule_id=1,
            )
        )
        self.db.commit()

        payload = OutsourceWorkGroupCancelIn(reason="no longer needed")

        with self.assertRaises(HTTPException) as ctx:
            cancel_work_group(self.db, 1, payload, actor="tester")

        self.assertEqual(409, ctx.exception.status_code)
        self.assertIsNone(self.db.get(OutsourceWorkGroup, 1).status)
        self.assertIsNotNone(self.db.get(InspectionSchedule, 1))
        self.assertIsNotNone(self.db.get(ProductInventoryMovement, 1))

    def test_cancel_work_group_resequences_remaining_schedule(self) -> None:
        self.db.add_all(
            [
                Lot(
                    lot_id=2,
                    lot_no="LOT-002",
                    order_line_id=1,
                    product_id=1,
                    lot_qty=50,
                    uom="EA",
                    created_date=date(2026, 1, 3),
                    due_date=date(2026, 1, 10),
                    status="WAITING",
                ),
                InspectionSchedule(
                    inspection_schedule_id=2,
                    lot_id=2,
                    inspection_date=date(2026, 1, 5),
                    status="WAITING",
                    day_seq=2,
                ),
            ]
        )
        self.db.commit()

        with patch(
            "app.services.outsource_work_group_service.refresh_order_line_snapshots_for_work_groups"
        ):
            cancel_work_group(
                self.db,
                1,
                OutsourceWorkGroupCancelIn(reason="no longer needed"),
                actor="tester",
            )

        self.assertIsNone(self.db.get(InspectionSchedule, 1))
        self.assertEqual(1, self.db.get(InspectionSchedule, 2).day_seq)

    def test_canceled_work_group_schedule_can_be_recreated_for_same_lot_and_date(self) -> None:
        with patch(
            "app.services.outsource_work_group_service.refresh_order_line_snapshots_for_work_groups"
        ):
            cancel_work_group(
                self.db,
                1,
                OutsourceWorkGroupCancelIn(reason="change vendor"),
                actor="tester",
            )

        self.db.add_all(
            [
                OutsourceWorkInstruction(
                    outsource_work_instruction_id=2,
                    instruction_no="OWI-002",
                    instruction_date=date(2026, 1, 4),
                    process_type="CUT",
                    partner_id=2,
                    is_bundle=False,
                ),
                OutsourceWorkInstructionItem(
                    outsource_work_instruction_item_id=2,
                    outsource_work_instruction_id=2,
                    lot_id=1,
                    process_type="CUT",
                    is_active=True,
                ),
                OutsourceWorkGroup(
                    outsource_work_group_id=2,
                    outsource_work_instruction_id=2,
                    group_seq="G-002",
                    process_type="CUT",
                    is_bundle=False,
                    sheet_qty=100,
                    sheet_cut_count=1,
                    status=None,
                    representative_lot_id=1,
                ),
                OutsourceWorkGroupItem(
                    outsource_work_group_item_id=2,
                    outsource_work_group_id=2,
                    lot_id=1,
                    cuts_per_sheet=1,
                    expected_output_qty=100,
                ),
            ]
        )
        self.db.flush()

        schedule = create_inspection_schedule(
            self.db,
            InspectionScheduleCreate(
                lot_id=1,
                inspection_date=date(2026, 1, 5),
                outsource_work_group_id=2,
            ),
        )

        self.assertEqual(1, schedule.lot_id)
        self.assertEqual(2, schedule.outsource_work_group_id)
        self.assertEqual(2, schedule.outsource_work_group_item_id)
        self.assertEqual("WAITING", schedule.status)

    def test_create_inspection_schedule_rejects_canceled_work_group(self) -> None:
        with patch(
            "app.services.outsource_work_group_service.refresh_order_line_snapshots_for_work_groups"
        ):
            cancel_work_group(
                self.db,
                1,
                OutsourceWorkGroupCancelIn(reason="no longer needed"),
                actor="tester",
            )

        with self.assertRaises(HTTPException) as ctx:
            create_inspection_schedule(
                self.db,
                InspectionScheduleCreate(
                    lot_id=1,
                    inspection_date=date(2026, 1, 5),
                    outsource_work_group_id=1,
                ),
            )

        self.assertEqual(409, ctx.exception.status_code)
        self.assertEqual(0, len(self.db.execute(select(InspectionSchedule)).scalars().all()))

    def test_legacy_cleanup_dry_run_does_not_delete_schedule(self) -> None:
        self.db.get(OutsourceWorkGroup, 1).status = "CANCELED"
        self.db.get(InspectionSchedule, 1).status = "CANCELED"
        self.db.commit()

        report = cleanup_legacy_canceled_outsource_schedules(self.db)

        self.assertEqual(1, report["candidate_count"])
        self.assertEqual(1, report["safe_count"])
        self.assertEqual(0, report["blocked_count"])
        self.assertFalse(report["applied"])
        self.assertIsNotNone(self.db.get(InspectionSchedule, 1))

    def test_legacy_cleanup_apply_deletes_only_expected_safe_schedule(self) -> None:
        self.db.get(OutsourceWorkGroup, 1).status = "CANCELED"
        self.db.get(InspectionSchedule, 1).status = "CANCELED"
        self.db.commit()

        report = cleanup_legacy_canceled_outsource_schedules(
            self.db,
            apply=True,
            expected_count=1,
        )

        self.assertTrue(report["applied"])
        self.assertEqual(1, report["deleted_count"])
        self.assertIsNone(self.db.get(InspectionSchedule, 1))

    def test_legacy_cleanup_apply_blocks_referenced_schedule(self) -> None:
        self.db.get(OutsourceWorkGroup, 1).status = "CANCELED"
        self.db.get(InspectionSchedule, 1).status = "CANCELED"
        self.db.add(
            InspectionResult(
                inspection_result_id=1,
                inspection_schedule_id=1,
                good_qty=0,
                defect_ship_qty=0,
                defect_qty=0,
                inspected_qty=0,
                uninspected_qty=100,
                discard_qty=0,
                is_partial=False,
            )
        )
        self.db.commit()

        with self.assertRaises(RuntimeError):
            cleanup_legacy_canceled_outsource_schedules(
                self.db,
                apply=True,
                expected_count=0,
            )

        self.assertIsNotNone(self.db.get(InspectionSchedule, 1))
        self.assertIsNotNone(self.db.get(InspectionResult, 1))

    def test_legacy_cleanup_writes_complete_recovery_snapshot(self) -> None:
        self.db.get(OutsourceWorkGroup, 1).status = "CANCELED"
        self.db.get(InspectionSchedule, 1).status = "CANCELED"
        self.db.commit()

        report = cleanup_legacy_canceled_outsource_schedules(
            self.db,
            apply=True,
            expected_count=1,
        )

        with TemporaryDirectory() as backup_root:
            backup_path = _write_backup(
                backup_root=Path(backup_root),
                app_env="test",
                database_name="test_db",
                report=report,
            )
            payload = json.loads(Path(backup_path).read_text(encoding="utf-8"))

        self.assertEqual(1, payload["candidate_count"])
        self.assertEqual(1, len(payload["rows"]))
        self.assertEqual(1, payload["rows"][0]["inspection_schedule_id"])
        self.assertEqual("CANCELED", payload["rows"][0]["status"])
        self.assertIn("created_at", payload["rows"][0])

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
                RoutingTemplate(
                    routing_template_id=1,
                    template_code="BLANK",
                    template_name="\ubb34\uc9c0",
                    is_active=True,
                ),
                Product(
                    product_id=1,
                    product_code="P-001",
                    product_name="Blank Product",
                    uom="EA",
                    drawing_id=1,
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
                Lot(
                    lot_id=1,
                    lot_no="LOT-001",
                    order_line_id=1,
                    product_id=1,
                    lot_qty=100,
                    uom="EA",
                    created_date=date(2026, 1, 3),
                    due_date=date(2026, 1, 10),
                    status="WAITING",
                ),
                OutsourceWorkInstruction(
                    outsource_work_instruction_id=1,
                    instruction_no="OWI-001",
                    instruction_date=date(2026, 1, 4),
                    process_type="CUT",
                    partner_id=2,
                    is_bundle=False,
                ),
                OutsourceWorkInstructionItem(
                    outsource_work_instruction_item_id=1,
                    outsource_work_instruction_id=1,
                    lot_id=1,
                    process_type="CUT",
                    is_active=True,
                ),
                OutsourceWorkGroup(
                    outsource_work_group_id=1,
                    outsource_work_instruction_id=1,
                    group_seq="G-001",
                    process_type="CUT",
                    is_bundle=False,
                    sheet_qty=100,
                    sheet_cut_count=1,
                    status=None,
                    representative_lot_id=1,
                ),
                OutsourceWorkGroupItem(
                    outsource_work_group_item_id=1,
                    outsource_work_group_id=1,
                    lot_id=1,
                    cuts_per_sheet=1,
                    expected_output_qty=100,
                ),
                InspectionSchedule(
                    inspection_schedule_id=1,
                    lot_id=1,
                    outsource_work_group_id=1,
                    outsource_work_group_item_id=1,
                    inspection_date=date(2026, 1, 5),
                    status="WAITING",
                    day_seq=1,
                ),
            ]
        )
        self.db.commit()


if __name__ == "__main__":
    unittest.main()
