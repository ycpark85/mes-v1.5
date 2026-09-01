from __future__ import annotations

from datetime import date
from typing import Optional, Tuple, List

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.drawing import Drawing
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.shipment_line import ShipmentLine
from app.services.order_line_display import to_plan_type_display
from app.services.order_line_plan_policy import evaluate_order_line_plan_policy
from app.services.ship_qty_policy import calculate_ship_qty


def list_order_lines_for_grid(
    db: Session,
    *,
    page: int,
    size: int,
    q: Optional[str] = None,
    status: Optional[str] = None,
    status_group: Optional[str] = None,
    is_active: Optional[bool] = True,
    partner_id: Optional[int] = None,
    product_id: Optional[int] = None,
    order_date_from: Optional[date] = None,
    order_date_to: Optional[date] = None,
    due_date_from: Optional[date] = None,
    due_date_to: Optional[date] = None,
) -> Tuple[List[dict], int]:
    lot_agg_sq = (
        select(
            Lot.order_line_id.label("order_line_id"),
            func.count(Lot.lot_id).label("lot_count"),
        )
        .group_by(Lot.order_line_id)
        .subquery()
    )

    reserved_inventory_sq = (
        select(
            ShipmentLine.product_id.label("product_id"),
            func.coalesce(func.sum(ShipmentLine.ship_qty), 0).label("reserved_qty"),
        )
        .where(
            ShipmentLine.source_type == "STOCK",
            ShipmentLine.status == "WAITING",
        )
        .group_by(ShipmentLine.product_id)
        .subquery()
    )

    stmt = (
        select(
            OrderLine,
            Partner.name.label("partner_name"),
            Product.product_code.label("product_code"),
            Product.product_name.label("product_name"),
            Drawing.drawing_no.label("drawing_no"),
            func.coalesce(ProductInventory.current_qty, 0).label("current_qty"),
            func.coalesce(reserved_inventory_sq.c.reserved_qty, 0).label("reserved_qty"),
            func.coalesce(lot_agg_sq.c.lot_count, 0).label("lot_count"),
        )
        .join(Partner, Partner.partner_id == OrderLine.partner_id)
        .join(Product, Product.product_id == OrderLine.product_id)
        .outerjoin(Drawing, Drawing.drawing_id == Product.drawing_id)
        .outerjoin(ProductInventory, ProductInventory.product_id == OrderLine.product_id)
        .outerjoin(reserved_inventory_sq, reserved_inventory_sq.c.product_id == Product.product_id)
        .outerjoin(lot_agg_sq, lot_agg_sq.c.order_line_id == OrderLine.order_line_id)
    )

    conds = []

    if is_active is not None:
        conds.append(OrderLine.is_active == is_active)

    if status_group:
        normalized_group = status_group.strip().upper()

        if normalized_group == "IN_PROGRESS":
            conds.append(OrderLine.status.in_(["OPEN", "CLOSED"]))
        elif normalized_group == "COMPLETED":
            conds.append(OrderLine.status.in_(["DONE", "CANCELED"]))
    elif status:
        conds.append(OrderLine.status == status)

    if partner_id:
        conds.append(OrderLine.partner_id == partner_id)

    if product_id:
        conds.append(OrderLine.product_id == product_id)

    if order_date_from:
        conds.append(OrderLine.order_date >= order_date_from)

    if order_date_to:
        conds.append(OrderLine.order_date <= order_date_to)

    if due_date_from:
        conds.append(OrderLine.due_date >= due_date_from)

    if due_date_to:
        conds.append(OrderLine.due_date <= due_date_to)

    if q and q.strip():
        normalized_q = q.strip()
        normalized_number = normalized_q.upper()
        like = f"%{normalized_q}%"
        conds.append(
            or_(
                OrderLine.order_no == normalized_number,
                func.upper(OrderLine.customer_po) == normalized_number,
                OrderLine.memo.ilike(like),
                Partner.name.ilike(like),
                Product.product_name.ilike(like),
                Product.product_code.ilike(like),
                Drawing.drawing_no.ilike(like),
            )
        )

    if conds:
        stmt = stmt.where(*conds)

    count_stmt = (
        select(func.count())
        .select_from(OrderLine)
        .join(Partner, Partner.partner_id == OrderLine.partner_id)
        .join(Product, Product.product_id == OrderLine.product_id)
        .outerjoin(Drawing, Drawing.drawing_id == Product.drawing_id)
    )

    if conds:
        count_stmt = count_stmt.where(*conds)

    total = db.execute(count_stmt).scalar_one()

    stmt = stmt.order_by(
        OrderLine.due_date.asc(),
        OrderLine.order_no.asc(),
        OrderLine.line_no.asc(),
    )

    stmt = stmt.offset((page - 1) * size).limit(size)

    rows = db.execute(stmt).all()
    order_line_ids = [row[0].order_line_id for row in rows]

    latest_plan_history_map: dict[int, OrderLinePlanHistory] = {}
    already_shipped_qty_map: dict[int, int] = {}
    if order_line_ids:
        histories = (
            db.execute(
                select(OrderLinePlanHistory)
                .where(OrderLinePlanHistory.order_line_id.in_(order_line_ids))
                .order_by(
                    OrderLinePlanHistory.order_line_id.asc(),
                    OrderLinePlanHistory.created_at.desc(),
                    OrderLinePlanHistory.plan_history_id.desc(),
                )
            )
            .scalars()
            .all()
        )

        for history in histories:
            latest_plan_history_map.setdefault(history.order_line_id, history)

        shipped_rows = (
            db.execute(
                select(
                    ProductInventoryMovement.order_line_id,
                    func.coalesce(func.sum(-ProductInventoryMovement.qty), 0).label("already_shipped_qty"),
                )
                .where(
                    ProductInventoryMovement.order_line_id.in_(order_line_ids),
                    ProductInventoryMovement.movement_type == "SHIP_OUT",
                )
                .group_by(ProductInventoryMovement.order_line_id)
            )
            .all()
        )

        already_shipped_qty_map = {
            int(order_line_id): int(already_shipped_qty or 0)
            for order_line_id, already_shipped_qty in shipped_rows
            if order_line_id is not None
        }

    items: List[dict] = []

    for (
        ol,
        partner_name,
        product_code,
        product_name,
        drawing_no,
        current_qty,
        reserved_qty,
        lot_count,
    ) in rows:
        lot_count_int = int(lot_count or 0)
        available_inventory_qty = max(int(current_qty or 0) - int(reserved_qty or 0), 0)
        order_qty = int(ol.order_qty or 0)
        latest_plan_history = latest_plan_history_map.get(ol.order_line_id)
        plan_type = latest_plan_history.plan_type if latest_plan_history else None

        target_ship_qty = int(calculate_ship_qty(partner_name or "", order_qty) or 0)

        plan_policy = evaluate_order_line_plan_policy(
            available_inventory_qty=available_inventory_qty,
            target_ship_qty=target_ship_qty,
        )
        recommended_mode = plan_policy.recommended_fulfillment_mode

        saved_mode = ol.fulfillment_mode or recommended_mode
        saved_policy = ol.production_policy or "ORDER_ONLY"
        extra_production_qty = int(ol.extra_production_qty or 0)

        if saved_policy == "INVENTORY_ONLY_CLOSE":
            saved_mode = "INVENTORY_FIRST"
            extra_production_qty = 0
            base_planned_production_qty = 0
        elif saved_mode == "PRODUCTION_FIRST":
            base_planned_production_qty = target_ship_qty
        else:
            base_planned_production_qty = max(target_ship_qty - available_inventory_qty, 0)

        if saved_policy != "ALLOW_STOCK_BUILD":
            extra_production_qty = 0

        recommended_production_qty = plan_policy.recommended_production_qty

        planned_production_qty = base_planned_production_qty + extra_production_qty
        if plan_type == "STOCK_REPLENISHMENT" and latest_plan_history is not None:
            planned_production_qty = int(latest_plan_history.production_qty or 0)

        if saved_policy == "INVENTORY_ONLY_CLOSE":
            expected_ship_qty = min(available_inventory_qty, target_ship_qty)
        else:
            expected_ship_qty = min(
                available_inventory_qty + planned_production_qty,
                target_ship_qty,
            )

        ship_target_qty = target_ship_qty
        already_shipped_qty = already_shipped_qty_map.get(ol.order_line_id, 0)

        remaining_ship_qty = max(ship_target_qty - already_shipped_qty, 0)

        needs_shortage_action = (
            ol.status == "CLOSED"
            and remaining_ship_qty > 0
            and (ol.production_policy or "") != "INVENTORY_ONLY_CLOSE"
            and lot_count_int > 0
        )

        shortage_closed = ol.status == "DONE" and remaining_ship_qty > 0
        expected_short_qty = max(target_ship_qty - expected_ship_qty, 0)
        decision_required = (
            not bool(ol.decision_made)
            and ol.status == "OPEN"
            and lot_count_int == 0
            and bool(plan_policy.allowed_plan_types)
        )
        allowed_plan_types = (
            [plan_type.value for plan_type in plan_policy.allowed_plan_types]
            if decision_required
            else []
        )

        items.append(
            {
                "order_line_id": ol.order_line_id,
                "order_no": ol.order_no,
                "line_no": ol.line_no,
                "partner_id": ol.partner_id,
                "product_id": ol.product_id,
                "order_date": ol.order_date,
                "due_date": ol.due_date,
                "order_qty": ol.order_qty,
                "uom": ol.uom,
                "customer_po": ol.customer_po,
                "memo": ol.memo,
                "status": ol.status,
                "is_active": ol.is_active,
                "priority": ol.priority,
                "created_at": ol.created_at,
                "updated_at": ol.updated_at,
                "partner_name": partner_name,
                "product_code": product_code,
                "product_name": product_name,
                "drawing_no": drawing_no,
                "has_lot": lot_count_int > 0,
                "lot_count": lot_count_int,
                "fulfillment_mode": saved_mode,
                "production_policy": saved_policy,
                "extra_production_qty": extra_production_qty,
                "decision_made": bool(ol.decision_made),
                "decision_made_at": ol.decision_made_at,
                "decision_made_by": ol.decision_made_by,
                "plan_type": plan_type,
                "plan_type_display": to_plan_type_display(plan_type),
                "available_inventory_qty": available_inventory_qty,
                "target_ship_qty": target_ship_qty,
                "recommended_fulfillment_mode": recommended_mode,
                "recommended_production_qty": recommended_production_qty,
                "planned_production_qty": planned_production_qty,
                "decision_required": decision_required,
                "allowed_plan_types": allowed_plan_types,
                "expected_ship_qty": expected_ship_qty,
                "expected_short_qty": expected_short_qty,
                "ship_target_qty": ship_target_qty,
                "already_shipped_qty": already_shipped_qty,
                "remaining_ship_qty": remaining_ship_qty,
                "needs_shortage_action": needs_shortage_action,
                "shortage_closed": shortage_closed,
            }
        )

    return items, total
