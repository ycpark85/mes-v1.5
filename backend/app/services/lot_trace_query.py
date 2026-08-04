from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.defect_type import DefectType
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
from app.schemas.lot import (
    LotTraceBasicOut,
    LotTraceDefectAttachmentOut,
    LotTraceDetailOut,
    LotTraceInspectionDefectOut,
    LotTraceInspectionOut,
    LotTraceInspectionRoundOut,
    LotTraceOutsourceWorkOut,
    LotTraceProductOrderOut,
    LotTraceProgressOut,
    LotTraceTimelineItemOut,
)


def get_lot_trace_detail_for_lot(
    db: Session,
    lot_id: int,
    *,
    attachment_content_url_builder: Callable[[int], str] | None = None,
) -> LotTraceDetailOut:
    row = (
        db.execute(
            select(Lot, OrderLine, Product, Partner)
            .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
            .join(Product, Product.product_id == Lot.product_id)
            .join(Partner, Partner.partner_id == OrderLine.partner_id)
            .where(Lot.lot_id == lot_id)
        )
        .one_or_none()
    )

    if row is None:
        raise HTTPException(status_code=404, detail="LOT not found")

    lot, order_line, product, partner = row
    latest_plan_history = _get_latest_plan_history(db, order_line.order_line_id)
    current_stock_qty = _get_current_stock_qty(db, product.product_id)
    parent_lot_no = _get_parent_lot_no(db, lot)
    outsource_works = _build_outsource_works(db, lot_id)
    inspection, inspection_rounds = _build_inspection_details(
        db,
        lot_id,
        attachment_content_url_builder=attachment_content_url_builder,
    )
    timeline = _build_lot_timeline(
        lot=lot,
        parent_lot_no=parent_lot_no,
        outsource_works=outsource_works,
        inspection_rounds=inspection_rounds,
    )

    return LotTraceDetailOut(
        progress=_build_lot_trace_progress(
            outsource_works=outsource_works,
            inspection=inspection,
        ),
        lot_basic=LotTraceBasicOut(
            lot_id=lot.lot_id,
            lot_no=lot.lot_no,
            status=lot.status,
            is_rework=lot.parent_lot_id is not None,
            parent_lot_id=lot.parent_lot_id,
            parent_lot_no=parent_lot_no,
            lot_qty=lot.lot_qty,
            uom=lot.uom,
            created_date=lot.created_date,
            due_date=lot.due_date,
            memo=lot.memo,
        ),
        product_order=LotTraceProductOrderOut(
            order_line_id=order_line.order_line_id,
            order_no=order_line.order_no,
            line_no=order_line.line_no,
            partner_id=partner.partner_id,
            partner_name=partner.name,
            product_id=product.product_id,
            product_code=product.product_code,
            product_name=product.product_name,
            product_spec=product.product_spec,
            panel_width_mm=product.panel_width_mm,
            panel_length_mm=product.panel_length_mm,
            cut_qty_per_panel=product.cut_qty_per_panel,
            current_stock_qty=current_stock_qty,
            order_qty=order_line.order_qty,
            order_date=order_line.order_date,
            due_date=order_line.due_date,
            memo=order_line.memo,
            plan_type=latest_plan_history.plan_type if latest_plan_history else None,
            plan_type_display=(
                _to_plan_type_display(latest_plan_history.plan_type)
                if latest_plan_history
                else None
            ),
            plan_ship_target_qty=(
                latest_plan_history.ship_target_qty
                if latest_plan_history
                else None
            ),
            plan_available_inventory_qty=(
                latest_plan_history.available_inventory_qty
                if latest_plan_history
                else None
            ),
            plan_stock_ship_qty=(
                latest_plan_history.stock_ship_qty
                if latest_plan_history
                else None
            ),
            plan_production_qty=(
                latest_plan_history.production_qty
                if latest_plan_history
                else None
            ),
            plan_is_short_close=(
                latest_plan_history.is_short_close
                if latest_plan_history
                else None
            ),
        ),
        outsource_works=outsource_works,
        inspection=inspection,
        inspection_rounds=inspection_rounds,
        timeline=timeline,
    )


