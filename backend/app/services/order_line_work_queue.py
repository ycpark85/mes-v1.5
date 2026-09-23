"""One set of predicates for queue rows, counts, and server-side completion checks."""
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.partner import Partner
from app.models.product_inventory_movement import ProductInventoryMovement
from app.services.ship_qty_policy import ship_target_sql


def work_queue_expressions():
    latest_plan = select(OrderLinePlanHistory.plan_history_id).where(
        OrderLinePlanHistory.order_line_id == OrderLine.order_line_id,
    ).order_by(OrderLinePlanHistory.created_at.desc(), OrderLinePlanHistory.plan_history_id.desc()).limit(1).correlate(OrderLine).scalar_subquery()
    plan_target = select(case((OrderLinePlanHistory.plan_type == "STOCK_REPLENISHMENT", 0),
                              else_=OrderLinePlanHistory.ship_target_qty)).where(
        OrderLinePlanHistory.plan_history_id == latest_plan).correlate(OrderLine).scalar_subquery()
    partner_name = select(Partner.name).where(Partner.partner_id == OrderLine.partner_id).correlate(OrderLine).scalar_subquery()
    target = case((OrderLine.decision_made.is_(True), func.coalesce(plan_target, ship_target_sql(partner_name, OrderLine.order_qty))),
                  else_=ship_target_sql(partner_name, OrderLine.order_qty))
    shipped = select(func.coalesce(func.sum(-ProductInventoryMovement.qty), 0)).where(
        ProductInventoryMovement.order_line_id == OrderLine.order_line_id,
        ProductInventoryMovement.movement_type == "SHIP_OUT",
    ).correlate(OrderLine).scalar_subquery()
    has_lot = select(Lot.lot_id).where(Lot.order_line_id == OrderLine.order_line_id).correlate(OrderLine).exists()
    lot_wait = and_(OrderLine.is_active.is_(True), OrderLine.status == "OPEN",
                    OrderLine.lot_creation_deferred.is_(True), ~has_lot)

    final_result = select(InspectionResult.inspection_result_id).join(InspectionSchedule,
        InspectionSchedule.inspection_schedule_id == InspectionResult.inspection_schedule_id).where(
        InspectionSchedule.lot_id == Lot.lot_id, InspectionSchedule.status == "DONE",
        InspectionResult.is_partial.is_(False), InspectionResult.settled_at.is_not(None),
    ).correlate(Lot).exists()
    active_schedule = select(InspectionSchedule.inspection_schedule_id).where(
        InspectionSchedule.lot_id == Lot.lot_id,
        InspectionSchedule.status.not_in(("DONE", "PARTIAL_DONE", "CANCELED")),
    ).correlate(Lot).exists()
    active_lots = select(Lot.lot_id).where(Lot.order_line_id == OrderLine.order_line_id,
        Lot.status != "CANCELED").correlate(OrderLine)
    unfinished = active_lots.where((Lot.status != "DONE") | ~final_result | active_schedule).exists()
    close_wait = and_(OrderLine.is_active.is_(True), OrderLine.status == "CLOSED",
        OrderLine.short_close_state == "NONE", active_lots.exists(), ~unfinished, shipped < target)
    return lot_wait, close_wait


def is_close_decision_pending(db: Session, order_line_id: int) -> bool:
    _, pending = work_queue_expressions()
    return bool(db.execute(select(pending).where(OrderLine.order_line_id == order_line_id)).scalar_one())


def get_work_queue_counts(db: Session) -> dict[str, int]:
    lot_wait, close_wait = work_queue_expressions()
    row = db.execute(select(
        func.coalesce(func.sum(case((lot_wait, 1), else_=0)), 0),
        func.coalesce(func.sum(case((close_wait, 1), else_=0)), 0),
    ).select_from(OrderLine).where(OrderLine.is_active.is_(True), OrderLine.status.in_(("OPEN", "CLOSED")))).one()
    return {"lot_creation": int(row[0]), "close_decision": int(row[1])}
