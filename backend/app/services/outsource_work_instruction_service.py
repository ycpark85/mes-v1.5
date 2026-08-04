from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction import OutsourceWorkInstruction
from app.models.outsource_work_instruction_file import OutsourceWorkInstructionFile
from app.models.outsource_work_instruction_item import OutsourceWorkInstructionItem
from app.models.partner import Partner
from app.models.product import Product
from app.models.routing_template import RoutingTemplate
from app.schemas.outsource_work_instruction import (
    OutsourceWorkInstructionBatchCreate,
    OutsourceWorkInstructionGroupCreate,
    OutsourceWorkInstructionGroupItemCreate,
)
from app.services.production_daily_query import refresh_order_line_snapshots_for_lots
from app.services.routing_policy import get_available_process_types


def create_work_instruction_batch(
    db: Session,
    payload: OutsourceWorkInstructionBatchCreate,
) -> list[OutsourceWorkInstruction]:
    created_instructions: list[OutsourceWorkInstruction] = []

    for group in payload.groups:
        partner = db.get(Partner, group.customer_partner_id)

        if not partner or not partner.is_active:
            raise HTTPException(status_code=404, detail="Partner not found or inactive")

        if len(group.lot_ids) > 1 and len(group.files) > 1:
            raise HTTPException(
                status_code=409,
                detail="Bundle work instruction allows only one plate data file",
            )

        if len(group.lot_ids) > 1 and len(group.files) == 0:
            raise HTTPException(
                status_code=409,
                detail="Bundle work instruction requires plate data file",
            )

        lots = (
            db.execute(
                select(Lot, OrderLine, Product, RoutingTemplate)
                .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
                .join(Product, Product.product_id == Lot.product_id)
                .join(RoutingTemplate, RoutingTemplate.routing_template_id == Product.routing_template_id)
                .where(Lot.lot_id.in_(group.lot_ids))
            )
            .all()
        )

        if len(lots) != len(set(group.lot_ids)):
            raise HTTPException(status_code=404, detail="Some lots were not found")

        cut_lot_ids: list[int] = []
        print_lot_ids: list[int] = []

        for lot, _order_line, _product, routing_template in lots:
            primary_process_type = _get_primary_outsource_process_type(
                routing_template.template_name
            )

            if primary_process_type == "PRINT":
                print_lot_ids.append(lot.lot_id)
            elif primary_process_type == "CUT":
                cut_lot_ids.append(lot.lot_id)

        if not cut_lot_ids and not print_lot_ids:
            raise HTTPException(status_code=409, detail="No available process for selected lots")

        _raise_if_lots_registered(db, cut_lot_ids, "CUT")
        _raise_if_lots_registered(db, print_lot_ids, "PRINT")

        cut_groups = _filter_groups_for_lot_ids(group.groups, cut_lot_ids) if group.groups else []
        print_groups = _filter_groups_for_lot_ids(group.groups, print_lot_ids) if group.groups else []

        if cut_lot_ids:
            created_instructions.append(
                _create_instruction(
                    db=db,
                    instruction_date=payload.instruction_date,
                    process_type="CUT",
                    partner_id=group.customer_partner_id,
                    lot_ids=cut_lot_ids,
                    memo=group.memo,
                    files=group.files,
                    groups=cut_groups,
                )
            )

        if print_lot_ids:
            created_instructions.append(
                _create_instruction(
                    db=db,
                    instruction_date=payload.instruction_date,
                    process_type="PRINT",
                    partner_id=group.customer_partner_id,
                    lot_ids=print_lot_ids,
                    memo=group.memo,
                    files=group.files,
                    groups=print_groups,
                )
            )

    refresh_order_line_snapshots_for_lots(
        db,
        {lot_id for group in payload.groups for lot_id in group.lot_ids},
    )

    return created_instructions


