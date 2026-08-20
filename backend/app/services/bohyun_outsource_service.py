from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Iterable, Mapping

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy.orm import Session

from app.core.time import utc_now

from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction import OutsourceWorkInstruction
from app.models.partner import Partner
from app.models.product import Product
from app.models.routing_template import RoutingTemplate
from app.schemas.outsource_work_instruction import (
    BohyunOutsourceGroupItemOut,
    BohyunOutsourceGroupListItemOut,
    BohyunOutsourceGroupListOut,
)
from app.services.production_daily_query import refresh_order_line_snapshots_for_work_groups
from app.services.routing_policy import (
    get_available_process_types as _get_available_process_types,
    get_outsource_partner_name_by_process_type as _get_outsource_partner_name_by_process_type,
)


BOHYUN_DB_STATUS_VENDOR_RECEIVED = "VENDOR_RECEIVED"
BOHYUN_DB_STATUS_WORK_DONE = "WORK_DONE"
BOHYUN_DB_STATUS_SHIPPED = "SHIPPED"
OUTSOURCE_WORK_GROUP_STATUS_CANCELED = "CANCELED"

BOHYUN_UI_STATUS_WAITING_INBOUND = "WAITING_INBOUND"
BOHYUN_UI_STATUS_INBOUNDED = "INBOUNDED"
BOHYUN_UI_STATUS_WORK_DONE = "WORK_DONE"
BOHYUN_UI_STATUS_SHIPPED = "SHIPPED"

BOHYUN_VALID_PROCESS_TYPES = ("CUT", "PRINT", "DIECUT")
BOHYUN_VALID_UI_STATUSES = (
    BOHYUN_UI_STATUS_WAITING_INBOUND,
    BOHYUN_UI_STATUS_INBOUNDED,
    BOHYUN_UI_STATUS_WORK_DONE,
    BOHYUN_UI_STATUS_SHIPPED,
)


def to_bohyun_ui_status(db_status: str | None) -> str:
    if db_status == BOHYUN_DB_STATUS_VENDOR_RECEIVED:
        return BOHYUN_UI_STATUS_INBOUNDED

    if db_status == BOHYUN_DB_STATUS_WORK_DONE:
        return BOHYUN_UI_STATUS_WORK_DONE

    if db_status == BOHYUN_DB_STATUS_SHIPPED:
        return BOHYUN_UI_STATUS_SHIPPED

    return BOHYUN_UI_STATUS_WAITING_INBOUND


def get_bohyun_inbound_source_name(process_type: str) -> str | None:
    return _get_outsource_partner_name_by_process_type(process_type)


