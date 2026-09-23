from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import korea_today
from app.crud.lot import lot_crud
from app.models.lot import Lot
from app.models.lot_step import LotStep
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.process import Process
from app.models.product import Product
from app.models.routing_template_step import RoutingTemplateStep
from app.schemas.lot import LotCreate, LotDetailOut
from app.services.production_daily_query import refresh_order_line_snapshot
from app.services.order_line_manual_close_service import reopen_order_for_rework


def create_rework_lot(
    db: Session,
    payload: LotCreate,
    *,
    actor: str = "system",
) -> LotDetailOut:
    order_line = _ensure_order_line(db, payload.order_line_id)
    product = _ensure_active_product(db, order_line.product_id)

    created_date = payload.created_date or korea_today()
    parent_lot_id = payload.parent_lot_id or None
    lot_qty = int(payload.lot_qty)

    if parent_lot_id is None:
        raise HTTPException(
            status_code=409,
            detail="Manual LOT creation is allowed for rework LOT only",
        )

    material_lot_no, material_used_qty, material_sheet_count = _validate_material_fields(payload)
    parent = _ensure_parent_lot(db, parent_lot_id)
    _validate_rework_parent(order_line, parent)

    lot = _create_lot_with_retry(
        db,
        order_line=order_line,
        product=product,
        parent_lot_id=parent.lot_id,
        lot_qty=lot_qty,
        created_date=created_date,
        material_lot_no=material_lot_no,
        material_used_qty=material_used_qty,
        material_sheet_count=material_sheet_count,
        memo=payload.memo,
    )

    reopen_order_for_rework(db, order_line, lot_id=lot.lot_id, actor=actor)
    refresh_order_line_snapshot(db, order_line.order_line_id)
    db.flush()

    return _build_lot_detail_out(db, lot, order_line, product)


def _create_lot_with_retry(
    db: Session,
    *,
    order_line: OrderLine,
    product: Product,
    parent_lot_id: int,
    lot_qty: int,
    created_date: date,
    material_lot_no,
    material_used_qty,
    material_sheet_count,
    memo: str | None,
) -> Lot:
    for _ in range(3):
        lot_no = _generate_lot_no(db, created_date, e_fixed="E")
        lot = Lot(
            lot_no=lot_no,
            order_line_id=order_line.order_line_id,
            product_id=order_line.product_id,
            parent_lot_id=parent_lot_id,
            lot_qty=lot_qty,
            uom=order_line.uom,
            material_lot_no=material_lot_no,
            material_used_qty=material_used_qty,
            material_sheet_count=material_sheet_count,
            created_date=created_date,
            due_date=order_line.due_date,
            memo=memo,
            status="WAITING",
        )

        try:
            with db.begin_nested():
                lot_crud.create(db, lot)
                _create_lot_steps_from_routing(db, lot.lot_id, product.routing_template_id)
                db.flush()
            return lot
        except IntegrityError:
            continue

    raise HTTPException(status_code=409, detail="Failed to generate unique lot_no (retry exceeded)")


def _build_lot_detail_out(
    db: Session,
    lot: Lot,
    order_line: OrderLine,
    product: Product,
) -> LotDetailOut:
    out = LotDetailOut.model_validate(lot, from_attributes=True)
    partner = db.get(Partner, order_line.partner_id)
    out.order_no = order_line.order_no
    out.line_no = order_line.line_no
    out.partner_id = order_line.partner_id
    out.partner_name = partner.name if partner else None
    out.product_code = product.product_code
    out.product_name = product.product_name
    out.steps = [s for s in lot.steps]
    return out


def _get_lot_month_code(value: date) -> str:
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


