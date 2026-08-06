from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.crud.order_line import order_line_crud
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.partner import Partner
from app.models.product import Product
from app.schemas.order_line import OrderLineStatus
from app.schemas.order_line_detail import (
    OrderLineDetailDto,
    OrderLineDetailLotDto,
    OrderLineTimelineItemDto,
)
from app.services.order_quantity_change_history import parse_order_quantity_change_memo
from app.services.order_line_change_timeline import (
    OrderLineChangeTimelineEvent,
    get_order_line_change_timeline_events,
)
from app.services.order_line_change_history_service import (
    QUANTITY_CHANGE_PLAN_MEMO_PREFIX,
)
from app.services.outsource_work_timeline import (
    OutsourceWorkTimelineEvent,
    get_outsource_work_timeline_events,
)


def get_order_line_detail_dto(
    db: Session,
    order_line_id: int,
    *,
    include_plan_history: bool = True,
) -> OrderLineDetailDto:
    order_line = order_line_crud.get(db, order_line_id)
    if not order_line or not order_line.is_active:
        raise HTTPException(status_code=404, detail="OrderLine not found")

    partner = db.get(Partner, order_line.partner_id)
    product = db.get(Product, order_line.product_id)
    lots = _load_order_line_lots(db, order_line_id)
    plan_histories = _load_plan_histories(db, order_line_id) if include_plan_history else []
    lot_no_by_id = {lot.lot_id: lot.lot_no for lot in lots}
    order_change_events = get_order_line_change_timeline_events(
        db,
        order_line_id=order_line_id,
        uom=order_line.uom,
        lot_no_by_id=lot_no_by_id,
    )
    outsource_events = get_outsource_work_timeline_events(
        db,
        lot_ids=[lot.lot_id for lot in lots],
    )

    return build_order_line_detail_dto(
        order_line=order_line,
        partner=partner,
        product=product,
        lots=lots,
        plan_histories=plan_histories,
        order_change_events=order_change_events,
        outsource_events=outsource_events,
    )


def _load_order_line_lots(db: Session, order_line_id: int) -> list[Lot]:
    return (
        db.execute(
            select(Lot)
            .options(selectinload(Lot.steps))
            .where(Lot.order_line_id == order_line_id)
            .order_by(Lot.created_date.asc(), Lot.lot_id.asc())
        )
        .scalars()
        .all()
    )


def _load_plan_histories(db: Session, order_line_id: int) -> list[OrderLinePlanHistory]:
    return (
        db.execute(
            select(OrderLinePlanHistory)
            .where(OrderLinePlanHistory.order_line_id == order_line_id)
            .order_by(
                OrderLinePlanHistory.created_at.asc(),
                OrderLinePlanHistory.plan_history_id.asc(),
            )
        )
        .scalars()
        .all()
    )


def build_order_line_detail_dto(
    *,
    order_line: OrderLine,
    partner: Partner | None,
    product: Product | None,
    lots: list[Lot],
    plan_histories: list[OrderLinePlanHistory] | None = None,
    order_change_events: list[OrderLineChangeTimelineEvent] | None = None,
    outsource_events: list[OutsourceWorkTimelineEvent] | None = None,
) -> OrderLineDetailDto:
    plan_histories = plan_histories or []
    order_change_events = order_change_events or []
    outsource_events = outsource_events or []
    has_any_lot = len(lots) > 0
    has_base_lot = any(l.parent_lot_id is None for l in lots)

    can_edit = order_line.status in {
        OrderLineStatus.OPEN.value,
        OrderLineStatus.CLOSED.value,
    }
    can_save = can_edit
    can_cancel_order = (
        order_line.status not in {OrderLineStatus.DONE.value, OrderLineStatus.CANCELED.value}
        and (
            not has_any_lot
            or all(l.status == "CANCELED" for l in lots)
        )
    )
    can_create_base_lot = (
        order_line.status == OrderLineStatus.OPEN.value
        and not has_base_lot
    )

    lot_items = [_build_lot_detail_item(lot) for lot in lots]

    timeline = _build_detail_timeline(order_line, lots)
    primary_lot_ids = [lot.lot_id for lot in lots if lot.parent_lot_id is None]
    timeline.extend(
        _build_plan_history_timeline_items(
            plan_histories,
            uom=order_line.uom,
            lot_no_by_id={lot.lot_id: lot.lot_no for lot in lots},
            legacy_lot_id=primary_lot_ids[0] if len(primary_lot_ids) == 1 else None,
        )
    )
    timeline.extend(_build_order_change_timeline_items(order_change_events))
    timeline.extend(
        _build_outsource_timeline_items(
            outsource_events,
            lot_no_by_id={lot.lot_id: lot.lot_no for lot in lots},
        )
    )
    timeline.sort(key=lambda x: _timeline_sort_key(x.event_at))

    return OrderLineDetailDto(
        order_line_id=order_line.order_line_id,
        order_no=order_line.order_no,
        line_no=order_line.line_no,
        partner_id=order_line.partner_id,
        partner_name=partner.name if partner else "",
        product_id=order_line.product_id,
        product_code=product.product_code if product else "",
        product_name=product.product_name if product else "",
        order_date=order_line.order_date,
        due_date=order_line.due_date,
        order_qty=order_line.order_qty,
        uom=order_line.uom,
        customer_po=order_line.customer_po,
        memo=order_line.memo,
        status=order_line.status,
        status_display=_to_status_display(order_line.status),
        is_active=order_line.is_active,
        can_edit=can_edit,
        can_save=can_save,
        can_cancel_order=can_cancel_order,
        can_create_base_lot=can_create_base_lot,
        lots=lot_items,
        timeline=timeline,
    )