def _get_latest_plan_history(
    db: Session,
    order_line_id: int,
) -> OrderLinePlanHistory | None:
    return (
        db.execute(
            select(OrderLinePlanHistory)
            .where(OrderLinePlanHistory.order_line_id == order_line_id)
            .order_by(
                OrderLinePlanHistory.created_at.desc(),
                OrderLinePlanHistory.plan_history_id.desc(),
            )
            .limit(1)
        )
        .scalar_one_or_none()
    )


def _get_current_stock_qty(db: Session, product_id: int) -> int:
    current_stock_qty = db.execute(
        select(ProductInventory.current_qty).where(
            ProductInventory.product_id == product_id
        )
    ).scalar_one_or_none()

    return int(current_stock_qty or 0)


def _get_parent_lot_no(db: Session, lot: Lot) -> str | None:
    if not lot.parent_lot_id:
        return None

    parent_lot = db.get(Lot, lot.parent_lot_id)
    return parent_lot.lot_no if parent_lot else None


def _build_outsource_works(
    db: Session,
    lot_id: int,
) -> list[LotTraceOutsourceWorkOut]:
    outsource_rows = (
        db.execute(
            select(
                OutsourceWorkGroup,
                OutsourceWorkGroupItem,
                OutsourceWorkInstruction,
            )
            .join(
                OutsourceWorkGroupItem,
                OutsourceWorkGroupItem.outsource_work_group_id
                == OutsourceWorkGroup.outsource_work_group_id,
            )
            .join(
                OutsourceWorkInstruction,
                OutsourceWorkInstruction.outsource_work_instruction_id
                == OutsourceWorkGroup.outsource_work_instruction_id,
            )
            .where(OutsourceWorkGroupItem.lot_id == lot_id)
            .order_by(
                OutsourceWorkInstruction.instruction_date.desc(),
                OutsourceWorkInstruction.instruction_no.desc(),
                OutsourceWorkGroup.group_seq.asc(),
                OutsourceWorkGroupItem.outsource_work_group_item_id.asc(),
            )
        )
        .all()
    )

    outsource_works: list[LotTraceOutsourceWorkOut] = []

    for work_group, work_group_item, instruction in outsource_rows:
        group_expected_output_qty = (
            int(work_group.sheet_qty) * int(work_group.sheet_cut_count)
        )

        confirmed_outsource_qty = None
        if work_group.work_done_sheet_qty is not None:
            confirmed_outsource_qty = (
                int(work_group.work_done_sheet_qty)
                * int(work_group.sheet_cut_count)
            )

        outsource_works.append(
            LotTraceOutsourceWorkOut(
                outsource_work_group_id=work_group.outsource_work_group_id,
                outsource_work_group_item_id=work_group_item.outsource_work_group_item_id,
                outsource_work_instruction_id=instruction.outsource_work_instruction_id,
                instruction_no=instruction.instruction_no,
                instruction_date=instruction.instruction_date,
                process_type=work_group.process_type,
                group_seq=work_group.group_seq,
                is_bundle=work_group.is_bundle,
                fabric_lot_no=work_group.fabric_lot_no,
                length_m=work_group.length_m,
                sheet_qty=work_group.sheet_qty,
                sheet_cut_count=work_group.sheet_cut_count,
                cuts_per_sheet=work_group_item.cuts_per_sheet,
                expected_output_qty=work_group_item.expected_output_qty,
                group_expected_output_qty=group_expected_output_qty,
                work_done_sheet_qty=work_group.work_done_sheet_qty,
                confirmed_outsource_qty=confirmed_outsource_qty,
                status=work_group.status,
                vendor_received_at=work_group.vendor_received_at,
                work_done_at=work_group.work_done_at,
                shipped_at=work_group.shipped_at,
                remark=work_group.remark,
                work_done_remark=work_group.work_done_remark,
                instruction_created_at=instruction.created_at,
            )
        )

    return outsource_works


