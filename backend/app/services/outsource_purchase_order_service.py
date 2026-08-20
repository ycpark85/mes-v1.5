from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.lot import Lot
from app.models.outsource_purchase_order import OutsourcePurchaseOrder
from app.models.outsource_purchase_order_group import OutsourcePurchaseOrderGroup
from app.models.outsource_purchase_order_item import OutsourcePurchaseOrderItem
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction_item import OutsourceWorkInstructionItem
from app.models.partner import Partner
from app.models.product import Product
from app.models.routing_template import RoutingTemplate
from app.schemas.outsource_work_instruction import (
    OutsourcePurchaseOrderCreate,
    OutsourcePurchaseOrderCutSnapshot,
    OutsourcePurchaseOrderPrintSnapshot,
)
from app.services.production_daily_query import refresh_order_line_snapshots_for_lots
from app.services.routing_policy import (
    get_outsource_partner_name_by_process_type as _get_outsource_partner_name_by_process_type,
    is_purchase_order_target_process,
)


OUTSOURCE_WORK_GROUP_STATUS_CANCELED = "CANCELED"


def create_purchase_order(
    db: Session,
    payload: OutsourcePurchaseOrderCreate,
) -> OutsourcePurchaseOrder:
    normalized_process_type = (payload.process_type or "").strip().upper()

    if normalized_process_type not in ("CUT", "PRINT"):
        raise HTTPException(status_code=409, detail="Invalid process_type")

    outsource_partner = require_outsource_partner_by_process_type(
        db=db,
        process_type=normalized_process_type,
    )

    if payload.inbound_partner_id:
        inbound_partner = db.get(Partner, payload.inbound_partner_id)

        if not inbound_partner or not inbound_partner.is_active:
            raise HTTPException(
                status_code=404,
                detail="Inbound partner not found or inactive",
            )

    lot_ids = [item.lot_id for item in payload.items]

    if len(lot_ids) != len(set(lot_ids)):
        raise HTTPException(
            status_code=409,
            detail="Duplicate lot exists in purchase order items",
        )

    lot_count = (
        db.execute(
            select(func.count())
            .select_from(Lot)
            .where(Lot.lot_id.in_(lot_ids))
        )
        .scalar_one()
    )

    if int(lot_count) != len(set(lot_ids)):
        raise HTTPException(status_code=409, detail="Some lots do not exist")

    already_ordered_lot_id = (
        db.execute(
            select(OutsourcePurchaseOrderItem.lot_id)
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
            .where(OutsourcePurchaseOrder.process_type == normalized_process_type)
            .where(OutsourcePurchaseOrderItem.lot_id.in_(lot_ids))
            .limit(1)
        )
        .scalar_one_or_none()
    )

    if already_ordered_lot_id is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"LOT is already purchase ordered for process "
                f"{normalized_process_type}: lot_id={already_ordered_lot_id}"
            ),
        )

    if any(item.outsource_work_instruction_id is None for item in payload.items):
        raise HTTPException(
            status_code=409,
            detail="Outsource work instruction is required for purchase order items",
        )

    instruction_ids = {
        int(item.outsource_work_instruction_id)
        for item in payload.items
        if item.outsource_work_instruction_id is not None
    }

    work_group_rows = (
        db.execute(
            select(
                OutsourceWorkGroup.outsource_work_group_id,
                OutsourceWorkGroup.outsource_work_instruction_id,
                OutsourceWorkGroupItem.lot_id,
            )
            .join(
                OutsourceWorkGroupItem,
                OutsourceWorkGroupItem.outsource_work_group_id
                == OutsourceWorkGroup.outsource_work_group_id,
            )
            .join(
                OutsourceWorkInstructionItem,
                (
                    OutsourceWorkInstructionItem.outsource_work_instruction_id
                    == OutsourceWorkGroup.outsource_work_instruction_id
                )
                & (OutsourceWorkInstructionItem.lot_id == OutsourceWorkGroupItem.lot_id)
                & (OutsourceWorkInstructionItem.is_active.is_(True)),
            )
            .where(
                OutsourceWorkGroup.outsource_work_instruction_id.in_(instruction_ids),
                OutsourceWorkGroupItem.lot_id.in_(lot_ids),
                (
                    OutsourceWorkGroup.status.is_(None)
                    | (OutsourceWorkGroup.status != OUTSOURCE_WORK_GROUP_STATUS_CANCELED)
                ),
            )
            .with_for_update()
        )
        .all()
    )

    work_group_id_by_item_key: dict[tuple[int, int], int] = {}
    for work_group_id, instruction_id, lot_id in work_group_rows:
        work_group_id_by_item_key[(int(instruction_id), int(lot_id))] = int(work_group_id)

    selected_lot_ids_by_work_group_id: dict[int, set[int]] = {}
    ordered_work_group_ids: list[int] = []

    for item in payload.items:
        key = (int(item.outsource_work_instruction_id), int(item.lot_id))
        work_group_id = work_group_id_by_item_key.get(key)

        if work_group_id is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Purchase order item is not connected to an active outsource "
                    f"work group: lot_id={item.lot_id}"
                ),
            )

        if work_group_id not in selected_lot_ids_by_work_group_id:
            selected_lot_ids_by_work_group_id[work_group_id] = set()
            ordered_work_group_ids.append(work_group_id)

        selected_lot_ids_by_work_group_id[work_group_id].add(int(item.lot_id))

    group_lot_rows = (
        db.execute(
            select(
                OutsourceWorkGroupItem.outsource_work_group_id,
                OutsourceWorkGroupItem.lot_id,
            ).where(
                OutsourceWorkGroupItem.outsource_work_group_id.in_(ordered_work_group_ids)
            )
        )
        .all()
    )

    expected_lot_ids_by_work_group_id: dict[int, set[int]] = {}
    for work_group_id, lot_id in group_lot_rows:
        expected_lot_ids_by_work_group_id.setdefault(int(work_group_id), set()).add(int(lot_id))

    for work_group_id, selected_lot_ids in selected_lot_ids_by_work_group_id.items():
        expected_lot_ids = expected_lot_ids_by_work_group_id.get(work_group_id, set())
        if selected_lot_ids != expected_lot_ids:
            raise HTTPException(
                status_code=409,
                detail=(
                    "All LOTs in an outsource work group must be purchase ordered together: "
                    f"outsource_work_group_id={work_group_id}"
                ),
            )

    already_ordered_work_group_id = (
        db.execute(
            select(OutsourcePurchaseOrderGroup.outsource_work_group_id)
            .join(
                OutsourcePurchaseOrder,
                OutsourcePurchaseOrder.outsource_purchase_order_id
                == OutsourcePurchaseOrderGroup.outsource_purchase_order_id,
            )
            .where(
                OutsourcePurchaseOrderGroup.outsource_work_group_id.in_(ordered_work_group_ids),
                OutsourcePurchaseOrder.process_type == normalized_process_type,
            )
            .limit(1)
        )
        .scalar_one_or_none()
    )

    if already_ordered_work_group_id is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Outsource work group is already purchase ordered: "
                f"outsource_work_group_id={already_ordered_work_group_id}"
            ),
        )

    lot_rows = (
        db.execute(
            select(Lot, Product, RoutingTemplate)
            .join(Product, Product.product_id == Lot.product_id)
            .join(
                RoutingTemplate,
                RoutingTemplate.routing_template_id == Product.routing_template_id,
            )
            .where(Lot.lot_id.in_(lot_ids))
        )
        .all()
    )

    for lot, _product, routing_template in lot_rows:
        if not is_purchase_order_target_process(
            normalized_process_type,
            routing_template.template_name,
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"LOT {lot.lot_no} cannot be purchase ordered for "
                    f"process {normalized_process_type}"
                ),
            )

    form_snapshot_json = None

    if payload.form_snapshot:
        if normalized_process_type == "CUT":
            form_snapshot_json = OutsourcePurchaseOrderCutSnapshot.model_validate(
                payload.form_snapshot
            ).model_dump()
        elif normalized_process_type == "PRINT":
            form_snapshot_json = OutsourcePurchaseOrderPrintSnapshot.model_validate(
                payload.form_snapshot
            ).model_dump()

    purchase_order = OutsourcePurchaseOrder(
        purchase_order_no=_generate_purchase_order_no(
            db,
            normalized_process_type,
            payload.purchase_order_date,
        ),
        purchase_order_date=payload.purchase_order_date,
        due_date=payload.due_date,
        process_type=normalized_process_type,
        outsource_partner_id=outsource_partner.partner_id,
        inbound_partner_id=payload.inbound_partner_id,
        work_description=payload.work_description,
        remark=payload.remark,
        form_snapshot_json=form_snapshot_json,
        qty=payload.qty,
        unit_price=payload.unit_price,
        supply_amount=payload.supply_amount,
        vat_amount=payload.vat_amount,
        total_amount=payload.total_amount,
    )
    db.add(purchase_order)
    db.flush()

    for item in payload.items:
        db.add(
            OutsourcePurchaseOrderItem(
                outsource_purchase_order_id=purchase_order.outsource_purchase_order_id,
                lot_id=item.lot_id,
                outsource_work_instruction_id=item.outsource_work_instruction_id,
                item_seq=item.item_seq,
                qty=item.qty,
                status=None,
            )
        )

    for index, work_group_id in enumerate(ordered_work_group_ids, start=1):
        db.add(
            OutsourcePurchaseOrderGroup(
                outsource_purchase_order_id=purchase_order.outsource_purchase_order_id,
                outsource_work_group_id=work_group_id,
                item_seq=index,
                status=None,
            )
        )

    db.flush()
    return purchase_order