def list_bohyun_outsource_groups(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    process_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 100,
    include_processing_fee: bool = True,
) -> BohyunOutsourceGroupListOut:
    if process_type and process_type not in BOHYUN_VALID_PROCESS_TYPES:
        raise HTTPException(status_code=409, detail="Invalid process_type")

    if status and status not in BOHYUN_VALID_UI_STATUSES:
        raise HTTPException(status_code=409, detail="Invalid status")

    stmt = (
        select(OutsourceWorkGroup, OutsourceWorkInstruction, Partner)
        .join(
            OutsourceWorkInstruction,
            OutsourceWorkInstruction.outsource_work_instruction_id
            == OutsourceWorkGroup.outsource_work_instruction_id,
        )
        .join(Partner, Partner.partner_id == OutsourceWorkInstruction.partner_id)
        .where(
            OutsourceWorkGroup.process_type.in_(BOHYUN_VALID_PROCESS_TYPES),
            (
                OutsourceWorkGroup.status.is_(None)
                | (OutsourceWorkGroup.status != OUTSOURCE_WORK_GROUP_STATUS_CANCELED)
            ),
        )
        .order_by(
            OutsourceWorkInstruction.instruction_date.desc(),
            OutsourceWorkInstruction.instruction_no.desc(),
            OutsourceWorkGroup.group_seq.asc(),
        )
    )

    if date_from:
        stmt = stmt.where(OutsourceWorkInstruction.instruction_date >= date_from)

    if date_to:
        stmt = stmt.where(OutsourceWorkInstruction.instruction_date <= date_to)

    if process_type:
        stmt = stmt.where(OutsourceWorkGroup.process_type == process_type)

    if status == BOHYUN_UI_STATUS_WAITING_INBOUND:
        stmt = stmt.where(OutsourceWorkGroup.status.is_(None))
    elif status == BOHYUN_UI_STATUS_INBOUNDED:
        stmt = stmt.where(OutsourceWorkGroup.status == BOHYUN_DB_STATUS_VENDOR_RECEIVED)
    elif status == BOHYUN_UI_STATUS_WORK_DONE:
        stmt = stmt.where(OutsourceWorkGroup.status == BOHYUN_DB_STATUS_WORK_DONE)
    elif status == BOHYUN_UI_STATUS_SHIPPED:
        stmt = stmt.where(OutsourceWorkGroup.status == BOHYUN_DB_STATUS_SHIPPED)
    else:
        stmt = stmt.where(
            or_(
                OutsourceWorkGroup.status.is_(None),
                OutsourceWorkGroup.status != BOHYUN_DB_STATUS_SHIPPED,
            )
        )

    if q and q.strip():
        normalized_q = q.strip()
        like = f"%{normalized_q}%"

        exists_item_stmt = (
            select(OutsourceWorkGroupItem.outsource_work_group_item_id)
            .join(Lot, Lot.lot_id == OutsourceWorkGroupItem.lot_id)
            .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
            .join(Product, Product.product_id == Lot.product_id)
            .where(
                OutsourceWorkGroupItem.outsource_work_group_id
                == OutsourceWorkGroup.outsource_work_group_id
            )
            .where(
                (Lot.lot_no.ilike(like))
                | (OrderLine.order_no == normalized_q.upper())
                | (Product.product_code.ilike(like))
                | (Product.product_name.ilike(like))
            )
            .limit(1)
        )

        stmt = stmt.where(
            (OutsourceWorkInstruction.instruction_no.ilike(like))
            | (Partner.name.ilike(like))
            | exists(exists_item_stmt)
        )

    template_name = func.coalesce(RoutingTemplate.template_name, "")
    is_print_product = template_name.contains("인쇄")
    target_item_exists = (
        select(OutsourceWorkGroupItem.outsource_work_group_item_id)
        .join(Lot, Lot.lot_id == OutsourceWorkGroupItem.lot_id)
        .join(Product, Product.product_id == Lot.product_id)
        .join(
            RoutingTemplate,
            RoutingTemplate.routing_template_id == Product.routing_template_id,
        )
        .where(
            OutsourceWorkGroupItem.outsource_work_group_id
            == OutsourceWorkGroup.outsource_work_group_id,
            or_(
                and_(
                    OutsourceWorkGroup.process_type == "CUT",
                    not_(is_print_product),
                ),
                and_(
                    OutsourceWorkGroup.process_type == "PRINT",
                    is_print_product,
                ),
                OutsourceWorkGroup.process_type == "DIECUT",
            ),
        )
        .limit(1)
    )
    stmt = stmt.where(exists(target_item_exists))
    summary_stmt = stmt.with_only_columns(
        OutsourceWorkGroup.outsource_processing_fee,
        maintain_column_froms=True,
    ).order_by(None).subquery()
    total_count, processing_fee_total = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(summary_stmt.c.outsource_processing_fee), 0),
        ).select_from(summary_stmt)
    ).one()
    rows = db.execute(
        stmt.offset((page - 1) * size).limit(size)
    ).all()
    item_rows_by_group_id = _get_bohyun_target_group_item_rows_by_group_ids(
        db,
        {
            work_group.outsource_work_group_id: work_group.process_type
            for work_group, _, _ in rows
        },
    )
    result_items: list[BohyunOutsourceGroupListItemOut] = []

    for work_group, instruction, partner in rows:
        group_item_rows = item_rows_by_group_id.get(
            work_group.outsource_work_group_id,
            [],
        )

        if not group_item_rows:
            continue

        representative_row = next(
            (
                row
                for row in group_item_rows
                if row[1].lot_id == work_group.representative_lot_id
            ),
            group_item_rows[0],
        )
        representative_lot = representative_row[1]
        representative_product = representative_row[3]
        representative_product_name = representative_product.product_name

        group_items: list[BohyunOutsourceGroupItemOut] = []
        lot_nos: list[str] = []
        product_names: list[str] = []

        for group_item, lot, order_line, product, _ in group_item_rows:
            if lot.lot_no:
                lot_nos.append(lot.lot_no)

            if product.product_name:
                product_names.append(product.product_name)

            group_items.append(
                BohyunOutsourceGroupItemOut(
                    outsource_work_group_item_id=group_item.outsource_work_group_item_id,
                    lot_id=lot.lot_id,
                    lot_no=lot.lot_no,
                    order_no=order_line.order_no,
                    line_no=order_line.line_no,
                    product_id=product.product_id,
                    product_code=product.product_code,
                    product_name=product.product_name,
                    cuts_per_sheet=group_item.cuts_per_sheet,
                    expected_output_qty=group_item.expected_output_qty,
                    actual_output_qty=group_item.actual_output_qty,
                    remark=group_item.remark,
                )
            )

        display_product_names = (
            [representative_product_name]
            if representative_product_name
            else list(dict.fromkeys(product_names))
        )

        result_items.append(
            BohyunOutsourceGroupListItemOut(
                outsource_work_group_id=work_group.outsource_work_group_id,
                outsource_work_instruction_id=instruction.outsource_work_instruction_id,
                representative_lot_id=representative_lot.lot_id,
                representative_product_name=representative_product_name,
                instruction_no=instruction.instruction_no,
                instruction_date=instruction.instruction_date,
                process_type=work_group.process_type,
                partner_id=partner.partner_id,
                partner_name=partner.name,
                inbound_source_name=get_bohyun_inbound_source_name(work_group.process_type),
                is_bundle=work_group.is_bundle,
                group_seq=work_group.group_seq,
                sheet_qty=work_group.sheet_qty,
                work_done_sheet_qty=work_group.work_done_sheet_qty,
                length_m=work_group.length_m,
                sheet_cut_count=work_group.sheet_cut_count,
                status=to_bohyun_ui_status(work_group.status),
                vendor_received_at=work_group.vendor_received_at,
                work_done_at=work_group.work_done_at,
                shipped_at=work_group.shipped_at,
                outsource_processing_fee=(
                    work_group.outsource_processing_fee
                    if include_processing_fee
                    else None
                ),
                work_done_remark=work_group.work_done_remark,
                lot_nos=lot_nos,
                product_names=display_product_names,
                items=group_items,
            )
        )

    return BohyunOutsourceGroupListOut(
        items=result_items,
        total_count=int(total_count or 0),
        page=page,
        size=size,
        processing_fee_total=(
            processing_fee_total
            if include_processing_fee
            else Decimal("0")
        ),
    )