def _create_instruction(
    db: Session,
    instruction_date: date,
    process_type: str,
    partner_id: int,
    lot_ids: list[int],
    memo: str | None,
    files: list,
    groups: list[OutsourceWorkInstructionGroupCreate] | None = None,
) -> OutsourceWorkInstruction:
    instruction = OutsourceWorkInstruction(
        instruction_no=_generate_instruction_no(db, instruction_date),
        instruction_date=instruction_date,
        process_type=process_type,
        partner_id=partner_id,
        is_bundle=len(lot_ids) > 1,
        memo=memo,
    )
    db.add(instruction)
    db.flush()

    if groups:
        _create_work_groups(
            db=db,
            instruction_id=instruction.outsource_work_instruction_id,
            instruction_date=instruction_date,
            process_type=process_type,
            groups=groups,
        )

    for lot_id in lot_ids:
        db.add(
            OutsourceWorkInstructionItem(
                outsource_work_instruction_id=instruction.outsource_work_instruction_id,
                lot_id=lot_id,
                process_type=process_type,
            )
        )

    for file in files:
        db.add(
            OutsourceWorkInstructionFile(
                outsource_work_instruction_id=instruction.outsource_work_instruction_id,
                file_name=file.file_name,
                file_path=file.file_path,
                content_type=file.content_type,
            )
        )

    db.flush()
    return instruction


def _create_work_groups(
    db: Session,
    instruction_id: int,
    instruction_date: date,
    process_type: str,
    groups: list[OutsourceWorkInstructionGroupCreate],
) -> None:
    for group_payload in groups:
        group_lot_ids = {item.lot_id for item in group_payload.items}
        representative_lot_id = group_payload.representative_lot_id

        if representative_lot_id is not None and representative_lot_id not in group_lot_ids:
            raise HTTPException(
                status_code=409,
                detail="Representative lot must be included in outsource work group items",
            )

        if len(group_payload.items) > 1 and representative_lot_id is None:
            raise HTTPException(
                status_code=409,
                detail="Representative lot is required for bundle outsource work group",
            )

        if len(group_payload.items) == 1:
            representative_lot_id = group_payload.items[0].lot_id

        sheet_cut_count = _resolve_group_sheet_cut_count(
            db=db,
            process_type=process_type,
            group_payload=group_payload,
        )

        work_group = OutsourceWorkGroup(
            outsource_work_instruction_id=instruction_id,
            group_seq=_generate_work_group_seq(db, instruction_date),
            process_type=process_type,
            is_bundle=group_payload.is_bundle,
            sheet_qty=group_payload.sheet_qty,
            length_m=group_payload.length_m,
            sheet_cut_count=sheet_cut_count,
            fabric_lot_no=(
                group_payload.fabric_lot_no.strip()
                if group_payload.fabric_lot_no and group_payload.fabric_lot_no.strip()
                else None
            ),
            representative_lot_id=representative_lot_id,
            remark=group_payload.remark,
        )
        db.add(work_group)
        db.flush()

        for item in group_payload.items:
            expected_output_qty = item.expected_output_qty

            if expected_output_qty is None:
                expected_output_qty = group_payload.sheet_qty * item.cuts_per_sheet

            db.add(
                OutsourceWorkGroupItem(
                    outsource_work_group_id=work_group.outsource_work_group_id,
                    lot_id=item.lot_id,
                    cuts_per_sheet=item.cuts_per_sheet,
                    expected_output_qty=expected_output_qty,
                    remark=item.remark,
                )
            )

    db.flush()


def _generate_instruction_no(db: Session, instruction_date: date) -> str:
    yy = f"{instruction_date.year % 100:02d}"
    mm = f"{instruction_date.month:02d}"
    dd = f"{instruction_date.day:02d}"
    prefix = f"OWI{yy}{mm}{dd}"

    last = (
        db.execute(
            select(OutsourceWorkInstruction.instruction_no)
            .where(OutsourceWorkInstruction.instruction_no.like(f"{prefix}%"))
            .order_by(OutsourceWorkInstruction.instruction_no.desc())
            .limit(1)
        )
        .scalar_one_or_none()
    )

    if not last:
        seq = 1
    else:
        try:
            seq = int(last[-3:]) + 1
        except ValueError:
            seq = 1

    return f"{prefix}{seq:03d}"


def _get_primary_outsource_process_type(template_name: str | None) -> str:
    available_process_types = get_available_process_types(template_name)

    if "PRINT" in available_process_types:
        return "PRINT"

    if "CUT" in available_process_types:
        return "CUT"

    return ""