def _build_inspection_details(
    db: Session,
    lot_id: int,
    *,
    attachment_content_url_builder: Callable[[int], str] | None,
) -> tuple[LotTraceInspectionOut | None, list[LotTraceInspectionRoundOut]]:
    inspection_rows = (
        db.execute(
            select(InspectionSchedule, InspectionResult)
            .join(
                InspectionResult,
                InspectionResult.inspection_schedule_id
                == InspectionSchedule.inspection_schedule_id,
                isouter=True,
            )
            .where(
                InspectionSchedule.lot_id == lot_id,
            )
            .order_by(
                InspectionSchedule.inspection_date.asc(),
                InspectionSchedule.inspection_schedule_id.asc(),
            )
        )
        .all()
    )

    completed_inspection_rows = [
        (schedule, result)
        for schedule, result in inspection_rows
        if result is not None and schedule.status in ("PARTIAL_DONE", "DONE")
    ]

    inspection_rounds = [
        LotTraceInspectionRoundOut(
            inspection_round=index,
            inspection_schedule_id=schedule.inspection_schedule_id,
            inspection_result_id=(result.inspection_result_id if result else None),
            inspection_date=schedule.inspection_date,
            schedule_status=schedule.status,
            received_at=schedule.received_at,
            started_at=schedule.started_at,
            finished_at=schedule.finished_at,
            schedule_created_at=schedule.created_at,
            inspected_qty=(int(result.inspected_qty or 0) if result else None),
            good_qty=(int(result.good_qty or 0) if result else None),
            defect_qty=(int(result.defect_qty or 0) if result else None),
            defect_ship_qty=(int(result.defect_ship_qty or 0) if result else None),
            is_partial=(result.is_partial if result else None),
            next_inspection_date=(result.next_inspection_date if result else None),
            partial_reason=(result.partial_reason if result else None),
            memo=(result.memo if result else schedule.memo),
            created_by=(result.created_by if result else None),
            result_created_at=(result.created_at if result else None),
        )
        for index, (schedule, result) in enumerate(inspection_rows, start=1)
    ]

    if completed_inspection_rows:
        inspection_schedule, inspection_result = completed_inspection_rows[-1]
    elif inspection_rows:
        inspection_schedule, inspection_result = inspection_rows[-1]
    else:
        return None, inspection_rounds

    result_rows_for_totals = completed_inspection_rows

    if not result_rows_for_totals and inspection_result is not None:
        result_rows_for_totals = [(inspection_schedule, inspection_result)]

    result_ids = [
        result.inspection_result_id
        for _, result in result_rows_for_totals
        if result is not None
    ]
    result_context_by_id = {
        result.inspection_result_id: (
            index,
            schedule.inspection_date,
            bool(result.is_partial),
        )
        for index, (schedule, result) in enumerate(inspection_rows, start=1)
        if result is not None
    }

    defects = _build_inspection_defects(
        db,
        result_ids,
        result_context_by_id=result_context_by_id,
        attachment_content_url_builder=attachment_content_url_builder,
    )

    inspection = LotTraceInspectionOut(
        inspection_schedule_id=inspection_schedule.inspection_schedule_id,
        inspection_date=inspection_schedule.inspection_date,
        schedule_status=inspection_schedule.status,
        received_at=inspection_schedule.received_at,
        started_at=inspection_schedule.started_at,
        finished_at=inspection_schedule.finished_at,
        inspection_result_id=(
            inspection_result.inspection_result_id
            if inspection_result
            else None
        ),
        inspected_qty=_sum_result_qty(result_rows_for_totals, "inspected_qty"),
        good_qty=_sum_result_qty(result_rows_for_totals, "good_qty"),
        defect_qty=_sum_result_qty(result_rows_for_totals, "defect_qty"),
        defect_ship_qty=_sum_result_qty(result_rows_for_totals, "defect_ship_qty"),
        is_partial=inspection_result.is_partial if inspection_result else None,
        next_inspection_date=(
            inspection_result.next_inspection_date
            if inspection_result
            else None
        ),
        partial_reason=(
            inspection_result.partial_reason
            if inspection_result
            else None
        ),
        memo=inspection_result.memo if inspection_result else None,
        created_by=inspection_result.created_by if inspection_result else None,
        result_created_at=(
            inspection_result.created_at
            if inspection_result
            else None
        ),
        defects=defects,
    )

    return inspection, inspection_rounds


