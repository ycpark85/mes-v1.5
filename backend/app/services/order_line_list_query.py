from __future__ import annotations

from datetime import date
from typing import Optional, Tuple, List

from sqlalchemy import case, func, literal, or_, select, true
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
from app.services.order_fulfillment_policy import resolve_ship_target_qty
from app.services.order_line_work_queue import work_queue_expressions


def list_order_lines_for_grid(
    db: Session,
    *,
    page: int,
    size: int,
    q: Optional[str] = None,
    status: Optional[str] = None,
    status_group: Optional[str] = None,
    work_queue: Optional[str] = None,
    is_active: Optional[bool] = True,
    partner_id: Optional[int] = None,
    product_id: Optional[int] = None,
    order_date_from: Optional[date] = None,
    order_date_to: Optional[date] = None,
    due_date_from: Optional[date] = None,
    due_date_to: Optional[date] = None,
) -> Tuple[List[dict], int, Optional[dict[str, int]]]:
    normalized_group = (status_group or "").strip().upper()
    completed_only = normalized_group == "COMPLETED" or (not status_group and status in ("DONE", "CANCELED"))
    queue_rows = None
    if completed_only:
        lot_wait, close_wait = literal(False), literal(False)
    else:
        lot_wait, close_wait = work_queue_expressions()
        # Reuse one evaluation for global badges, filtered totals, and page rows.
        # This is statement-local, so a later read or write always checks fresh data.
        queue_rows = (
            select(OrderLine.order_line_id, lot_wait.label("lot_wait"), close_wait.label("close_wait"))
            .where(OrderLine.is_active.is_(True), OrderLine.status.in_(("OPEN", "CLOSED")))
            .cte("order_work_queues")
            .prefix_with("MATERIALIZED", dialect="postgresql")
        )
        lot_wait = func.coalesce(queue_rows.c.lot_wait, False)
        close_wait = func.coalesce(queue_rows.c.close_wait, False)

    filtered = (
        select(OrderLine.order_line_id, OrderLine.due_date, OrderLine.order_no, OrderLine.line_no,
               lot_wait.label("lot_wait"), close_wait.label("close_wait"))
        .join(Partner, Partner.partner_id == OrderLine.partner_id)
        .join(Product, Product.product_id == OrderLine.product_id)
        .outerjoin(Drawing, Drawing.drawing_id == Product.drawing_id)
    )
    if queue_rows is not None:
        filtered = filtered.outerjoin(queue_rows, queue_rows.c.order_line_id == OrderLine.order_line_id)
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

    conds = []

    if is_active is not None:
        conds.append(OrderLine.is_active == is_active)

    if status_group:
        if normalized_group == "IN_PROGRESS":
            conds.append(OrderLine.status.in_(["OPEN", "CLOSED"]))
        elif normalized_group == "COMPLETED":
            conds.append(OrderLine.status.in_(["DONE", "CANCELED"]))
    elif status:
        conds.append(OrderLine.status == status)

    if work_queue == "LOT_CREATION":
        conds.append(lot_wait)
    elif work_queue == "CLOSE_DECISION":
        conds.append(close_wait)

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
        filtered = filtered.where(*conds)
    filtered = filtered.cte("filtered_orders")
    total_query = select(func.count()).select_from(filtered).scalar_subquery()
    if queue_rows is None:
        summary = select(total_query.label("total"), literal(None).label("lot_creation_count"),
                         literal(None).label("close_decision_count")).cte("order_summary")
    else:
        summary = select(
            total_query.label("total"),
            func.coalesce(func.sum(case((queue_rows.c.lot_wait, 1), else_=0)), 0).label("lot_creation_count"),
            func.coalesce(func.sum(case((queue_rows.c.close_wait, 1), else_=0)), 0).label("close_decision_count"),
        ).select_from(queue_rows).cte("order_summary")
    page_rows = (
        select(filtered).order_by(filtered.c.due_date, filtered.c.order_no, filtered.c.line_no)
        .offset((page - 1) * size).limit(size).cte("order_page")
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
            page_rows.c.lot_wait, page_rows.c.close_wait,
            summary.c.total, summary.c.lot_creation_count, summary.c.close_decision_count,
        )
        .select_from(summary)
        # Keep the summary even when the search or requested page is empty.
        .outerjoin(page_rows, true())
        .outerjoin(OrderLine, OrderLine.order_line_id == page_rows.c.order_line_id)
        .outerjoin(Partner, Partner.partner_id == OrderLine.partner_id)
        .outerjoin(Product, Product.product_id == OrderLine.product_id)
        .outerjoin(Drawing, Drawing.drawing_id == Product.drawing_id)
        .outerjoin(ProductInventory, ProductInventory.product_id == OrderLine.product_id)
        .outerjoin(reserved_inventory_sq, reserved_inventory_sq.c.product_id == Product.product_id)
        .outerjoin(lot_agg_sq, lot_agg_sq.c.order_line_id == OrderLine.order_line_id)
        .order_by(page_rows.c.due_date, page_rows.c.order_no, page_rows.c.line_no)
    )
    result = db.execute(stmt).all()
    total = int(result[0].total)
    queue_counts = None if completed_only else {
        "lot_creation": int(result[0].lot_creation_count),
        "close_decision": int(result[0].close_decision_count),
    }
    rows = [row[:-3] for row in result if row[0] is not None]
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
        is_lot_wait,
        is_close_wait,
    ) in rows:
        lot_count_int = int(lot_count or 0)
        available_inventory_qty = max(int(current_qty or 0) - int(reserved_qty or 0), 0)
        order_qty = int(ol.order_qty or 0)
        latest_plan_history = latest_plan_history_map.get(ol.order_line_id)
        plan_type = latest_plan_history.plan_type if latest_plan_history else None

        target_ship_qty = resolve_ship_target_qty(ol, partner_name or "", latest_plan_history)

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
        if ol.decision_made and latest_plan_history is not None:
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

        needs_shortage_action = bool(is_close_wait)

        shortage_closed = ol.status == "DONE" and ol.short_close_state == "CONFIRMED"
        expected_short_qty = max(target_ship_qty - expected_ship_qty, 0)
        decision_required = (
            not bool(ol.decision_made)
            and ol.status == "OPEN"
            and lot_count_int == 0
            and (bool(plan_policy.allowed_plan_types) or ol.lot_creation_deferred)
        )
        allowed_plan_types = (
            [plan_type.value for plan_type in plan_policy.allowed_plan_types]
            if decision_required
            else []
        )
        if decision_required and not allowed_plan_types and ol.lot_creation_deferred:
            allowed_plan_types = ["AUTO_PRODUCTION"]

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
                "planned_stock_ship_qty": int(latest_plan_history.stock_ship_qty or 0) if ol.decision_made and latest_plan_history else 0,
                "decision_required": decision_required,
                "allowed_plan_types": allowed_plan_types,
                "expected_ship_qty": expected_ship_qty,
                "expected_short_qty": expected_short_qty,
                "ship_target_qty": ship_target_qty,
                "already_shipped_qty": already_shipped_qty,
                "remaining_ship_qty": remaining_ship_qty,
                "needs_shortage_action": needs_shortage_action,
                "shortage_closed": shortage_closed,
                "short_close_state": ol.short_close_state,
                "lot_creation_deferred": ol.lot_creation_deferred,
                "manual_closed": ol.manual_closed,
                "work_queue": "LOT_CREATION" if is_lot_wait else "CLOSE_DECISION" if is_close_wait else None,
            }
        )

    return items, total, queue_counts