def _generate_purchase_order_no(db: Session, process_type: str, order_date: date) -> str:
    normalized = (process_type or "").strip().upper()
    prefix = "OCUT" if normalized == "CUT" else "OPRT"
    ymd = order_date.strftime("%Y%m%d")
    like_prefix = f"{prefix}-{ymd}-"

    last_no = (
        db.execute(
            select(OutsourcePurchaseOrder.purchase_order_no)
            .where(OutsourcePurchaseOrder.purchase_order_no.like(f"{like_prefix}%"))
            .order_by(OutsourcePurchaseOrder.purchase_order_no.desc())
            .limit(1)
        )
        .scalar_one_or_none()
    )

    if last_no:
        try:
            seq = int(last_no.split("-")[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1

    return f"{prefix}-{ymd}-{seq:03d}"


def require_outsource_partner_by_process_type(
    db: Session,
    process_type: str,
) -> Partner:
    partner_name = _get_outsource_partner_name_by_process_type(process_type)

    if partner_name:
        outsource_partner = (
            db.execute(
                select(Partner)
                .where(Partner.name == partner_name)
                .where(Partner.partner_type == "VENDOR")
                .where(Partner.is_active.is_(True))
            )
            .scalar_one_or_none()
        )

        if outsource_partner is not None:
            return outsource_partner

    raise HTTPException(
        status_code=409,
        detail=(
            f"외주처를 찾을 수 없습니다. 거래처 기준정보에 "
            f"[{partner_name}] VENDOR 거래처를 활성 상태로 등록하세요."
        ),
    )

