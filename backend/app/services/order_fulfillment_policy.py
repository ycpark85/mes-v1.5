from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.partner import Partner
from app.models.product_inventory_movement import ProductInventoryMovement
from app.services.ship_qty_policy import calculate_ship_qty


def resolve_ship_target_qty(order_line: OrderLine, partner_name: str,
                            plan: OrderLinePlanHistory | None) -> int:
    if order_line.decision_made and plan is not None:
        return 0 if plan.plan_type == "STOCK_REPLENISHMENT" else int(plan.ship_target_qty)
    return calculate_ship_qty(partner_name, int(order_line.order_qty or 0))


def get_order_ship_target_qty(db: Session, order_line: OrderLine) -> int:
    plan = None
    if order_line.decision_made:
        plan = db.execute(select(OrderLinePlanHistory).where(
            OrderLinePlanHistory.order_line_id == order_line.order_line_id,
        ).order_by(OrderLinePlanHistory.created_at.desc(),
                   OrderLinePlanHistory.plan_history_id.desc()).limit(1)).scalar_one_or_none()
    partner = db.get(Partner, order_line.partner_id)
    return resolve_ship_target_qty(order_line, partner.name if partner else "", plan)


def sync_order_fulfillment_status(db: Session, order_line: OrderLine) -> None:
    if order_line.status == "CANCELED" or order_line.short_close_state in ("CONFIRMED", "REVIEW_REQUIRED"):
        return
    active = db.execute(select(Lot).where(
        Lot.order_line_id == order_line.order_line_id, Lot.status != "CANCELED",
    )).scalars().all()
    shipped = int(db.execute(select(func.coalesce(func.sum(-ProductInventoryMovement.qty), 0)).where(
        ProductInventoryMovement.order_line_id == order_line.order_line_id,
        ProductInventoryMovement.movement_type == "SHIP_OUT",
    )).scalar_one())
    done = all(lot.status == "DONE" for lot in active) and shipped >= get_order_ship_target_qty(db, order_line)
    if done:
        order_line.status = "DONE"
    elif order_line.status == "DONE":
        order_line.status = "CLOSED"