def _build_lot_timeline(
    *,
    lot: Lot,
    parent_lot_no: str | None,
    outsource_works: list[LotTraceOutsourceWorkOut],
    inspection_rounds: list[LotTraceInspectionRoundOut],
) -> list[LotTraceTimelineItemOut]:
    lot_kind = "재작업 LOT" if lot.parent_lot_id else "기본 LOT"
    lot_summary = f"{lot.lot_no} / {lot_kind} / 계획수량 {int(lot.lot_qty):,} {lot.uom}"
    if lot.parent_lot_id:
        lot_summary = f"{lot_summary} / 부모 {parent_lot_no or lot.parent_lot_id}"

    items = [
        LotTraceTimelineItemOut(
            event_type="LOT_CREATED",
            event_at=lot.created_at,
            title="재작업 LOT 생성" if lot.parent_lot_id else "LOT 생성",
            summary=lot_summary,
            status="DONE",
            memo=lot.memo if lot.parent_lot_id else None,
            ref_type="LOT",
            ref_id=lot.lot_id,
        )
    ]

    for work in outsource_works:
        instruction_at = work.instruction_created_at
        if instruction_at is not None:
            items.append(
                LotTraceTimelineItemOut(
                    event_type="OUTSOURCE_INSTRUCTION_CREATED",
                    event_at=instruction_at,
                    title="외주 작업 지시",
                    summary=(
                        f"{work.instruction_no} / {work.process_type} / "
                        f"예상수량 {int(work.expected_output_qty or 0):,}"
                    ),
                    status="DONE",
                    memo=work.remark,
                    ref_type="OUTSOURCE_WORK_GROUP",
                    ref_id=work.outsource_work_group_id,
                )
            )

        if work.vendor_received_at is not None:
            items.append(
                LotTraceTimelineItemOut(
                    event_type="OUTSOURCE_VENDOR_RECEIVED",
                    event_at=work.vendor_received_at,
                    title="업체 입고",
                    summary=(
                        f"{work.process_type} / 원단 LOT "
                        f"{work.fabric_lot_no or '-'}"
                    ),
                    status="DONE",
                    ref_type="OUTSOURCE_WORK_GROUP",
                    ref_id=work.outsource_work_group_id,
                )
            )

        if work.work_done_at is not None:
            items.append(
                LotTraceTimelineItemOut(
                    event_type="OUTSOURCE_WORK_DONE",
                    event_at=work.work_done_at,
                    title="외주 작업 완료",
                    summary=(
                        f"{work.process_type} / 완료수량 "
                        f"{int(work.confirmed_outsource_qty or 0):,}"
                    ),
                    status="DONE",
                    memo=work.work_done_remark,
                    ref_type="OUTSOURCE_WORK_GROUP",
                    ref_id=work.outsource_work_group_id,
                )
            )

        if work.shipped_at is not None:
            items.append(
                LotTraceTimelineItemOut(
                    event_type="OUTSOURCE_SHIPPED",
                    event_at=work.shipped_at,
                    title="외주 출고",
                    summary=f"{work.process_type} / {work.instruction_no}",
                    status="DONE",
                    ref_type="OUTSOURCE_WORK_GROUP",
                    ref_id=work.outsource_work_group_id,
                )
            )

    for round_item in inspection_rounds:
        if round_item.inspection_result_id is not None:
            is_partial = round_item.is_partial is True
            items.append(
                LotTraceTimelineItemOut(
                    event_type=(
                        "INSPECTION_PARTIAL_DONE"
                        if is_partial
                        else "INSPECTION_FINAL_DONE"
                    ),
                    event_at=(
                        round_item.finished_at
                        or round_item.result_created_at
                        or round_item.schedule_created_at
                    ),
                    title=(
                        f"{round_item.inspection_round}차 분할검수"
                        if is_partial
                        else f"{round_item.inspection_round}차 최종검수"
                    ),
                    summary=(
                        f"검수 {int(round_item.inspected_qty or 0):,} / "
                        f"양품 {int(round_item.good_qty or 0):,} / "
                        f"불량 {int(round_item.defect_qty or 0):,}"
                    ),
                    status=round_item.schedule_status,
                    memo=(
                        round_item.partial_reason
                        if is_partial
                        else round_item.memo
                    ),
                    ref_type="INSPECTION_SCHEDULE",
                    ref_id=round_item.inspection_schedule_id,
                )
            )
            continue

        status_titles = {
            "WAITING": "검수 대기",
            "RECEIVED": "검수 접수",
            "IN_PROGRESS": "검수 진행",
            "CANCELED": "검수 취소",
        }
        items.append(
            LotTraceTimelineItemOut(
                event_type="INSPECTION_STATUS",
                event_at=(
                    round_item.started_at
                    or round_item.received_at
                    or round_item.schedule_created_at
                ),
                title=status_titles.get(round_item.schedule_status, "검수 일정"),
                summary=(
                    f"{round_item.inspection_round}차 / "
                    f"검수일 {round_item.inspection_date:%Y-%m-%d}"
                ),
                status=round_item.schedule_status,
                memo=round_item.memo,
                ref_type="INSPECTION_SCHEDULE",
                ref_id=round_item.inspection_schedule_id,
            )
        )

    if lot.status == "DONE":
        items.append(
            LotTraceTimelineItemOut(
                event_type="LOT_DONE",
                event_at=lot.updated_at,
                title="LOT 완료",
                summary=f"{lot.lot_no} LOT가 완료되었습니다.",
                status="DONE",
                ref_type="LOT",
                ref_id=lot.lot_id,
            )
        )
    elif lot.status == "CANCELED":
        items.append(
            LotTraceTimelineItemOut(
                event_type="LOT_CANCELED",
                event_at=lot.updated_at,
                title="LOT 취소",
                summary=f"{lot.lot_no} LOT가 취소되었습니다.",
                status="CANCELED",
                memo=lot.memo,
                ref_type="LOT",
                ref_id=lot.lot_id,
            )
        )

    items.sort(key=lambda item: _timeline_sort_key(item.event_at))
    return items


