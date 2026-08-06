from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.order_line import OrderLine
from app.schemas.order_line import OrderLineStatus
from app.schemas.order_line_detail import OrderLineDetailUpdate
from app.services.order_line_change_history_service import (
    ORDER_LINE_DUE_DATE_CHANGE,
    ORDER_LINE_MEMO_CHANGE,
    record_order_line_change,
)
from app.services.order_line_quantity_change_service import apply_order_quantity_change
from app.services.order_line_update_service import propagate_order_line_due_date
from app.services.production_daily_query import refresh_order_line_snapshot


def update_order_line_detail_fields(
    db: Session,
    order_line_id: int,
    payload: OrderLineDetailUpdate,
    *,
    actor: str,
) -> OrderLine:
    actor = actor.strip()
    if not actor:
        raise ValueError("actor is required for order-line detail update")

    order_line = (
        db.execute(
            select(OrderLine)
            .where(OrderLine.order_line_id == order_line_id)
            .with_for_update()
        )
        .scalar_one_or_none()
    )
    if not order_line or not order_line.is_active:
        raise HTTPException(status_code=404, detail="OrderLine not found")

    if order_line.status in {
        OrderLineStatus.DONE.value,
        OrderLineStatus.CANCELED.value,
    }:
        raise HTTPException(
            status_code=409,
            detail="DONE 또는 CANCELED 상태의 수주는 수정할 수 없습니다.",
        )

    if payload.order_qty <= 0:
        raise HTTPException(status_code=422, detail="order_qty must be greater than 0")

    old_order_qty = int(order_line.order_qty or 0)
    old_due_date = order_line.due_date
    old_memo = order_line.memo

    if payload.order_qty != old_order_qty:
        apply_order_quantity_change(
            db,
            order_line=order_line,
            old_order_qty=old_order_qty,
            new_order_qty=payload.order_qty,
            actor=actor,
        )

    if payload.due_date != old_due_date:
        record_order_line_change(
            db,
            order_line_id=order_line.order_line_id,
            change_type=ORDER_LINE_DUE_DATE_CHANGE,
            before_data={"due_date": old_due_date.isoformat()},
            after_data={"due_date": payload.due_date.isoformat()},
            actor=actor,
        )

    if payload.memo != old_memo:
        record_order_line_change(
            db,
            order_line_id=order_line.order_line_id,
            change_type=ORDER_LINE_MEMO_CHANGE,
            before_data={"memo": old_memo},
            after_data={"memo": payload.memo},
            actor=actor,
        )

    order_line.due_date = payload.due_date
    order_line.order_qty = payload.order_qty
    order_line.memo = payload.memo
    order_line.updated_at = utc_now()

    db.add(order_line)

    if payload.due_date != old_due_date:
        propagate_order_line_due_date(db, order_line_id, payload.due_date)
    else:
        refresh_order_line_snapshot(db, order_line_id)

    db.flush()
    return order_line
