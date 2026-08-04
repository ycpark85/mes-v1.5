from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.outsource_purchase_order import OutsourcePurchaseOrder
from app.models.outsource_purchase_order_group import OutsourcePurchaseOrderGroup
from app.models.outsource_purchase_order_item import OutsourcePurchaseOrderItem
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction import OutsourceWorkInstruction
from app.models.outsource_work_instruction_file import OutsourceWorkInstructionFile
from app.models.outsource_work_instruction_item import OutsourceWorkInstructionItem
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.routing_template import RoutingTemplate
from app.schemas.outsource_work_instruction import (
    OutsourceWorkInstructionCandidateLotListOut,
    OutsourceWorkInstructionCandidateLotOut,
    OutsourceWorkInstructionItemOut,
    OutsourceWorkInstructionOut,
    OutsourceWorkGroupDetailOut,
    OutsourceWorkGroupListItemOut,
    OutsourceWorkGroupListOut,
    OutsourceWorkGroupLotOut,
    OutsourceWorkInstructionFileOut,
)
from app.services.routing_policy import get_available_process_types


OUTSOURCE_WORK_GROUP_STATUS_CANCELED = "CANCELED"
BOHYUN_DB_STATUS_VENDOR_RECEIVED = "VENDOR_RECEIVED"
BOHYUN_DB_STATUS_WORK_DONE = "WORK_DONE"
BOHYUN_DB_STATUS_SHIPPED = "SHIPPED"


def build_work_instruction_out(
    db: Session,
    instruction: OutsourceWorkInstruction,
) -> OutsourceWorkInstructionOut:
    item_rows = (
        db.execute(
            select(OutsourceWorkInstructionItem, Lot, OrderLine, Product)
            .join(Lot, Lot.lot_id == OutsourceWorkInstructionItem.lot_id)
            .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
            .join(Product, Product.product_id == Lot.product_id)
            .where(
                OutsourceWorkInstructionItem.outsource_work_instruction_id
                == instruction.outsource_work_instruction_id
            )
            .order_by(OutsourceWorkInstructionItem.outsource_work_instruction_item_id.asc())
        )
        .all()
    )

    file_rows = (
        db.execute(
            select(OutsourceWorkInstructionFile).where(
                OutsourceWorkInstructionFile.outsource_work_instruction_id
                == instruction.outsource_work_instruction_id
            )
            .order_by(OutsourceWorkInstructionFile.outsource_work_instruction_file_id.asc())
        )
        .scalars()
        .all()
    )

    return OutsourceWorkInstructionOut(
        outsource_work_instruction_id=instruction.outsource_work_instruction_id,
        instruction_no=instruction.instruction_no,
        instruction_date=instruction.instruction_date,
        process_type=instruction.process_type,
        partner_id=instruction.partner_id,
        is_bundle=instruction.is_bundle,
        memo=instruction.memo,
        created_at=instruction.created_at,
        updated_at=instruction.updated_at,
        items=[
            OutsourceWorkInstructionItemOut(
                outsource_work_instruction_item_id=item.outsource_work_instruction_item_id,
                lot_id=lot.lot_id,
                lot_no=lot.lot_no,
                order_no=order_line.order_no,
                line_no=order_line.line_no,
                product_code=product.product_code,
                product_name=product.product_name,
                lot_qty=lot.lot_qty,
                process_type=item.process_type,
            )
            for item, lot, order_line, product in item_rows
        ],
        files=[
            OutsourceWorkInstructionFileOut.model_validate(x, from_attributes=True)
            for x in file_rows
        ],
    )