def _timeline_sort_key(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sum_result_qty(
    result_rows: list[tuple[InspectionSchedule, InspectionResult]],
    attr_name: str,
) -> int | None:
    if not result_rows:
        return None

    return sum(
        int(getattr(result, attr_name) or 0)
        for _, result in result_rows
        if result is not None
    )


def _build_inspection_defects(
    db: Session,
    result_ids: list[int],
    *,
    result_context_by_id: dict[int, tuple[int, date, bool]],
    attachment_content_url_builder: Callable[[int], str] | None,
) -> list[LotTraceInspectionDefectOut]:
    if not result_ids:
        return []

    defect_rows = (
        db.execute(
            select(InspectionDefect, DefectType)
            .join(
                DefectType,
                DefectType.defect_type_id == InspectionDefect.defect_type_id,
            )
            .where(InspectionDefect.inspection_result_id.in_(result_ids))
            .order_by(
                InspectionDefect.inspection_result_id.asc(),
                InspectionDefect.inspection_defect_id.asc(),
            )
        )
        .all()
    )

    defect_ids = [
        inspection_defect.inspection_defect_id
        for inspection_defect, _ in defect_rows
    ]
    attachments_by_defect_id = _load_attachments_by_defect_id(db, defect_ids)

    items = [
        LotTraceInspectionDefectOut(
            inspection_defect_id=inspection_defect.inspection_defect_id,
            inspection_result_id=inspection_defect.inspection_result_id,
            inspection_round=result_context_by_id[
                inspection_defect.inspection_result_id
            ][0],
            inspection_date=result_context_by_id[
                inspection_defect.inspection_result_id
            ][1],
            is_partial=result_context_by_id[
                inspection_defect.inspection_result_id
            ][2],
            defect_type_id=inspection_defect.defect_type_id,
            defect_type_code=defect_type.code,
            defect_type_name=_format_defect_type_name(defect_type),
            defect_qty=inspection_defect.defect_qty,
            disposition=inspection_defect.disposition,
            memo=inspection_defect.memo,
            attachments=[
                LotTraceDefectAttachmentOut(
                    inspection_defect_attachment_id=attachment.inspection_defect_attachment_id,
                    file_uri=attachment.file_uri,
                    file_name=attachment.file_name,
                    mime_type=attachment.mime_type,
                    memo=attachment.memo,
                    image_url=(
                        attachment_content_url_builder(
                            attachment.inspection_defect_attachment_id
                        )
                        if attachment_content_url_builder
                        else None
                    ),
                )
                for attachment in attachments_by_defect_id.get(
                    inspection_defect.inspection_defect_id,
                    [],
                )
            ],
        )
        for inspection_defect, defect_type in defect_rows
    ]
    items.sort(
        key=lambda item: (item.inspection_round, item.inspection_defect_id)
    )
    return items


def _load_attachments_by_defect_id(
    db: Session,
    defect_ids: list[int],
) -> dict[int, list[InspectionDefectAttachment]]:
    if not defect_ids:
        return {}

    attachment_rows = (
        db.execute(
            select(InspectionDefectAttachment)
            .where(InspectionDefectAttachment.inspection_defect_id.in_(defect_ids))
            .order_by(InspectionDefectAttachment.inspection_defect_attachment_id)
        )
        .scalars()
        .all()
    )

    attachments_by_defect_id: dict[int, list[InspectionDefectAttachment]] = {}
    for attachment in attachment_rows:
        attachments_by_defect_id.setdefault(
            attachment.inspection_defect_id,
            [],
        ).append(attachment)

    return attachments_by_defect_id


def _format_defect_type_name(defect_type: DefectType | None) -> str | None:
    if defect_type is None:
        return None

    category1 = (defect_type.category1_name or "").strip()
    category2 = (defect_type.category2_name or "").strip()

    if category1 and category2:
        return f"{category1} / {category2}"

    if category2:
        return category2

    if category1:
        return category1

    return defect_type.code


def _to_plan_type_display(plan_type: str | None) -> str | None:
    if not plan_type:
        return None

    mapping = {
        "AUTO_PRODUCTION": "자동 생산",
        "AUTO_STOCK_SHIP": "재고 출고",
        "PARTIAL_STOCK_ONLY_CLOSE": "재고만 출고 후 종료",
        "PARTIAL_STOCK_PLUS_PRODUCTION": "부분재고 + 부족분 생산",
        "STOCK_REPLENISHMENT": "재고비축 생산",
    }

    return mapping.get(plan_type, plan_type)


def _build_lot_trace_progress(
    outsource_works: list[LotTraceOutsourceWorkOut],
    inspection: LotTraceInspectionOut | None,
) -> LotTraceProgressOut:
    outsource_instruction_created = len(outsource_works) > 0

    outsource_work_done = any(
        x.work_done_sheet_qty is not None
        or x.status in ("WORK_DONE", "SHIPPED")
        for x in outsource_works
    )

    inspection_done = (
        inspection is not None
        and inspection.inspection_result_id is not None
        and inspection.schedule_status in ("DONE", "PARTIAL_DONE")
    )

    return LotTraceProgressOut(
        lot_created=True,
        outsource_instruction_created=outsource_instruction_created,
        outsource_work_done=outsource_work_done,
        inspection_done=inspection_done,
    )