def inbound_bohyun_outsource_group(db: Session, group_id: int) -> None:
    work_group = _require_bohyun_work_group(db, group_id)

    if work_group.status == BOHYUN_DB_STATUS_SHIPPED:
        raise HTTPException(
            status_code=409,
            detail="Already shipped group cannot be inbounded",
        )

    if work_group.status == BOHYUN_DB_STATUS_WORK_DONE:
        raise HTTPException(
            status_code=409,
            detail="Already work done group cannot be inbounded",
        )

    if work_group.status == BOHYUN_DB_STATUS_VENDOR_RECEIVED:
        raise HTTPException(
            status_code=409,
            detail="Already inbounded",
        )

    work_group.status = BOHYUN_DB_STATUS_VENDOR_RECEIVED
    work_group.vendor_received_at = utc_now()

    refresh_order_line_snapshots_for_work_groups(
        db,
        {work_group.outsource_work_group_id},
    )

    db.flush()


def complete_bohyun_outsource_group_work(
    db: Session,
    group_id: int,
    *,
    work_done_sheet_qty: int,
    outsource_processing_fee: Decimal | None,
    remark: str | None,
) -> None:
    work_group = _require_bohyun_work_group(db, group_id)

    if work_group.status == BOHYUN_DB_STATUS_SHIPPED:
        raise HTTPException(
            status_code=409,
            detail="Already shipped group cannot be work done",
        )

    if work_group.status == BOHYUN_DB_STATUS_WORK_DONE:
        raise HTTPException(
            status_code=409,
            detail="Already work done",
        )

    if work_group.status != BOHYUN_DB_STATUS_VENDOR_RECEIVED:
        raise HTTPException(
            status_code=409,
            detail="Only inbounded group can be work done",
        )

    group_items = (
        db.execute(
            select(OutsourceWorkGroupItem)
            .where(
                OutsourceWorkGroupItem.outsource_work_group_id
                == work_group.outsource_work_group_id
            )
            .order_by(OutsourceWorkGroupItem.outsource_work_group_item_id.asc())
        )
        .scalars()
        .all()
    )

    if not group_items:
        raise HTTPException(
            status_code=409,
            detail="Outsource work group has no items",
        )

    for group_item in group_items:
        group_item.actual_output_qty = work_done_sheet_qty * group_item.cuts_per_sheet

    work_group.status = BOHYUN_DB_STATUS_WORK_DONE
    work_group.work_done_at = utc_now()
    work_group.work_done_sheet_qty = work_done_sheet_qty
    work_group.outsource_processing_fee = outsource_processing_fee
    work_group.work_done_remark = remark

    refresh_order_line_snapshots_for_work_groups(
        db,
        {work_group.outsource_work_group_id},
    )

    db.flush()


