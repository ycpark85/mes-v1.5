from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order_line_change_log import OrderLineChangeLog
from app.services.order_line_change_history_service import (
    ORDER_LINE_DUE_DATE_CHANGE,
    ORDER_LINE_MEMO_CHANGE,
    ORDER_LINE_QUANTITY_CHANGE,
)


@dataclass(frozen=True, slots=True)
class OrderLineChangeTimelineEvent:
    lot_id: int | None
    event_type: str
    event_at: datetime
    title: str
    summary: str
    actor: str
    ref_id: int


def get_order_line_change_timeline_events(
    db: Session,
    *,
    order_line_id: int,
    uom: str,
    lot_no_by_id: dict[int, str],
) -> list[OrderLineChangeTimelineEvent]:
    change_logs = (
        db.execute(
            select(OrderLineChangeLog)
            .where(OrderLineChangeLog.order_line_id == order_line_id)
            .order_by(
                OrderLineChangeLog.created_at.asc(),
                OrderLineChangeLog.order_line_change_log_id.asc(),
            )
        )
        .scalars()
        .all()
    )

    return [
        _build_timeline_event(
            change_log,
            uom=uom,
            lot_no_by_id=lot_no_by_id,
        )
        for change_log in change_logs
    ]


def _build_timeline_event(
    change_log: OrderLineChangeLog,
    *,
    uom: str,
    lot_no_by_id: dict[int, str],
) -> OrderLineChangeTimelineEvent:
    if change_log.change_type == ORDER_LINE_QUANTITY_CHANGE:
        title = "수주수량 정정"
        event_type = "ORDER_QUANTITY_CHANGED"
        old_order_qty = _to_int(change_log.before_data.get("order_qty"))
        new_order_qty = _to_int(change_log.after_data.get("order_qty"))
        summary = (
            f"수주수량 {old_order_qty:,} {uom} → "
            f"{new_order_qty:,} {uom}"
        )
        old_lot_qty = _to_optional_int(change_log.before_data.get("lot_qty"))
        new_lot_qty = _to_optional_int(change_log.after_data.get("lot_qty"))
        if (
            change_log.lot_id is not None
            and old_lot_qty is not None
            and new_lot_qty is not None
        ):
            lot_label = lot_no_by_id.get(
                change_log.lot_id,
                f"LOT ID {change_log.lot_id}",
            )
            summary = (
                f"{summary} / {lot_label} 계획수량 "
                f"{old_lot_qty:,} {uom} → {new_lot_qty:,} {uom}"
            )

        before_plan = change_log.before_data.get("plan")
        after_plan = change_log.after_data.get("plan")
        if isinstance(before_plan, dict) and isinstance(after_plan, dict):
            old_stock_qty = _to_optional_int(before_plan.get("stock_ship_qty"))
            new_stock_qty = _to_optional_int(after_plan.get("stock_ship_qty"))
            if old_stock_qty is not None and new_stock_qty is not None:
                if old_stock_qty == new_stock_qty and new_stock_qty > 0:
                    summary = (
                        f"{summary} / 예약재고 {new_stock_qty:,} {uom} 유지"
                    )
                elif old_stock_qty != new_stock_qty:
                    summary = (
                        f"{summary} / 예약재고 {old_stock_qty:,} {uom} → "
                        f"{new_stock_qty:,} {uom}"
                    )
    elif change_log.change_type == ORDER_LINE_DUE_DATE_CHANGE:
        title = "납기일 변경"
        event_type = "ORDER_DUE_DATE_CHANGED"
        summary = (
            f"납기일 {_format_text(change_log.before_data.get('due_date'))} → "
            f"{_format_text(change_log.after_data.get('due_date'))}"
        )
    elif change_log.change_type == ORDER_LINE_MEMO_CHANGE:
        title = "수주메모 변경"
        event_type = "ORDER_MEMO_CHANGED"
        summary = (
            f"메모 {_format_text(change_log.before_data.get('memo'))} → "
            f"{_format_text(change_log.after_data.get('memo'))}"
        )
    else:
        raise ValueError(f"Unsupported order-line change type: {change_log.change_type}")

    if change_log.reason:
        summary = f"{summary} / 사유: {change_log.reason}"

    return OrderLineChangeTimelineEvent(
        lot_id=change_log.lot_id,
        event_type=event_type,
        event_at=change_log.created_at,
        title=title,
        summary=summary,
        actor=change_log.created_by,
        ref_id=change_log.order_line_change_log_id,
    )


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid quantity change value: {value}") from exc


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return _to_int(value)


def _format_text(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)
