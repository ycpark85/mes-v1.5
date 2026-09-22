from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.inventory_fifo_service import release_order_stock_reservations
from app.models.order_line import OrderLine
from app.models.product_inventory_movement import ProductInventoryMovement
from app.schemas.order_line import OrderLineShortCloseRequest, OrderLineStatus
from app.services.order_fulfillment_policy import get_order_ship_target_qty
from app.services.order_line_change_history_service import ORDER_LINE_SHORT_CLOSE, record_order_line_change


def get_remaining_ship_qty(db: Session, order_line: OrderLine) -> int:
    ship_target_qty = get_order_ship_target_qty(db, order_line)
    already_shipped_qty = int(
        db.execute(
            select(func.coalesce(func.sum(-ProductInventoryMovement.qty), 0)).where(
                ProductInventoryMovement.order_line_id == order_line.order_line_id,
                ProductInventoryMovement.movement_type == "SHIP_OUT",
            )
        ).scalar_one()
        or 0
    )

    return max(ship_target_qty - already_shipped_qty, 0)


def short_close_order_line_status(
    db: Session,
    order_line_id: int,
    payload: OrderLineShortCloseRequest,
    *,
    actor: str,
) -> OrderLine:
    order_line = db.execute(select(OrderLine).where(OrderLine.order_line_id == order_line_id)
        .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if not order_line or not order_line.is_active:
        raise HTTPException(status_code=404, detail="OrderLine not found")

    if order_line.status != OrderLineStatus.CLOSED.value:
        raise HTTPException(status_code=409, detail="부족종료는 CLOSED 상태 수주에서만 가능합니다.")

    remaining_ship_qty = get_remaining_ship_qty(db, order_line)
    if remaining_ship_qty <= 0:
        raise HTTPException(status_code=409, detail="부족수량이 없어 부족종료 대상이 아닙니다.")

    record_order_line_change(
        db, order_line_id=order_line_id, change_type=ORDER_LINE_SHORT_CLOSE,
        before_data={"status": order_line.status, "short_close_state": order_line.short_close_state},
        after_data={"status": "DONE", "short_close_state": "CONFIRMED", "remaining_ship_qty": remaining_ship_qty},
        actor=actor, reason=payload.memo,
    )
    release_order_stock_reservations(db, order_line)
    order_line.status = OrderLineStatus.DONE.value
    order_line.short_close_state = "CONFIRMED"

    db.flush()
    return order_line
