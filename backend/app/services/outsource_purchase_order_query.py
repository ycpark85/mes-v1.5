from __future__ import annotations

from app.services.order_line_display import order_product_code, order_product_name, order_product_spec

from datetime import date

from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, aliased

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
from app.models.routing_template import RoutingTemplate
from app.schemas.outsource_work_instruction import (
    OutsourcePurchaseOrderTargetListOut,
    OutsourcePurchaseOrderTargetOut,
    OutsourcePurchaseOrderItemOut,
    OutsourcePurchaseOrderListItemOut,
    OutsourcePurchaseOrderListOut,
    OutsourcePurchaseOrderOut,
    OutsourceWorkInstructionFileOut,
)
from app.services.outsource_purchase_order_service import (
    require_outsource_partner_by_process_type,
)
from app.services.routing_policy import (
    INSPECTION_ONLY_TEMPLATE_NAME,
    get_available_process_types,
    get_purchase_order_inbound_partner_name,
    is_purchase_order_target_process,
)


OUTSOURCE_WORK_GROUP_STATUS_CANCELED = "CANCELED"


def build_purchase_order_out(
    db: Session,
    purchase_order: OutsourcePurchaseOrder,
) -> OutsourcePurchaseOrderOut:
    item_rows = (
        db.execute(
            select(OutsourcePurchaseOrderItem, Lot, OrderLine, Product)
            .join(Lot, Lot.lot_id == OutsourcePurchaseOrderItem.lot_id)
            .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
            .join(Product, Product.product_id == Lot.product_id)
            .where(
                OutsourcePurchaseOrderItem.outsource_purchase_order_id
                == purchase_order.outsource_purchase_order_id
            )
            .order_by(OutsourcePurchaseOrderItem.item_seq.asc())
        )
        .all()
    )

    items: list[OutsourcePurchaseOrderItemOut] = []

    for item, lot, order_line, product in item_rows:
        items.append(
            OutsourcePurchaseOrderItemOut(
                outsource_purchase_order_item_id=item.outsource_purchase_order_item_id,
                outsource_purchase_order_id=item.outsource_purchase_order_id,
                lot_id=item.lot_id,
                outsource_work_instruction_id=item.outsource_work_instruction_id,
                item_seq=item.item_seq,
                qty=item.qty,
                status=item.status,
                vendor_received_at=item.vendor_received_at,
                work_done_at=item.work_done_at,
                shipped_at=item.shipped_at,
                work_done_qty=item.work_done_qty,
                bad_qty=item.bad_qty,
                work_done_remark=item.work_done_remark,
                created_at=item.created_at,
                lot_no=lot.lot_no,
                order_no=order_line.order_no,
                line_no=order_line.line_no,
                product_code=order_product_code(order_line, product),
                mes_product_code=product.product_code if product else None,
                product_name=order_product_name(order_line, product),
                lot_qty=lot.lot_qty,
            )
        )

    outsource_partner = db.get(Partner, purchase_order.outsource_partner_id)
    inbound_partner = (
        db.get(Partner, purchase_order.inbound_partner_id)
        if purchase_order.inbound_partner_id
        else None
    )

    return OutsourcePurchaseOrderOut(
        outsource_purchase_order_id=purchase_order.outsource_purchase_order_id,
        purchase_order_no=purchase_order.purchase_order_no,
        purchase_order_date=purchase_order.purchase_order_date,
        due_date=purchase_order.due_date,
        process_type=purchase_order.process_type,
        outsource_partner_id=purchase_order.outsource_partner_id,
        inbound_partner_id=purchase_order.inbound_partner_id,
        work_description=purchase_order.work_description,
        remark=purchase_order.remark,
        qty=purchase_order.qty,
        unit_price=purchase_order.unit_price,
        supply_amount=purchase_order.supply_amount,
        vat_amount=purchase_order.vat_amount,
        total_amount=purchase_order.total_amount,
        created_at=purchase_order.created_at,
        updated_at=purchase_order.updated_at,
        outsource_partner_name=outsource_partner.name if outsource_partner else None,
        inbound_partner_name=inbound_partner.name if inbound_partner else None,
        items=items,
    )


def get_purchase_order_detail(
    db: Session,
    outsource_purchase_order_id: int,
) -> OutsourcePurchaseOrderOut:
    purchase_order = db.get(OutsourcePurchaseOrder, outsource_purchase_order_id)

    if not purchase_order:
        raise HTTPException(status_code=404, detail="Outsource purchase order not found")

    return build_purchase_order_out(db, purchase_order)


