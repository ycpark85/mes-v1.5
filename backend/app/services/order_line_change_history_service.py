from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.order_line_change_log import OrderLineChangeLog


ORDER_LINE_QUANTITY_CHANGE = "QUANTITY_CHANGE"
ORDER_LINE_DUE_DATE_CHANGE = "DUE_DATE_CHANGE"
ORDER_LINE_MEMO_CHANGE = "MEMO_CHANGE"
QUANTITY_CHANGE_PLAN_MEMO_PREFIX = "수주수량 변경으로 처리계획 재계산:"


def record_order_line_change(
    db: Session,
    *,
    order_line_id: int,
    change_type: str,
    before_data: dict[str, Any],
    after_data: dict[str, Any],
    actor: str,
    lot_id: int | None = None,
    reason: str | None = None,
) -> OrderLineChangeLog:
    normalized_actor = actor.strip()
    if not normalized_actor:
        raise ValueError("actor is required for order-line change history")
    if before_data == after_data:
        raise ValueError("before_data and after_data must be different")

    change_log = OrderLineChangeLog(
        order_line_id=order_line_id,
        lot_id=lot_id,
        change_type=change_type,
        before_data=before_data,
        after_data=after_data,
        reason=reason.strip() if reason and reason.strip() else None,
        created_by=normalized_actor,
    )
    db.add(change_log)
    return change_log