def _generate_lot_no(db: Session, created_date: date, e_fixed: str = "E") -> str:
    yy = f"{created_date.year % 100:02d}"
    dd = f"{created_date.day:02d}"
    month_code = _get_lot_month_code(created_date)
    fixed_code = (e_fixed or "E").strip().upper()
    prefix = f"CT{yy}{month_code}{dd}{fixed_code}"
    legacy_prefix = f"CT{yy}{created_date.month:02d}{dd}0"

    existing_lot_nos = db.execute(
        select(Lot.lot_no)
        .where(or_(Lot.lot_no.like(f"{prefix}%"), Lot.lot_no.like(f"{legacy_prefix}%")))
        .order_by(desc(Lot.lot_no))
    ).scalars().all()

    max_seq = 0
    for lot_no in existing_lot_nos:
        try:
            max_seq = max(max_seq, int(lot_no[-2:]))
        except ValueError:
            continue

    next_seq = max_seq + 1

    if next_seq > 99:
        raise HTTPException(status_code=409, detail="LOT sequence exceeded for the day (NN > 99)")

    return f"{prefix}{next_seq:02d}"


def _ensure_order_line(db: Session, order_line_id: int) -> OrderLine:
    order_line = db.execute(select(OrderLine).where(OrderLine.order_line_id == order_line_id)
        .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if not order_line or not order_line.is_active:
        raise HTTPException(status_code=404, detail="OrderLine not found or inactive")
    if order_line.status == "CANCELED":
        raise HTTPException(status_code=409, detail="취소된 발주에는 재작업 LOT를 생성할 수 없습니다.")
    return order_line


def _ensure_active_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise HTTPException(status_code=409, detail="Product not found or inactive")
    return product


def _ensure_parent_lot(db: Session, parent_lot_id: int) -> Lot:
    parent = db.get(Lot, parent_lot_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent LOT not found")
    return parent


def _validate_rework_parent(order_line: OrderLine, parent: Lot) -> None:
    if parent.order_line_id != order_line.order_line_id:
        raise HTTPException(status_code=409, detail="Parent LOT must belong to same OrderLine")

    if parent.parent_lot_id is not None:
        raise HTTPException(status_code=409, detail="Parent LOT must be a primary LOT")

    if parent.status not in ("DONE", "CANCELED"):
        raise HTTPException(
            status_code=409,
            detail="Rework LOT can only be created when parent LOT is DONE or CANCELED",
        )


def _create_lot_steps_from_routing(db: Session, lot_id: int, routing_template_id: int) -> None:
    steps = db.execute(
        select(RoutingTemplateStep)
        .where(
            RoutingTemplateStep.routing_template_id == routing_template_id,
            RoutingTemplateStep.is_active == True,  # noqa: E712
        )
        .order_by(RoutingTemplateStep.step_seq.asc())
    ).scalars().all()

    if not steps:
        raise HTTPException(status_code=409, detail="RoutingTemplate has no active steps")

    process_ids = [step.process_id for step in steps]
    processes = db.execute(select(Process).where(Process.process_id.in_(process_ids))).scalars().all()
    process_map = {process.process_id: process for process in processes}

    for step in steps:
        process = process_map.get(step.process_id)
        if not process:
            raise HTTPException(status_code=409, detail=f"Process not found for process_id={step.process_id}")

        db.add(
            LotStep(
                lot_id=lot_id,
                step_seq=step.step_seq,
                process_id=step.process_id,
                process_code=process.process_code,
                process_name=process.process_name,
                process_type=step.default_process_type,
                status="WAITING",
            )
        )


def _normalize_optional_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _validate_material_fields(payload: LotCreate):
    material_lot_no = _normalize_optional_str(payload.material_lot_no)
    material_used_qty = payload.material_used_qty
    material_sheet_count = payload.material_sheet_count

    has_lot_no = material_lot_no is not None
    has_used_qty = material_used_qty is not None
    has_sheet_count = material_sheet_count is not None

    if has_lot_no and not has_used_qty:
        raise HTTPException(status_code=409, detail="material_used_qty is required when material_lot_no is provided")

    if has_used_qty and not has_lot_no:
        raise HTTPException(status_code=409, detail="material_lot_no is required when material_used_qty is provided")

    if has_sheet_count and not has_lot_no:
        raise HTTPException(status_code=409, detail="material_lot_no is required when material_sheet_count is provided")

    return material_lot_no, material_used_qty, material_sheet_count