def build_purchase_order_item_out(
    db: Session,
    item: OutsourcePurchaseOrderItem,
) -> OutsourcePurchaseOrderItemOut:
    lot = db.get(Lot, item.lot_id)
    order_line = db.get(OrderLine, lot.order_line_id) if lot else None
    product = db.get(Product, lot.product_id) if lot else None

    return OutsourcePurchaseOrderItemOut(
        outsource_purchase_order_item_id=item.outsource_purchase_order_item_id,
        outsource_purchase_order_id=item.outsource_purchase_order_id,
        lot_id=item.lot_id,
        outsource_work_instruction_id=item.outsource_work_instruction_id,
        item_seq=item.item_seq,
        qty=item.qty,
        status=item.status,
        vendor_received_at=item.vendor_received_at,
        work_done_at=item.work_done_at,
        shipped_at=item.shipped_at,
        work_done_qty=item.work_done_qty,
        bad_qty=item.bad_qty,
        work_done_remark=item.work_done_remark,
        created_at=item.created_at,
        lot_no=lot.lot_no if lot else None,
        order_no=order_line.order_no if order_line else None,
        line_no=order_line.line_no if order_line else None,
        product_code=order_product_code(order_line, product),
        mes_product_code=product.product_code if product else None,
        product_name=order_product_name(order_line, product),
        lot_qty=lot.lot_qty if lot else None,
    )


def list_purchase_orders(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    process_type: str | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 100,
) -> OutsourcePurchaseOrderListOut:
    normalized_page = max(page, 1)
    normalized_size = min(max(size, 1), 200)
    conditions = []

    if date_from:
        conditions.append(OutsourcePurchaseOrder.purchase_order_date >= date_from)

    if date_to:
        conditions.append(OutsourcePurchaseOrder.purchase_order_date <= date_to)

    normalized_process_type = (process_type or "").strip().upper()

    if normalized_process_type in {"CUT", "PRINT"}:
        conditions.append(OutsourcePurchaseOrder.process_type == normalized_process_type)

    if q and q.strip():
        normalized_q = q.strip()
        like = f"%{normalized_q}%"
        conditions.append(
            (OutsourcePurchaseOrder.purchase_order_no == normalized_q.upper())
            | (OutsourcePurchaseOrder.remark.ilike(like))
            | (Partner.name.ilike(like))
        )

    count_stmt = (
        select(func.count())
        .select_from(OutsourcePurchaseOrder)
        .join(Partner, Partner.partner_id == OutsourcePurchaseOrder.outsource_partner_id)
    )

    stmt = (
        select(OutsourcePurchaseOrder, Partner)
        .join(Partner, Partner.partner_id == OutsourcePurchaseOrder.outsource_partner_id)
    )

    if conditions:
        count_stmt = count_stmt.where(*conditions)
        stmt = stmt.where(*conditions)

    total_count = db.execute(count_stmt).scalar_one()

    stmt = (
        stmt.order_by(
            OutsourcePurchaseOrder.purchase_order_date.desc(),
            OutsourcePurchaseOrder.outsource_purchase_order_id.desc(),
        )
        .offset((normalized_page - 1) * normalized_size)
        .limit(normalized_size)
    )

    rows = db.execute(stmt).all()

    items: list[OutsourcePurchaseOrderListItemOut] = []

    for purchase_order, outsource_partner in rows:
        items.append(
            OutsourcePurchaseOrderListItemOut(
                outsource_purchase_order_id=purchase_order.outsource_purchase_order_id,
                purchase_order_no=purchase_order.purchase_order_no,
                purchase_order_date=purchase_order.purchase_order_date,
                process_type=purchase_order.process_type,
                outsource_partner_id=purchase_order.outsource_partner_id,
                outsource_partner_name=outsource_partner.name if outsource_partner else None,
                qty=purchase_order.qty,
                remark=purchase_order.remark,
                created_at=purchase_order.created_at,
            )
        )

    return OutsourcePurchaseOrderListOut(
        items=items,
        total_count=total_count,
        page=normalized_page,
        size=normalized_size,
    )