def _build_lot_detail_item(lot: Lot) -> OrderLineDetailLotDto:
    is_done_or_canceled = lot.status in {"DONE", "CANCELED"}

    return OrderLineDetailLotDto(
        lot_id=lot.lot_id,
        lot_no=lot.lot_no,
        lot_type="REWORK" if lot.parent_lot_id else "NORMAL",
        parent_lot_id=lot.parent_lot_id,
        lot_qty=lot.lot_qty,
        status=lot.status,
        current_process_name=_get_lot_current_process_name(lot),
        is_editable=not is_done_or_canceled,
        can_cancel=not is_done_or_canceled,
        can_create_rework=is_done_or_canceled,
    )


def _to_status_display(order_status: str) -> str:
    return "IN_PROGRESS" if order_status == OrderLineStatus.CLOSED.value else order_status


def _get_lot_current_process_name(lot: Lot) -> Optional[str]:
    in_progress = next((s for s in lot.steps if s.status == "IN_PROGRESS"), None)
    if in_progress:
        return in_progress.process_name

    waiting = next((s for s in lot.steps if s.status == "WAITING"), None)
    if waiting:
        return waiting.process_name

    return None


def _to_plan_timeline_message(history: OrderLinePlanHistory) -> str:
    plan_type = history.plan_type

    ship_target_qty = int(history.ship_target_qty or 0)
    available_inventory_qty = int(history.available_inventory_qty or 0)
    stock_ship_qty = int(history.stock_ship_qty or 0)
    production_qty = int(history.production_qty or 0)

    if plan_type == "AUTO_PRODUCTION":
        return (
            f"처리계획 확정: 현재고 없음, "
            f"출고목표수량 {ship_target_qty:,}개 기준으로 "
            f"생산필요수량 {production_qty:,}개 생산을 진행합니다."
        )

    if plan_type == "AUTO_STOCK_SHIP":
        return (
            f"처리계획 확정: 현재고 {available_inventory_qty:,}개 중 "
            f"{stock_ship_qty:,}개를 재고 출하대기로 생성했습니다."
        )

    if plan_type == "PARTIAL_STOCK_ONLY_CLOSE":
        return (
            f"처리계획 확정: 현재고 {available_inventory_qty:,}개 중 "
            f"{stock_ship_qty:,}개만 출하하고 부족분 생산 없이 종료합니다."
        )

    if plan_type == "PARTIAL_STOCK_PLUS_PRODUCTION":
        return (
            f"처리계획 확정: 현재고 {available_inventory_qty:,}개 사용 예정, "
            f"부족분 {production_qty:,}개 생산 후 출고목표수량 "
            f"{ship_target_qty:,}개를 맞춥니다."
        )

    if plan_type == "STOCK_REPLENISHMENT":
        return (
            f"처리계획 확정: 재고비축 목적 발주로 "
            f"{production_qty:,}개 생산 후 재고로 입고합니다."
        )

    return "처리계획이 확정되었습니다."


def _build_plan_history_timeline_items(
    plan_histories: list[OrderLinePlanHistory],
    *,
    uom: str,
    lot_no_by_id: dict[int, str],
    legacy_lot_id: int | None,
) -> list[OrderLineTimelineItemDto]:
    items: list[OrderLineTimelineItemDto] = []

    for history in plan_histories:
        if history.memo and history.memo.startswith(QUANTITY_CHANGE_PLAN_MEMO_PREFIX):
            continue

        quantity_change = parse_order_quantity_change_memo(history.memo)
        if quantity_change is not None:
            resolved_lot_id = quantity_change.lot_id or legacy_lot_id
            lot_label = (
                lot_no_by_id.get(resolved_lot_id, f"LOT ID {resolved_lot_id}")
                if resolved_lot_id is not None
                else "LOT"
            )
            items.append(
                OrderLineTimelineItemDto(
                    event_type="ORDER_QUANTITY_CHANGED",
                    event_label="수주수량 정정",
                    event_at=history.created_at,
                    message=(
                        f"수주수량 {quantity_change.old_order_qty:,} {uom} → "
                        f"{quantity_change.new_order_qty:,} {uom} / "
                        f"{lot_label} 계획수량 {quantity_change.old_lot_qty:,} {uom} → "
                        f"{quantity_change.new_lot_qty:,} {uom}"
                    ),
                    ref_type="ORDER_LINE_PLAN_HISTORY",
                    ref_id=history.plan_history_id,
                )
            )
            continue

        message = _to_plan_timeline_message(history)

        if history.memo:
            message = f"{message} 메모: {history.memo}"

        items.append(
            OrderLineTimelineItemDto(
                event_type="PLAN_CONFIRMED",
                event_label="처리계획 확정",
                event_at=history.created_at,
                message=message,
                ref_type="ORDER_LINE_PLAN_HISTORY",
                ref_id=history.plan_history_id,
            )
        )

    return items