def ship_bohyun_outsource_groups(db: Session, group_ids: Iterable[int]) -> None:
    requested_group_ids = list(dict.fromkeys(group_ids))

    work_groups = (
        db.execute(
            select(OutsourceWorkGroup)
            .where(OutsourceWorkGroup.outsource_work_group_id.in_(requested_group_ids))
        )
        .scalars()
        .all()
    )

    if len(work_groups) != len(requested_group_ids):
        raise HTTPException(
            status_code=404,
            detail="Some outsource work groups were not found",
        )

    invalid_target_groups = [
        work_group
        for work_group in work_groups
        if not _is_bohyun_target_work_group_by_db(db, work_group)
    ]

    if invalid_target_groups:
        raise HTTPException(
            status_code=404,
            detail="Some Bohyun outsource work groups were not found",
        )

    invalid_groups = [
        work_group
        for work_group in work_groups
        if work_group.status != BOHYUN_DB_STATUS_WORK_DONE
    ]

    if invalid_groups:
        raise HTTPException(
            status_code=409,
            detail="Only work done groups can be shipped",
        )

    now = utc_now()

    for work_group in work_groups:
        work_group.status = BOHYUN_DB_STATUS_SHIPPED
        work_group.shipped_at = now

    refresh_order_line_snapshots_for_work_groups(db, requested_group_ids)

    db.flush()


def _require_bohyun_work_group(db: Session, group_id: int) -> OutsourceWorkGroup:
    work_group = db.get(OutsourceWorkGroup, group_id)

    if not work_group:
        raise HTTPException(
            status_code=404,
            detail="Outsource work group not found",
        )

    if work_group.status == OUTSOURCE_WORK_GROUP_STATUS_CANCELED:
        raise HTTPException(
            status_code=409,
            detail="Canceled outsource work group cannot be processed",
        )

    if not _is_bohyun_target_work_group_by_db(db, work_group):
        raise HTTPException(
            status_code=404,
            detail="Bohyun outsource work group not found",
        )

    return work_group


def _get_bohyun_target_group_item_rows(
    db: Session,
    work_group: OutsourceWorkGroup,
):
    return _get_bohyun_target_group_item_rows_by_group_ids(
        db,
        {work_group.outsource_work_group_id: work_group.process_type},
    ).get(work_group.outsource_work_group_id, [])


def _get_bohyun_target_group_item_rows_by_group_ids(
    db: Session,
    process_type_by_group_id: Mapping[int, str],
):
    normalized_group_ids = list(process_type_by_group_id)
    if not normalized_group_ids:
        return {}

    group_item_rows = (
        db.execute(
            select(
                OutsourceWorkGroupItem,
                Lot,
                OrderLine,
                Product,
                RoutingTemplate,
            )
            .join(Lot, Lot.lot_id == OutsourceWorkGroupItem.lot_id)
            .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
            .join(Product, Product.product_id == Lot.product_id)
            .join(
                RoutingTemplate,
                RoutingTemplate.routing_template_id == Product.routing_template_id,
            )
            .where(
                OutsourceWorkGroupItem.outsource_work_group_id.in_(
                    normalized_group_ids
                )
            )
            .order_by(
                OutsourceWorkGroupItem.outsource_work_group_id.asc(),
                Lot.lot_no.asc(),
                OutsourceWorkGroupItem.outsource_work_group_item_id.asc(),
            )
        )
        .all()
    )

    result = defaultdict(list)

    for row in group_item_rows:
        group_id = row[0].outsource_work_group_id
        if _is_bohyun_target_work_group(
            process_type_by_group_id[group_id],
            row[4].template_name,
        ):
            result[group_id].append(row)

    return dict(result)


def _is_bohyun_target_work_group_by_db(
    db: Session,
    work_group: OutsourceWorkGroup,
) -> bool:
    return bool(_get_bohyun_target_group_item_rows(db, work_group))


def _is_bohyun_target_work_group(
    process_type: str,
    template_name: str | None,
) -> bool:
    available_process_types = _get_available_process_types(template_name)
    is_print_product = "PRINT" in available_process_types

    if process_type == "CUT":
        return not is_print_product

    if process_type == "PRINT":
        return is_print_product

    if process_type == "DIECUT":
        return True

    return False