def list_purchase_order_targets(
    db: Session,
    *,
    process_type: str,
    page: int = 1,
    size: int = 100,
) -> OutsourcePurchaseOrderTargetListOut:
    normalized_process_type = (process_type or "").strip().upper()
    normalized_page = max(page, 1)
    normalized_size = min(max(size, 1), 200)

    if normalized_process_type not in {"CUT", "PRINT"}:
        raise HTTPException(
            status_code=400,
            detail="process_type must be CUT or PRINT",
        )

    outsource_partner = require_outsource_partner_by_process_type(
        db=db,
        process_type=normalized_process_type,
    )

    order_partner = aliased(Partner)
    normalized_template_name = func.replace(RoutingTemplate.template_name, " ", "")

    target_conditions = [
        OutsourceWorkInstructionItem.is_active.is_(True),
        OutsourceWorkGroupItem.lot_id == Lot.lot_id,
        (
            OutsourceWorkGroup.status.is_(None)
            | (OutsourceWorkGroup.status != OUTSOURCE_WORK_GROUP_STATUS_CANCELED)
        ),
        ~exists(
            select(1)
            .select_from(OutsourcePurchaseOrderGroup)
            .join(
                OutsourcePurchaseOrder,
                OutsourcePurchaseOrder.outsource_purchase_order_id
                == OutsourcePurchaseOrderGroup.outsource_purchase_order_id,
            )
            .where(
                OutsourcePurchaseOrderGroup.outsource_work_group_id
                == OutsourceWorkGroup.outsource_work_group_id,
                OutsourcePurchaseOrder.process_type == normalized_process_type,
            )
        ),
        ~exists(
            select(1)
            .select_from(OutsourcePurchaseOrderItem)
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
                OutsourcePurchaseOrderItem.lot_id == Lot.lot_id,
                OutsourcePurchaseOrder.process_type == normalized_process_type,
            )
        ),
    ]

    if normalized_process_type == "PRINT":
        target_conditions.append(RoutingTemplate.template_name.like("%\uc778\uc1c4%"))
    else:
        target_conditions.append(
            or_(
                RoutingTemplate.template_name.is_(None),
                normalized_template_name != INSPECTION_ONLY_TEMPLATE_NAME,
            )
        )

    base_group_stmt = (
        select(
            OutsourceWorkGroup.outsource_work_group_id.label("outsource_work_group_id"),
            OutsourceWorkInstruction.instruction_date.label("instruction_date"),
            OutsourceWorkInstruction.instruction_no.label("instruction_no"),
        )
        .join(
            OutsourceWorkInstructionItem,
            OutsourceWorkInstructionItem.outsource_work_instruction_id
            == OutsourceWorkInstruction.outsource_work_instruction_id,
        )
        .join(
            OutsourceWorkGroup,
            OutsourceWorkGroup.outsource_work_instruction_id
            == OutsourceWorkInstruction.outsource_work_instruction_id,
        )
        .join(
            OutsourceWorkGroupItem,
            OutsourceWorkGroupItem.outsource_work_group_id
            == OutsourceWorkGroup.outsource_work_group_id,
        )
        .join(Lot, Lot.lot_id == OutsourceWorkInstructionItem.lot_id)
        .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
        .join(Product, Product.product_id == Lot.product_id)
        .join(RoutingTemplate, RoutingTemplate.routing_template_id == Product.routing_template_id)
        .where(*target_conditions)
        .group_by(
            OutsourceWorkGroup.outsource_work_group_id,
            OutsourceWorkInstruction.instruction_date,
            OutsourceWorkInstruction.instruction_no,
        )
    )

    count_stmt = select(func.count()).select_from(base_group_stmt.subquery())
    total_count = db.execute(count_stmt).scalar_one()

    paged_group_ids = (
        db.execute(
            base_group_stmt.order_by(
                OutsourceWorkInstruction.instruction_date.desc(),
                OutsourceWorkInstruction.instruction_no.desc(),
                OutsourceWorkGroup.outsource_work_group_id.desc(),
            )
            .offset((normalized_page - 1) * normalized_size)
            .limit(normalized_size)
        )
        .scalars()
        .all()
    )

    if not paged_group_ids:
        return OutsourcePurchaseOrderTargetListOut(
            items=[],
            total_count=total_count,
            page=normalized_page,
            size=normalized_size,
        )

    rows = (
        db.execute(
            select(
                OutsourceWorkInstruction,
                OutsourceWorkInstructionItem,
                OutsourceWorkGroup,
                OutsourceWorkGroupItem,
                Lot,
                OrderLine,
                Product,
                Partner,
                RoutingTemplate,
                order_partner,
            )
            .join(
                OutsourceWorkInstructionItem,
                OutsourceWorkInstructionItem.outsource_work_instruction_id
                == OutsourceWorkInstruction.outsource_work_instruction_id,
            )
            .join(
                OutsourceWorkGroup,
                OutsourceWorkGroup.outsource_work_instruction_id
                == OutsourceWorkInstruction.outsource_work_instruction_id,
            )
            .join(
                OutsourceWorkGroupItem,
                OutsourceWorkGroupItem.outsource_work_group_id
                == OutsourceWorkGroup.outsource_work_group_id,
            )
            .join(Lot, Lot.lot_id == OutsourceWorkInstructionItem.lot_id)
            .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
            .join(Product, Product.product_id == Lot.product_id)
            .join(RoutingTemplate, RoutingTemplate.routing_template_id == Product.routing_template_id)
            .join(order_partner, order_partner.partner_id == OrderLine.partner_id)
            .join(Partner, Partner.partner_id == OutsourceWorkInstruction.partner_id)
            .where(
                *target_conditions,
                OutsourceWorkGroup.outsource_work_group_id.in_(paged_group_ids),
            )
            .order_by(
                OutsourceWorkInstruction.instruction_date.desc(),
                OutsourceWorkInstruction.instruction_no.desc(),
                Lot.lot_no.asc(),
            )
        )
        .all()
    )

    instruction_ids = list(
        {
            instruction.outsource_work_instruction_id
            for instruction, _, _, _, _, _, _, _, _, _ in rows
        }
    )

    file_map: dict[int, list[OutsourceWorkInstructionFileOut]] = {}

    if instruction_ids:
        file_rows = (
            db.execute(
                select(OutsourceWorkInstructionFile).where(
                    OutsourceWorkInstructionFile.outsource_work_instruction_id.in_(instruction_ids)
                )
            )
            .scalars()
            .all()
        )

        for file_row in file_rows:
            instruction_id = file_row.outsource_work_instruction_id

            if instruction_id not in file_map:
                file_map[instruction_id] = []

            file_map[instruction_id].append(
                OutsourceWorkInstructionFileOut.model_validate(
                    file_row,
                    from_attributes=True,
                )
            )

    items: list[OutsourcePurchaseOrderTargetOut] = []

    for (
        instruction,
        item,
        work_group,
        _work_group_item,
        lot,
        order_line,
        product,
        _instruction_partner,
        routing_template,
        source_partner,
    ) in rows:
        if not is_purchase_order_target_process(
            normalized_process_type,
            routing_template.template_name,
        ):
            continue

        available_process_types = get_available_process_types(routing_template.template_name)

        items.append(
            OutsourcePurchaseOrderTargetOut(
                outsource_work_instruction_id=instruction.outsource_work_instruction_id,
                outsource_work_instruction_item_id=item.outsource_work_instruction_item_id,
                outsource_work_group_id=work_group.outsource_work_group_id,
                instruction_no=instruction.instruction_no,
                instruction_date=instruction.instruction_date,
                process_type=normalized_process_type,
                group_seq=work_group.group_seq,
                lot_id=lot.lot_id,
                lot_no=lot.lot_no,
                is_rework=lot.parent_lot_id is not None,
                order_line_id=order_line.order_line_id,
                order_no=order_line.order_no,
                line_no=order_line.line_no,
                product_id=product.product_id,
                product_code=order_product_code(order_line, product),
                mes_product_code=product.product_code if product else None,
                product_name=order_product_name(order_line, product),
                representative_lot_id=work_group.representative_lot_id,
                customer_partner_id=source_partner.partner_id,
                customer_partner_name=source_partner.name,
                lot_qty=lot.lot_qty,
                outsource_partner_id=outsource_partner.partner_id,
                outsource_partner_name=outsource_partner.name,
                inbound_partner_name=get_purchase_order_inbound_partner_name(
                    normalized_process_type,
                    routing_template.template_name,
                ),
                is_bundle=instruction.is_bundle,
                memo=instruction.memo,
                files=file_map.get(instruction.outsource_work_instruction_id, []),
                panel_width_mm=product.panel_width_mm,
                panel_length_mm=product.panel_length_mm,
                product_spec=order_product_spec(order_line, product),
                cut_qty_per_panel=product.cut_qty_per_panel,
                length_m=work_group.length_m,
                sheet_qty=work_group.sheet_qty,
                is_print_product="PRINT" in available_process_types,
            )
        )

    return OutsourcePurchaseOrderTargetListOut(
        items=items,
        total_count=total_count,
        page=normalized_page,
        size=normalized_size,
    )