def _build_outsource_timeline_items(
    events: list[OutsourceWorkTimelineEvent],
    *,
    lot_no_by_id: dict[int, str],
) -> list[OrderLineTimelineItemDto]:
    items: list[OrderLineTimelineItemDto] = []
    for event in events:
        lot_label = lot_no_by_id.get(event.lot_id, f"LOT ID {event.lot_id}")
        message = (
            f"{lot_label} / {event.instruction_no} / "
            f"{event.process_type} / {event.group_seq}"
        )
        if event.details:
            message = f"{message} / {event.details}"
        if event.reason:
            reason_label = "취소사유" if event.status == "CANCELED" else "수정사유"
            message = f"{message} / {reason_label}: {event.reason}"
        if event.actor:
            message = f"{message} / 처리자: {event.actor}"

        items.append(
            OrderLineTimelineItemDto(
                event_type=event.event_type,
                event_label=event.title,
                event_at=event.event_at,
                message=message,
                ref_type=event.ref_type,
                ref_id=event.ref_id,
            )
        )
    return items


def _build_order_change_timeline_items(
    events: list[OrderLineChangeTimelineEvent],
) -> list[OrderLineTimelineItemDto]:
    return [
        OrderLineTimelineItemDto(
            event_type=event.event_type,
            event_label=event.title,
            event_at=event.event_at,
            message=f"{event.summary} / 처리자: {event.actor}",
            ref_type="ORDER_LINE_CHANGE_LOG",
            ref_id=event.ref_id,
        )
        for event in events
    ]


def _build_detail_timeline(
    order_line: OrderLine,
    lots: list[Lot],
) -> list[OrderLineTimelineItemDto]:
    items: list[OrderLineTimelineItemDto] = []

    items.append(
        OrderLineTimelineItemDto(
            event_type="ORDER_CREATED",
            event_label="수주 생성",
            event_at=order_line.created_at,
            message=f"수주가 등록되었습니다. (수주수량 {order_line.order_qty:,} {order_line.uom})",
            ref_type="ORDER_LINE",
            ref_id=order_line.order_line_id,
        )
    )

    for lot in lots:
        lot_type = "REWORK" if lot.parent_lot_id else "NORMAL"
        label = "재작업 LOT 생성" if lot.parent_lot_id else "기본 LOT 생성"

        items.append(
            OrderLineTimelineItemDto(
                event_type="LOT_CREATED",
                event_label=label,
                event_at=lot.created_at,
                message=f"{lot.lot_no} / {lot_type} / 계획수량 {lot.lot_qty:,} {lot.uom}",
                ref_type="LOT",
                ref_id=lot.lot_id,
            )
        )

        if lot.status == "DONE":
            items.append(
                OrderLineTimelineItemDto(
                    event_type="LOT_DONE",
                    event_label="LOT 완료",
                    event_at=lot.updated_at,
                    message=f"{lot.lot_no} LOT가 완료되었습니다.",
                    ref_type="LOT",
                    ref_id=lot.lot_id,
                )
            )
        elif lot.status == "CANCELED":
            items.append(
                OrderLineTimelineItemDto(
                    event_type="LOT_CANCELED",
                    event_label="LOT 취소",
                    event_at=lot.updated_at,
                    message=f"{lot.lot_no} LOT가 취소되었습니다.",
                    ref_type="LOT",
                    ref_id=lot.lot_id,
                )
            )

    if order_line.status == OrderLineStatus.CANCELED.value:
        items.append(
            OrderLineTimelineItemDto(
                event_type="ORDER_CANCELED",
                event_label="수주 취소",
                event_at=order_line.updated_at,
                message="수주가 취소되었습니다.",
                ref_type="ORDER_LINE",
                ref_id=order_line.order_line_id,
            )
        )

    items.sort(key=lambda x: _timeline_sort_key(x.event_at), reverse=True)
    return items


def _timeline_sort_key(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
