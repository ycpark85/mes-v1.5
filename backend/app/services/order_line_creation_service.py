from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import korea_today, utc_now
from app.crud.lot import lot_crud
from app.crud.order_line import order_line_crud
from app.models.lot import Lot
from app.models.lot_step import LotStep
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.process import Process
from app.models.product import Product
from app.models.routing_template_step import RoutingTemplateStep
from app.schemas.order_line import (
    OrderLineCreate,
    OrderLineFulfillmentMode,
    OrderLinePlanType,
    OrderLineProductionPolicy,
    OrderLineStatus,
)
from app.services.order_line_plan_service import (
    create_plan_history,
    get_available_inventory_qty,
)
from app.services.order_line_plan_policy import evaluate_order_line_plan_policy
from app.services.production_daily_query import refresh_order_line_snapshot
from app.services.ship_qty_policy import calculate_ship_qty, is_stock_replenishment_partner


def ensure_partner_active(db: Session, partner_id: int) -> Partner:
    partner = db.get(Partner, partner_id)
    if not partner or not partner.is_active:
        raise HTTPException(status_code=404, detail="Partner not found or inactive")
    return partner


def ensure_product_active(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found or inactive")
    return product


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

    existing_lot_nos = (
        db.execute(
            select(Lot.lot_no)
            .where(or_(Lot.lot_no.like(f"{prefix}%"), Lot.lot_no.like(f"{legacy_prefix}%")))
            .order_by(desc(Lot.lot_no))
        )
        .scalars()
        .all()
    )

    max_seq = 0
    for lot_no in existing_lot_nos:
        try:
            max_seq = max(max_seq, int(lot_no[-2:]))
        except ValueError:
            continue

    nn = max_seq + 1

    if nn > 99:
        raise HTTPException(status_code=409, detail="LOT sequence exceeded for the day (NN > 99)")

    return f"{prefix}{nn:02d}"


def _create_lot_steps_from_routing(db: Session, lot_id: int, routing_template_id: int) -> None:
    steps = (
        db.execute(
            select(RoutingTemplateStep)
            .where(
                RoutingTemplateStep.routing_template_id == routing_template_id,
                RoutingTemplateStep.is_active == True,  # noqa: E712
            )
            .order_by(RoutingTemplateStep.step_seq.asc())
        )
        .scalars()
        .all()
    )

    if not steps:
        raise HTTPException(status_code=409, detail="RoutingTemplate has no active steps")

    process_ids = [s.process_id for s in steps]
    procs = db.execute(select(Process).where(Process.process_id.in_(process_ids))).scalars().all()
    process_map = {p.process_id: p for p in procs}

    for s in steps:
        p = process_map.get(s.process_id)
        if not p:
            raise HTTPException(status_code=409, detail=f"Process not found for process_id={s.process_id}")

        db.add(
            LotStep(
                lot_id=lot_id,
                step_seq=s.step_seq,
                process_id=s.process_id,
                process_code=p.process_code,
                process_name=p.process_name,
                process_type=s.default_process_type,
                status="WAITING",
            )
        )


def create_primary_lot_for_order_line(
    db: Session,
    order_line: OrderLine,
    product: Product,
    *,
    lot_qty: int | None = None,
) -> Lot:
    if order_line.status != OrderLineStatus.OPEN.value:
        raise HTTPException(
            status_code=409,
            detail="Primary LOT can only be auto-created when OrderLine is OPEN",
        )

    if not product.routing_template_id:
        raise HTTPException(status_code=409, detail="Product has no routing template")

    create_lot_qty = int(lot_qty if lot_qty is not None else order_line.order_qty)

    if create_lot_qty <= 0:
        raise HTTPException(status_code=409, detail="LOT quantity must be greater than zero")

    created_date = korea_today()

    for _ in range(3):
        lot_no = _generate_lot_no(db, created_date, e_fixed="E")

        lot = Lot(
            lot_no=lot_no,
            order_line_id=order_line.order_line_id,
            product_id=order_line.product_id,
            parent_lot_id=None,
            lot_qty=create_lot_qty,
            uom=order_line.uom,
            material_lot_no=None,
            material_used_qty=None,
            material_sheet_count=None,
            created_date=created_date,
            due_date=order_line.due_date,
            memo=None,
            status="WAITING",
        )

        try:
            with db.begin_nested():
                lot_crud.create(db, lot)
                _create_lot_steps_from_routing(db, lot.lot_id, product.routing_template_id)

                order_line.status = OrderLineStatus.CLOSED.value

                db.flush()
                db.refresh(lot)
                refresh_order_line_snapshot(db, order_line.order_line_id)

                return lot

        except IntegrityError:
            continue

    raise HTTPException(status_code=409, detail="Failed to generate unique lot_no (retry exceeded)")


def create_order_line_with_policy(db: Session, payload: OrderLineCreate) -> OrderLine:
    partner = ensure_partner_active(db, payload.partner_id)
    product = ensure_product_active(db, payload.product_id)

    data = payload.model_dump()
    data["uom"] = product.uom

    obj = OrderLine(**data)

    order_line_crud.create(db, obj)
    db.flush()

    actor = "system"

    available_inventory_qty = get_available_inventory_qty(
        db,
        obj.product_id,
    )

    is_stock_replenishment = is_stock_replenishment_partner(
        partner.name,
        partner.business_no,
    )

    if is_stock_replenishment:
        production_qty = int(obj.order_qty or 0)

        create_plan_history(
            db,
            order_line=obj,
            plan_type=OrderLinePlanType.STOCK_REPLENISHMENT,
            ship_target_qty=0,
            available_inventory_qty=available_inventory_qty,
            stock_ship_qty=0,
            production_qty=production_qty,
            is_short_close=False,
            memo="발주 등록 자동 처리: 재고비축 생산",
            actor=actor,
        )

        obj.fulfillment_mode = OrderLineFulfillmentMode.PRODUCTION_FIRST.value
        obj.production_policy = OrderLineProductionPolicy.ALLOW_STOCK_BUILD.value
        obj.extra_production_qty = 0
        obj.decision_made = True
        obj.decision_made_at = utc_now()
        obj.decision_made_by = actor

        create_primary_lot_for_order_line(
            db,
            obj,
            product,
            lot_qty=production_qty,
        )

        db.flush()
        return obj

    ship_target_qty = calculate_ship_qty(
        partner.name,
        int(obj.order_qty or 0),
    )

    if ship_target_qty <= 0:
        obj.decision_made = False
        obj.decision_made_at = None
        obj.decision_made_by = None
        db.flush()
        return obj

    if available_inventory_qty <= 0:
        production_qty = ship_target_qty

        create_plan_history(
            db,
            order_line=obj,
            plan_type=OrderLinePlanType.AUTO_PRODUCTION,
            ship_target_qty=ship_target_qty,
            available_inventory_qty=available_inventory_qty,
            stock_ship_qty=0,
            production_qty=production_qty,
            is_short_close=False,
            memo="발주 등록 자동 처리: 현재고 없음, 생산 진행",
            actor=actor,
        )

        obj.fulfillment_mode = OrderLineFulfillmentMode.PRODUCTION_FIRST.value
        obj.production_policy = OrderLineProductionPolicy.ORDER_ONLY.value
        obj.extra_production_qty = 0
        obj.decision_made = True
        obj.decision_made_at = utc_now()
        obj.decision_made_by = actor

        create_primary_lot_for_order_line(
            db,
            obj,
            product,
            lot_qty=production_qty,
        )

        db.flush()
        return obj

    policy = evaluate_order_line_plan_policy(
        available_inventory_qty=available_inventory_qty,
        target_ship_qty=ship_target_qty,
    )

    obj.fulfillment_mode = policy.recommended_fulfillment_mode
    obj.lot_creation_deferred = True
    obj.production_policy = OrderLineProductionPolicy.ORDER_ONLY.value
    obj.extra_production_qty = 0
    obj.decision_made = False
    obj.decision_made_at = None
    obj.decision_made_by = None

    db.flush()
    return obj