def _filter_groups_for_lot_ids(
    groups: list[OutsourceWorkInstructionGroupCreate],
    allowed_lot_ids: list[int],
) -> list[OutsourceWorkInstructionGroupCreate]:
    allowed_set = set(allowed_lot_ids)
    filtered_groups: list[OutsourceWorkInstructionGroupCreate] = []

    for group in groups:
        filtered_items = [
            OutsourceWorkInstructionGroupItemCreate(
                lot_id=item.lot_id,
                cuts_per_sheet=item.cuts_per_sheet,
                expected_output_qty=item.expected_output_qty,
                remark=item.remark,
            )
            for item in group.items
            if item.lot_id in allowed_set
        ]

        if not filtered_items:
            continue

        sheet_cut_count = group.sheet_cut_count

        if group.is_bundle:
            sheet_cut_count = sum(item.cuts_per_sheet for item in filtered_items)

        representative_lot_id = (
            group.representative_lot_id
            if group.representative_lot_id in allowed_set
            else None
        )

        filtered_groups.append(
            OutsourceWorkInstructionGroupCreate(
                group_seq=group.group_seq,
                is_bundle=group.is_bundle,
                sheet_qty=group.sheet_qty,
                length_m=group.length_m,
                sheet_cut_count=sheet_cut_count,
                fabric_lot_no=group.fabric_lot_no,
                representative_lot_id=representative_lot_id,
                remark=group.remark,
                items=filtered_items,
            )
        )

    return filtered_groups


def _get_work_group_month_code(value: date) -> str:
    month_codes = {
        1: "A",
        2: "B",
        3: "C",
        4: "D",
        5: "E",
        6: "F",
        7: "G",
        8: "H",
        9: "I",
        10: "J",
        11: "K",
        12: "L",
    }

    return month_codes[value.month]


def _generate_work_group_seq(
    db: Session,
    instruction_date: date,
) -> str:
    prefix = f"{_get_work_group_month_code(instruction_date)}{instruction_date.day:02d}"

    existing_codes = (
        db.execute(
            select(OutsourceWorkGroup.group_seq)
            .join(
                OutsourceWorkInstruction,
                OutsourceWorkInstruction.outsource_work_instruction_id
                == OutsourceWorkGroup.outsource_work_instruction_id,
            )
            .where(OutsourceWorkInstruction.instruction_date == instruction_date)
            .where(OutsourceWorkGroup.group_seq.like(f"{prefix}%"))
            .order_by(OutsourceWorkGroup.group_seq.desc())
            .with_for_update()
        )
        .scalars()
        .all()
    )

    max_seq = 0

    for code in existing_codes:
        suffix = str(code).replace(prefix, "", 1)

        if not suffix.isdigit():
            continue

        max_seq = max(max_seq, int(suffix))

    return f"{prefix}{max_seq + 1}"


def _resolve_group_sheet_cut_count(
    db: Session,
    process_type: str,
    group_payload: OutsourceWorkInstructionGroupCreate,
) -> int:
    if group_payload.is_bundle:
        if group_payload.sheet_cut_count is None or group_payload.sheet_cut_count <= 0:
            raise HTTPException(
                status_code=409,
                detail="sheet_cut_count is required for bundle group",
            )

        cuts_sum = sum(item.cuts_per_sheet for item in group_payload.items)

        if cuts_sum != group_payload.sheet_cut_count:
            raise HTTPException(
                status_code=409,
                detail="sum(cuts_per_sheet) must equal sheet_cut_count for bundle group",
            )

        return group_payload.sheet_cut_count

    if len(group_payload.items) != 1:
        raise HTTPException(
            status_code=409,
            detail="non-bundle group must contain exactly one item",
        )

    lot_id = group_payload.items[0].lot_id

    cut_qty_per_panel = db.execute(
        select(Product.cut_qty_per_panel)
        .join(Lot, Lot.product_id == Product.product_id)
        .where(Lot.lot_id == lot_id)
    ).scalar_one_or_none()

    if cut_qty_per_panel is not None and int(cut_qty_per_panel) > 0:
        return int(cut_qty_per_panel)

    if group_payload.sheet_cut_count is not None and group_payload.sheet_cut_count > 0:
        return group_payload.sheet_cut_count

    raise HTTPException(
        status_code=409,
        detail="cut_qty_per_panel or sheet_cut_count is required for non-bundle group",
    )


def _raise_if_lots_registered(db: Session, lot_ids: list[int], process_type: str) -> None:
    if not lot_ids:
        return

    for lot_id in lot_ids:
        exists_registered = db.execute(
            select(OutsourceWorkInstructionItem.outsource_work_instruction_item_id)
            .where(
                OutsourceWorkInstructionItem.lot_id == lot_id,
                OutsourceWorkInstructionItem.process_type == process_type,
                OutsourceWorkInstructionItem.is_active.is_(True),
            )
            .limit(1)
        ).scalar_one_or_none()

        if exists_registered:
            raise HTTPException(
                status_code=409,
                detail=f"Some lots are already registered for process {process_type}",
            )
