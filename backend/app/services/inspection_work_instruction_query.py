from __future__ import annotations

from datetime import date

from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session

from app.models.drawing import Drawing
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction import OutsourceWorkInstruction
from app.models.outsource_work_instruction_file import OutsourceWorkInstructionFile
from app.models.partner import Partner
from app.models.product import Product
from app.models.routing_template import RoutingTemplate
from app.schemas.inspection_schedule import (
    InspectionScheduleListItemOut,
    InspectionWorkInstructionTargetListOut,
    InspectionWorkInstructionTargetOut,
)
from app.services.order_line_display import order_product_code, order_product_name
from app.services.routing_policy import is_inspection_only_template_name
from app.services.ship_qty_policy import calculate_ship_qty


def list_inspection_schedule_items(
    db: Session,
    *,
    inspection_date_from: date | None = None,
    inspection_date_to: date | None = None,
    status: str | None = None,
    partner_q: str | None = None,
    product_q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[InspectionScheduleListItemOut]:
    plate_data_file_name_subq = (
        select(OutsourceWorkInstructionFile.file_name)
        .where(
            OutsourceWorkInstructionFile.outsource_work_instruction_id
            == OutsourceWorkInstruction.outsource_work_instruction_id
        )
        .order_by(OutsourceWorkInstructionFile.outsource_work_instruction_file_id.asc())
        .limit(1)
        .scalar_subquery()
    )
    plate_data_file_path_subq = (
        select(OutsourceWorkInstructionFile.file_path)
        .where(
            OutsourceWorkInstructionFile.outsource_work_instruction_id
            == OutsourceWorkInstruction.outsource_work_instruction_id
        )
        .order_by(OutsourceWorkInstructionFile.outsource_work_instruction_file_id.asc())
        .limit(1)
        .scalar_subquery()
    )

    stmt = (
        select(
            InspectionSchedule.inspection_schedule_id,
            InspectionSchedule.lot_id,
            Lot.lot_no,
            (Lot.parent_lot_id.is_not(None)).label("is_rework"),
            InspectionSchedule.inspection_date,
            InspectionSchedule.status,
            InspectionSchedule.day_seq,
            Lot.due_date,
            Partner.name.label("partner_name"),
            func.coalesce(OrderLine.source_erp_product_code, Product.product_code).label("product_code"),
            Product.product_code.label("mes_product_code"),
            func.coalesce(OrderLine.source_product_name, Product.product_name).label("product_name"),
            case((OrderLine.source_erp_product_code.is_not(None), OrderLine.source_product_spec),
                 else_=Product.product_spec).label("product_spec"),
            Product.drawing_id,
            Drawing.drawing_no,
            Lot.lot_qty,
            OrderLine.order_qty,
            InspectionSchedule.outsource_work_group_id,
            InspectionSchedule.outsource_work_group_item_id,
            OutsourceWorkGroup.group_seq,
            OutsourceWorkGroup.is_bundle,
            OutsourceWorkGroup.status.label("outsource_work_group_status"),
            OutsourceWorkInstruction.instruction_no,
            plate_data_file_name_subq.label("plate_data_file_name"),
            plate_data_file_path_subq.label("plate_data_file_path"),
            InspectionSchedule.memo,
        )
        .select_from(InspectionSchedule)
        .join(Lot, Lot.lot_id == InspectionSchedule.lot_id)
        .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
        .join(Partner, Partner.partner_id == OrderLine.partner_id)
        .join(Product, Product.product_id == OrderLine.product_id)
        .join(Drawing, Drawing.drawing_id == Product.drawing_id)
        .outerjoin(
            OutsourceWorkGroup,
            OutsourceWorkGroup.outsource_work_group_id
            == InspectionSchedule.outsource_work_group_id,
        )
        .outerjoin(
            OutsourceWorkInstruction,
            OutsourceWorkInstruction.outsource_work_instruction_id
            == OutsourceWorkGroup.outsource_work_instruction_id,
        )
    )

    if inspection_date_from is not None:
        stmt = stmt.where(InspectionSchedule.inspection_date >= inspection_date_from)
    if inspection_date_to is not None:
        stmt = stmt.where(InspectionSchedule.inspection_date <= inspection_date_to)
    if status is not None:
        stmt = stmt.where(InspectionSchedule.status == status)

    if partner_q:
        stmt = stmt.where(Partner.name.ilike(f"%{partner_q}%"))

    if product_q:
        stmt = stmt.where(
            ((Product.product_name.ilike(f"%{product_q}%") | OrderLine.source_product_name.ilike(f"%{product_q}%")))
            | ((Product.product_code.ilike(f"%{product_q}%") | OrderLine.source_erp_product_code.ilike(f"%{product_q}%")))
        )

    stmt = (
        stmt.order_by(
            InspectionSchedule.inspection_date.asc(),
            InspectionSchedule.day_seq.asc().nulls_last(),
            InspectionSchedule.inspection_schedule_id.asc(),
        )
        .limit(limit)
        .offset(offset)
    )

    rows = db.execute(stmt).mappings().all()

    items: list[InspectionScheduleListItemOut] = []

    for row in rows:
        row_dict = dict(row)

        row_dict["ship_qty"] = calculate_ship_qty(
            row_dict["partner_name"],
            row_dict["order_qty"],
        )

        row_dict["bundle_no"] = _build_inspection_bundle_no_from_values(
            instruction_no=row_dict.get("instruction_no"),
            outsource_work_group_id=row_dict.get("outsource_work_group_id"),
            group_seq=row_dict.get("group_seq"),
            is_bundle=row_dict.get("is_bundle"),
        )

        row_dict["diecut_status"] = _to_diecut_status_label(
            row_dict.get("outsource_work_group_status")
        )

        items.append(InspectionScheduleListItemOut(**row_dict))

    return items


def list_inspection_work_instruction_targets(
    db: Session,
    *,
    partner_q: str | None = None,
    product_q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> InspectionWorkInstructionTargetListOut:
    stmt = (
        select(
            Lot.lot_id,
            Lot.lot_no,
            OutsourceWorkGroup.outsource_work_group_id,
            OutsourceWorkGroupItem.outsource_work_group_item_id,
            OutsourceWorkGroup.group_seq,
            OutsourceWorkGroup.is_bundle,
            OutsourceWorkInstruction.instruction_no,
            func.coalesce(OrderLine.source_erp_product_code, Product.product_code).label("product_code"),
            Product.product_code.label("mes_product_code"),
            func.coalesce(OrderLine.source_product_name, Product.product_name).label("product_name"),
            Partner.name.label("partner_name"),
            Lot.lot_qty,
            Lot.due_date,
            OutsourceWorkGroup.remark.label("memo"),
        )
        .select_from(OutsourceWorkGroupItem)
        .join(
            OutsourceWorkGroup,
            OutsourceWorkGroup.outsource_work_group_id
            == OutsourceWorkGroupItem.outsource_work_group_id,
        )
        .join(
            OutsourceWorkInstruction,
            OutsourceWorkInstruction.outsource_work_instruction_id
            == OutsourceWorkGroup.outsource_work_instruction_id,
        )
        .join(Lot, Lot.lot_id == OutsourceWorkGroupItem.lot_id)
        .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
        .join(Partner, Partner.partner_id == OrderLine.partner_id)
        .join(Product, Product.product_id == Lot.product_id)
        .where(
            (
                OutsourceWorkGroup.status.is_(None)
                | (OutsourceWorkGroup.status != "CANCELED")
            ),
            ~exists(
                select(1)
                .select_from(InspectionSchedule)
                .where(
                    InspectionSchedule.lot_id == Lot.lot_id,
                    InspectionSchedule.status != "CANCELED",
                )
            ),
        )
    )

    if partner_q:
        stmt = stmt.where(Partner.name.ilike(f"%{partner_q.strip()}%"))

    if product_q:
        like = f"%{product_q.strip()}%"
        stmt = stmt.where(
            ((Product.product_code.ilike(like) | OrderLine.source_erp_product_code.ilike(like)))
            | ((Product.product_name.ilike(like) | OrderLine.source_product_name.ilike(like)))
            | (Lot.lot_no.ilike(like))
        )

    stmt = (
        stmt.order_by(
            OutsourceWorkInstruction.instruction_date.desc(),
            OutsourceWorkInstruction.instruction_no.desc(),
            OutsourceWorkGroup.group_seq.asc(),
            Lot.lot_no.asc(),
        )
        .limit(limit)
        .offset(offset)
    )

    rows = db.execute(stmt).mappings().all()

    items: list[InspectionWorkInstructionTargetOut] = []

    for row in rows:
        row_dict = dict(row)

        bundle_no = _build_inspection_bundle_no_from_values(
            instruction_no=row_dict.get("instruction_no"),
            outsource_work_group_id=row_dict.get("outsource_work_group_id"),
            group_seq=row_dict.get("group_seq"),
            is_bundle=row_dict.get("is_bundle"),
        )

        items.append(
            InspectionWorkInstructionTargetOut(
                lot_id=row_dict["lot_id"],
                lot_no=row_dict["lot_no"],
                outsource_work_group_id=row_dict["outsource_work_group_id"],
                outsource_work_group_item_id=row_dict["outsource_work_group_item_id"],
                bundle_no=bundle_no,
                product_code=row_dict.get("product_code"),
                mes_product_code=row_dict.get("mes_product_code"),
                product_name=row_dict.get("product_name"),
                partner_name=row_dict.get("partner_name"),
                lot_qty=row_dict["lot_qty"],
                due_date=row_dict.get("due_date"),
                memo=row_dict.get("memo"),
            )
        )

    existing_item_lot_ids = {int(item.lot_id) for item in items}

    inspection_only_stmt = (
        select(Lot, OrderLine, Product, Partner, RoutingTemplate)
        .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
        .join(Partner, Partner.partner_id == OrderLine.partner_id)
        .join(Product, Product.product_id == Lot.product_id)
        .join(
            RoutingTemplate,
            RoutingTemplate.routing_template_id == Product.routing_template_id,
        )
        .where(
            Lot.status != "CANCELED",
            ~exists(
                select(1)
                .select_from(InspectionSchedule)
                .where(
                    InspectionSchedule.lot_id == Lot.lot_id,
                    InspectionSchedule.status != "CANCELED",
                )
            ),
        )
    )

    if partner_q:
        inspection_only_stmt = inspection_only_stmt.where(
            Partner.name.ilike(f"%{partner_q.strip()}%")
        )

    if product_q:
        like = f"%{product_q.strip()}%"
        inspection_only_stmt = inspection_only_stmt.where(
            ((Product.product_code.ilike(like) | OrderLine.source_erp_product_code.ilike(like)))
            | ((Product.product_name.ilike(like) | OrderLine.source_product_name.ilike(like)))
            | (Lot.lot_no.ilike(like))
        )

    inspection_only_rows = (
        db.execute(
            inspection_only_stmt.order_by(
                Lot.created_date.desc(),
                Lot.lot_no.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        .all()
    )

    for lot, order_line, product, partner, routing_template in inspection_only_rows:
        if int(lot.lot_id) in existing_item_lot_ids:
            continue

        if not is_inspection_only_template_name(routing_template.template_name):
            continue

        items.append(
            InspectionWorkInstructionTargetOut(
                lot_id=lot.lot_id,
                lot_no=lot.lot_no,
                outsource_work_group_id=None,
                outsource_work_group_item_id=None,
                bundle_no=None,
                product_code=order_product_code(order_line, product),
                mes_product_code=product.product_code,
                product_name=order_product_name(order_line, product),
                partner_name=partner.name,
                lot_qty=lot.lot_qty,
                due_date=lot.due_date,
                memo=lot.memo,
            )
        )

    return InspectionWorkInstructionTargetListOut(items=items)


def _to_diecut_status_label(status: str | None) -> str | None:
    if status is None:
        return "\uc678\uc8fc \uc785\uace0\ub300\uae30"

    if status == "VENDOR_RECEIVED":
        return "\uc678\uc8fc \uc785\uace0\uc644\ub8cc"

    if status == "WORK_DONE":
        return "\uc678\uc8fc \uc791\uc5c5\uc644\ub8cc"

    if status == "SHIPPED":
        return "\uc678\uc8fc \ucd9c\uace0\uc644\ub8cc"

    return status


def _build_inspection_bundle_no_from_values(
    instruction_no: str | None,
    outsource_work_group_id: int | None,
    group_seq: int | None,
    is_bundle: bool | None,
) -> str | None:
    if not is_bundle:
        return None

    if group_seq is not None:
        return f"G{group_seq}"

    if instruction_no and "-" in instruction_no:
        return instruction_no.split("-")[-1]

    if outsource_work_group_id:
        return f"G{outsource_work_group_id}"

    return None
