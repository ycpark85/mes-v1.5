from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import KOREA_TIME_ZONE, UTC, utc_now
from app.models.order_line import OrderLine
from app.schemas.order_line import OrderLineShortCloseRequest
from app.services.inventory_fifo_service import release_order_stock_reservations
from app.services.order_fulfillment_policy import get_order_ship_target_qty, sync_order_fulfillment_status
from app.services.order_line_plan_service import get_already_shipped_qty
from app.services.order_line_change_history_service import ORDER_LINE_SHORT_CLOSE, record_order_line_change
from app.services.order_line_work_queue import is_close_decision_pending


def _lock_order(db: Session, order_line_id: int) -> OrderLine:
    order = db.execute(select(OrderLine).where(OrderLine.order_line_id == order_line_id)
        .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if order is None or not order.is_active:
        raise HTTPException(status_code=404, detail="OrderLine not found")
    return order


def _check_snapshot(order: OrderLine, payload: OrderLineShortCloseRequest, target: int, shipped: int) -> None:
    if payload.expected_updated_at is not None:
        def normalize(value: datetime) -> datetime:
            return (value.replace(tzinfo=KOREA_TIME_ZONE) if value.tzinfo is None else value).astimezone(UTC)
        if normalize(order.updated_at) != normalize(payload.expected_updated_at):
            raise HTTPException(status_code=409, detail="발주가 변경되었습니다. 목록을 다시 조회한 후 처리하세요.")
    if ((payload.expected_ship_target_qty is not None and payload.expected_ship_target_qty != target)
            or (payload.expected_shipped_qty is not None and payload.expected_shipped_qty != shipped)):
        raise HTTPException(status_code=409, detail="출고 현황이 변경되었습니다. 목록을 다시 조회한 후 처리하세요.")


def _snapshot(order: OrderLine) -> dict:
    return {"status": order.status, "short_close_state": order.short_close_state,
            "manual_closed": bool(order.manual_closed)}


def manual_close_order_line(
    db: Session, order_line_id: int, payload: OrderLineShortCloseRequest, *, actor: str,
) -> OrderLine:
    order = _lock_order(db, order_line_id)
    if order.manual_closed and order.status == "DONE":
        return order  # A duplicate submission cannot create another audit or inventory action.
    target = get_order_ship_target_qty(db, order)
    shipped = get_already_shipped_qty(db, order_line_id)
    _check_snapshot(order, payload, target, shipped)
    if not is_close_decision_pending(db, order_line_id):
        raise HTTPException(status_code=409, detail="진행 중인 LOT·검수가 없고 최종검수와 정산이 끝난 출고부족 발주만 완료할 수 있습니다.")
    before = _snapshot(order)
    release_order_stock_reservations(db, order)
    order.status = "DONE"
    order.short_close_state = "CONFIRMED"
    order.manual_closed = True
    order.updated_at = utc_now()
    record_order_line_change(db, order_line_id=order_line_id, change_type=ORDER_LINE_SHORT_CLOSE,
        before_data=before, after_data={**_snapshot(order), "action": "MANUAL_CLOSE",
        "ship_target_qty": target, "shipped_qty": shipped, "remaining_ship_qty": max(target - shipped, 0)}, actor=actor)
    db.flush()
    return order


def reopen_manual_order_line(
    db: Session, order_line_id: int, payload: OrderLineShortCloseRequest, *, actor: str,
) -> OrderLine:
    order = _lock_order(db, order_line_id)
    if not order.manual_closed or order.status != "DONE":
        raise HTTPException(status_code=409, detail="현재 실적으로 수동완료한 발주만 완료 취소할 수 있습니다.")
    target = get_order_ship_target_qty(db, order)
    shipped = get_already_shipped_qty(db, order_line_id)
    _check_snapshot(order, payload, target, shipped)
    before = _snapshot(order)
    order.manual_closed = False
    order.short_close_state = "NONE"
    order.status = "CLOSED"
    order.updated_at = utc_now()
    # Re-evaluate automatic completion without touching quantities or restoring reservations.
    db.flush()
    sync_order_fulfillment_status(db, order)
    record_order_line_change(db, order_line_id=order_line_id, change_type=ORDER_LINE_SHORT_CLOSE,
        before_data=before, after_data={**_snapshot(order), "action": "MANUAL_REOPEN",
        "ship_target_qty": target, "shipped_qty": shipped}, actor=actor)
    db.flush()
    return order


def reopen_order_for_rework(db: Session, order: OrderLine, *, lot_id: int, actor: str) -> None:
    before = _snapshot(order)
    had_decision = order.short_close_state != "NONE" or order.manual_closed
    order.status = "CLOSED"
    order.manual_closed = False
    order.short_close_state = "NONE"
    order.updated_at = utc_now()
    if had_decision:
        record_order_line_change(db, order_line_id=order.order_line_id, lot_id=lot_id,
            change_type=ORDER_LINE_SHORT_CLOSE, before_data=before,
            after_data={**_snapshot(order), "action": "REWORK_REOPEN"}, actor=actor)