def list_candidate_lots(
    db: Session,
    *,
    process_type: str | None = None,
    q: str | None = None,
) -> OutsourceWorkInstructionCandidateLotListOut:
    if process_type and process_type not in ("CUT", "PRINT"):
        raise HTTPException(status_code=409, detail="Invalid process_type")

    stmt = (
        select(Lot, OrderLine, Product, Partner, RoutingTemplate)
        .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
        .join(Product, Product.product_id == Lot.product_id)
        .join(Partner, Partner.partner_id == OrderLine.partner_id)
        .join(RoutingTemplate, RoutingTemplate.routing_template_id == Product.routing_template_id)
        .order_by(Lot.created_date.desc(), Lot.lot_no.asc())
    )

    if q and q.strip():
        normalized_q = q.strip()
        like = f"%{normalized_q}%"
        stmt = stmt.where(
            (Lot.lot_no.ilike(like))
            | (OrderLine.order_no == normalized_q.upper())
            | (Product.product_code.ilike(like))
            | (Product.product_name.ilike(like))
            | (Partner.name.ilike(like))
        )

    rows = db.execute(stmt).all()

    product_ids = sorted({
        int(product.product_id)
        for _lot, _order_line, product, _partner, _routing_template in rows
    })

    current_stock_qty_map: dict[int, int] = {}

    if product_ids:
        inventory_rows = db.execute(
            select(ProductInventory.product_id, ProductInventory.current_qty)
            .where(ProductInventory.product_id.in_(product_ids))
        ).all()

        current_stock_qty_map = {
            int(product_id): int(current_qty or 0)
            for product_id, current_qty in inventory_rows
        }

    items: list[OutsourceWorkInstructionCandidateLotOut] = []

    for lot, order_line, product, partner, routing_template in rows:
        available = get_available_process_types(routing_template.template_name)
        if not available:
            continue

        if process_type and process_type not in available:
            continue

        required_processes = [process_type] if process_type else available

        exists_registered = db.execute(
            select(OutsourceWorkGroupItem.outsource_work_group_item_id)
            .join(
                OutsourceWorkGroup,
                OutsourceWorkGroup.outsource_work_group_id
                == OutsourceWorkGroupItem.outsource_work_group_id,
            )
            .where(
                OutsourceWorkGroupItem.lot_id == lot.lot_id,
                OutsourceWorkGroup.process_type.in_(required_processes),
                (
                    OutsourceWorkGroup.status.is_(None)
                    | (OutsourceWorkGroup.status != OUTSOURCE_WORK_GROUP_STATUS_CANCELED)
                ),
            )
            .limit(1)
        ).scalar_one_or_none()

        if exists_registered:
            continue

        items.append(
            OutsourceWorkInstructionCandidateLotOut(
                lot_id=lot.lot_id,
                lot_no=lot.lot_no,
                order_line_id=order_line.order_line_id,
                order_no=order_line.order_no,
                line_no=order_line.line_no,
                product_id=product.product_id,
                product_code=product.product_code,
                product_name=product.product_name,
                customer_partner_id=partner.partner_id,
                customer_partner_name=partner.name,
                lot_qty=lot.lot_qty,
                current_stock_qty=current_stock_qty_map.get(int(product.product_id), 0),
                available_process_types=available,
                panel_width_mm=product.panel_width_mm,
                panel_length_mm=product.panel_length_mm,
                product_spec=product.product_spec,
                cut_qty_per_panel=product.cut_qty_per_panel,
            )
        )

    return OutsourceWorkInstructionCandidateLotListOut(items=items)


def list_work_groups(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    process_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 100,
) -> OutsourceWorkGroupListOut:
    if process_type and process_type not in ("CUT", "PRINT"):
        raise HTTPException(status_code=409, detail="Invalid process_type")

    stmt = (
        select(OutsourceWorkGroup)
        .join(
            OutsourceWorkInstruction,
            OutsourceWorkInstruction.outsource_work_instruction_id
            == OutsourceWorkGroup.outsource_work_instruction_id,
        )
        .join(Partner, Partner.partner_id == OutsourceWorkInstruction.partner_id)
    )
    count_stmt = (
        select(func.count())
        .select_from(OutsourceWorkGroup)
        .join(
            OutsourceWorkInstruction,
            OutsourceWorkInstruction.outsource_work_instruction_id
            == OutsourceWorkGroup.outsource_work_instruction_id,
        )
        .join(Partner, Partner.partner_id == OutsourceWorkInstruction.partner_id)
    )

    if date_from is not None:
        stmt = stmt.where(OutsourceWorkInstruction.instruction_date >= date_from)
        count_stmt = count_stmt.where(OutsourceWorkInstruction.instruction_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(OutsourceWorkInstruction.instruction_date <= date_to)
        count_stmt = count_stmt.where(OutsourceWorkInstruction.instruction_date <= date_to)
    if process_type:
        stmt = stmt.where(OutsourceWorkGroup.process_type == process_type)
        count_stmt = count_stmt.where(OutsourceWorkGroup.process_type == process_type)
    if status:
        normalized_status = status.strip().upper()
        if normalized_status == "REGISTERED":
            stmt = stmt.where(OutsourceWorkGroup.status.is_(None))
            count_stmt = count_stmt.where(OutsourceWorkGroup.status.is_(None))
        else:
            stmt = stmt.where(OutsourceWorkGroup.status == normalized_status)
            count_stmt = count_stmt.where(OutsourceWorkGroup.status == normalized_status)
    if q and q.strip():
        like = f"%{q.strip()}%"
        lot_match = (
            select(OutsourceWorkGroupItem.outsource_work_group_id)
            .join(Lot, Lot.lot_id == OutsourceWorkGroupItem.lot_id)
            .join(Product, Product.product_id == Lot.product_id)
            .where(
                (Lot.lot_no.like(like))
                | (Product.product_code.ilike(like))
                | (Product.product_name.ilike(like))
            )
        )
        condition = (
            OutsourceWorkInstruction.instruction_no.like(like)
            | Partner.name.ilike(like)
            | OutsourceWorkGroup.group_seq.like(like)
            | OutsourceWorkGroup.fabric_lot_no.like(like)
            | OutsourceWorkGroup.outsource_work_group_id.in_(lot_match)
        )
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total_count = int(db.execute(count_stmt).scalar_one() or 0)
    rows = (
        db.execute(
            stmt.order_by(
                OutsourceWorkInstruction.instruction_date.desc(),
                OutsourceWorkInstruction.instruction_no.desc(),
                OutsourceWorkGroup.outsource_work_group_id.desc(),
            )
            .limit(size)
            .offset((page - 1) * size)
        )
        .scalars()
        .all()
    )

    details = [build_work_group_detail(db, work_group) for work_group in rows]
    items = [
        OutsourceWorkGroupListItemOut(
            **detail.model_dump(exclude={"lots", "files"})
        )
        for detail in details
    ]

    return OutsourceWorkGroupListOut(items=items, total_count=total_count)


def get_work_group_detail(
    db: Session,
    outsource_work_group_id: int,
) -> OutsourceWorkGroupDetailOut:
    work_group = db.get(OutsourceWorkGroup, outsource_work_group_id)
    if work_group is None:
        raise HTTPException(status_code=404, detail="Outsource work group not found")

    return build_work_group_detail(db, work_group)


def display_work_group_status(status: str | None) -> str:
    if status == OUTSOURCE_WORK_GROUP_STATUS_CANCELED:
        return "취소"
    if status == BOHYUN_DB_STATUS_VENDOR_RECEIVED:
        return "외주입고"
    if status == BOHYUN_DB_STATUS_WORK_DONE:
        return "작업완료"
    if status == BOHYUN_DB_STATUS_SHIPPED:
        return "출고완료"

    return "지시등록"


def normalized_work_group_status(status: str | None) -> str:
    return status or "REGISTERED"


def get_cancel_block_reason(
    db: Session,
    work_group: OutsourceWorkGroup,
) -> str | None:
    if work_group.status == OUTSOURCE_WORK_GROUP_STATUS_CANCELED:
        return "이미 취소된 작업지시입니다."

    if work_group.status in {
        BOHYUN_DB_STATUS_VENDOR_RECEIVED,
        BOHYUN_DB_STATUS_WORK_DONE,
        BOHYUN_DB_STATUS_SHIPPED,
    }:
        return "외주 입고 이후 상태라 취소할 수 없습니다."

    group_lot_ids = [
        row[0]
        for row in db.execute(
            select(OutsourceWorkGroupItem.lot_id).where(
                OutsourceWorkGroupItem.outsource_work_group_id
                == work_group.outsource_work_group_id
            )
        ).all()
    ]

    if group_lot_ids:
        progressed_purchase_order_item = db.execute(
            select(OutsourcePurchaseOrderItem.outsource_purchase_order_item_id)
            .where(
                OutsourcePurchaseOrderItem.outsource_work_instruction_id
                == work_group.outsource_work_instruction_id,
                OutsourcePurchaseOrderItem.lot_id.in_(group_lot_ids),
                OutsourcePurchaseOrderItem.status.in_(
                    [
                        BOHYUN_DB_STATUS_VENDOR_RECEIVED,
                        BOHYUN_DB_STATUS_WORK_DONE,
                        BOHYUN_DB_STATUS_SHIPPED,
                    ]
                ),
            )
            .limit(1)
        ).scalar_one_or_none()

        if progressed_purchase_order_item is not None:
            return "연결된 외주발주 항목이 입고 이후 상태라 취소할 수 없습니다."

    progressed_purchase_order_group = db.execute(
        select(OutsourcePurchaseOrderGroup.outsource_purchase_order_group_id)
        .where(
            OutsourcePurchaseOrderGroup.outsource_work_group_id
            == work_group.outsource_work_group_id,
            OutsourcePurchaseOrderGroup.status.in_(
                [
                    BOHYUN_DB_STATUS_VENDOR_RECEIVED,
                    BOHYUN_DB_STATUS_WORK_DONE,
                    BOHYUN_DB_STATUS_SHIPPED,
                ]
            ),
        )
        .limit(1)
    ).scalar_one_or_none()

    if progressed_purchase_order_group is not None:
        return "연결된 외주발주가 입고 이후 상태라 취소할 수 없습니다."

    progressed_inspection_schedule = db.execute(
        select(InspectionSchedule.inspection_schedule_id)
        .where(
            InspectionSchedule.outsource_work_group_id
            == work_group.outsource_work_group_id,
            InspectionSchedule.status.notin_(("WAITING", "RECEIVED", "CANCELED")),
        )
        .limit(1)
    ).scalar_one_or_none()

    if progressed_inspection_schedule is not None:
        return "Inspection schedule already progressed and cannot be canceled with outsource work group"

    return None


def get_update_block_reason(
    db: Session,
    work_group: OutsourceWorkGroup,
) -> str | None:
    if work_group.status == OUTSOURCE_WORK_GROUP_STATUS_CANCELED:
        return "Canceled outsource work instruction cannot be updated"

    if work_group.status in {
        BOHYUN_DB_STATUS_VENDOR_RECEIVED,
        BOHYUN_DB_STATUS_WORK_DONE,
        BOHYUN_DB_STATUS_SHIPPED,
    }:
        return "Outsource work instruction cannot be updated after vendor receipt"

    purchase_order_group_id = db.execute(
        select(OutsourcePurchaseOrderGroup.outsource_purchase_order_group_id)
        .where(
            OutsourcePurchaseOrderGroup.outsource_work_group_id
            == work_group.outsource_work_group_id
        )
        .limit(1)
    ).scalar_one_or_none()

    if purchase_order_group_id is not None:
        return "Outsource work instruction cannot be updated after purchase order creation"

    group_lot_ids = [
        row[0]
        for row in db.execute(
            select(OutsourceWorkGroupItem.lot_id).where(
                OutsourceWorkGroupItem.outsource_work_group_id
                == work_group.outsource_work_group_id
            )
        ).all()
    ]

    if group_lot_ids:
        purchase_order_item_id = db.execute(
            select(OutsourcePurchaseOrderItem.outsource_purchase_order_item_id)
            .join(
                OutsourcePurchaseOrder,
                OutsourcePurchaseOrder.outsource_purchase_order_id
                == OutsourcePurchaseOrderItem.outsource_purchase_order_id,
            )
            .join(
                OutsourceWorkInstructionItem,
                (
                    OutsourceWorkInstructionItem.outsource_work_instruction_id
                    == OutsourcePurchaseOrderItem.outsource_work_instruction_id
                )
                & (OutsourceWorkInstructionItem.lot_id == OutsourcePurchaseOrderItem.lot_id)
                & (OutsourceWorkInstructionItem.is_active.is_(True)),
            )
            .where(
                OutsourcePurchaseOrder.process_type == work_group.process_type,
                OutsourcePurchaseOrderItem.lot_id.in_(group_lot_ids),
            )
            .limit(1)
        ).scalar_one_or_none()

        if purchase_order_item_id is not None:
            return "Outsource work instruction cannot be updated after purchase order creation"

    return None


def build_work_group_detail(
    db: Session,
    work_group: OutsourceWorkGroup,
) -> OutsourceWorkGroupDetailOut:
    instruction = db.get(OutsourceWorkInstruction, work_group.outsource_work_instruction_id)
    if instruction is None:
        raise HTTPException(status_code=404, detail="Outsource work instruction not found")

    partner = db.get(Partner, instruction.partner_id)

    item_rows = (
        db.execute(
            select(OutsourceWorkGroupItem, Lot, OrderLine, Product)
            .join(Lot, Lot.lot_id == OutsourceWorkGroupItem.lot_id)
            .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
            .join(Product, Product.product_id == Lot.product_id)
            .where(
                OutsourceWorkGroupItem.outsource_work_group_id
                == work_group.outsource_work_group_id
            )
            .order_by(Lot.lot_no.asc())
        )
        .all()
    )

    file_rows = (
        db.execute(
            select(OutsourceWorkInstructionFile)
            .where(
                OutsourceWorkInstructionFile.outsource_work_instruction_id
                == instruction.outsource_work_instruction_id
            )
            .order_by(OutsourceWorkInstructionFile.outsource_work_instruction_file_id.asc())
        )
        .scalars()
        .all()
    )

    lot_outputs: list[OutsourceWorkGroupLotOut] = []
    lot_nos: list[str] = []
    product_names: list[str] = []
    representative_lot_no: str | None = None
    representative_product_name: str | None = None

    for item, lot, order_line, product in item_rows:
        lot_nos.append(lot.lot_no)
        product_names.append(product.product_name)

        if lot.lot_id == work_group.representative_lot_id:
            representative_lot_no = lot.lot_no
            representative_product_name = product.product_name

        lot_outputs.append(
            OutsourceWorkGroupLotOut(
                outsource_work_group_item_id=item.outsource_work_group_item_id,
                lot_id=lot.lot_id,
                lot_no=lot.lot_no,
                order_no=order_line.order_no,
                line_no=order_line.line_no,
                product_code=product.product_code,
                product_name=product.product_name,
                lot_qty=lot.lot_qty,
                cuts_per_sheet=item.cuts_per_sheet,
                expected_output_qty=item.expected_output_qty,
            )
        )

    cancel_block_reason = get_cancel_block_reason(db, work_group)
    update_block_reason = get_update_block_reason(db, work_group)

    return OutsourceWorkGroupDetailOut(
        outsource_work_group_id=work_group.outsource_work_group_id,
        outsource_work_instruction_id=instruction.outsource_work_instruction_id,
        instruction_no=instruction.instruction_no,
        instruction_date=instruction.instruction_date,
        process_type=work_group.process_type,
        partner_id=instruction.partner_id,
        partner_name=partner.name if partner else None,
        group_seq=work_group.group_seq,
        status=normalized_work_group_status(work_group.status),
        status_name=display_work_group_status(work_group.status),
        is_bundle=work_group.is_bundle,
        representative_lot_id=work_group.representative_lot_id,
        representative_lot_no=representative_lot_no,
        representative_product_name=representative_product_name,
        lot_nos_text=", ".join(lot_nos),
        product_names_text=", ".join(dict.fromkeys(product_names)),
        sheet_qty=work_group.sheet_qty,
        length_m=work_group.length_m,
        sheet_cut_count=work_group.sheet_cut_count,
        fabric_lot_no=work_group.fabric_lot_no,
        can_cancel=cancel_block_reason is None,
        cancel_block_reason=cancel_block_reason,
        can_update=update_block_reason is None,
        update_block_reason=update_block_reason,
        memo=work_group.remark or instruction.memo,
        created_at=work_group.created_at,
        lots=lot_outputs,
        files=[
            OutsourceWorkInstructionFileOut.model_validate(file_row, from_attributes=True)
            for file_row in file_rows
        ],
    )
