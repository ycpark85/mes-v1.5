from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.lot_step import LotStep
from app.models.order_line import OrderLine
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.partner import Partner
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.shipment_line import ShipmentLine
from app.schemas.order_line import OrderLinePlanType, OrderLineStatus
from app.services.order_line_change_history_service import (
    ORDER_LINE_QUANTITY_CHANGE,
    QUANTITY_CHANGE_PLAN_MEMO_PREFIX,
    record_order_line_change,
)
from app.services.order_line_plan_service import (
    create_plan_history,
    get_available_inventory_qty,
    get_latest_plan_history,
)
from app.services.ship_qty_policy import (
    calculate_ship_qty,
    is_stock_replenishment_partner,
)


def apply_order_quantity_change(
    db: Session,
    *,
    order_line: OrderLine,
    old_order_qty: int,
    new_order_qty: int,
    actor: str,
) -> None:
    lots = (
        db.execute(
            select(Lot)
            .where(Lot.order_line_id == order_line.order_line_id)
            .order_by(Lot.created_date.asc(), Lot.lot_id.asc())
            .with_for_update()
        )
        .scalars()
        .all()
    )

    if not lots:
        _invalidate_unreleased_plan(db, order_line)
        _record_quantity_change(
            db,
            order_line=order_line,
            actor=actor,
            old_order_qty=old_order_qty,
            new_order_qty=new_order_qty,
        )
        return

    active_lots = [lot for lot in lots if lot.status != "CANCELED"]
    if len(active_lots) != 1 or active_lots[0].parent_lot_id is not None:
        raise HTTPException(
            status_code=409,
            detail="수량을 직접 변경할 수 없는 LOT 구성입니다. 기본 LOT와 재작업 LOT를 확인하세요.",
        )

    lot = active_lots[0]
    if lot.status != "WAITING" or _has_started_lot_step(db, lot.lot_id):
        raise HTTPException(
            status_code=409,
            detail="LOT 작업이 시작되어 수주수량을 직접 변경할 수 없습니다. 추가 LOT 또는 감산 처리하세요.",
        )

    if _has_active_outsource_work(db, lot.lot_id):
        raise HTTPException(
            status_code=409,
            detail="진행 중인 외주 작업지시가 있습니다. 외주 작업지시를 먼저 취소하세요.",
        )

    if _has_active_inspection_or_result(db, lot.lot_id):
        raise HTTPException(
            status_code=409,
            detail="진행 중인 검수 일정 또는 검수 결과가 있어 수주수량을 변경할 수 없습니다.",
        )

    active_shipment_lines = _get_active_shipment_lines_for_update(
        db,
        order_line.order_line_id,
    )
    if _has_inventory_movement(db, order_line.order_line_id):
        raise HTTPException(
            status_code=409,
            detail="실제 재고 수불 이력이 있어 수주수량을 직접 변경할 수 없습니다.",
        )

    latest_plan = get_latest_plan_history(db, order_line.order_line_id)
    reserved_stock_qty = _get_reusable_partial_stock_qty(
        latest_plan=latest_plan,
        active_shipment_lines=active_shipment_lines,
    )

    partner = db.get(Partner, order_line.partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")

    is_stock_replenishment = is_stock_replenishment_partner(
        partner.name,
        partner.business_no,
    )
    plan_type = (
        OrderLinePlanType.PARTIAL_STOCK_PLUS_PRODUCTION
        if reserved_stock_qty > 0
        else _resolve_quantity_change_plan_type(
            latest_plan,
            is_stock_replenishment,
        )
    )
    ship_target_qty = (
        0
        if plan_type == OrderLinePlanType.STOCK_REPLENISHMENT
        else int(calculate_ship_qty(partner.name, new_order_qty) or 0)
    )
    extra_production_qty = (
        int(order_line.extra_production_qty or 0)
        if order_line.production_policy == "ALLOW_STOCK_BUILD"
        and plan_type != OrderLinePlanType.STOCK_REPLENISHMENT
        else 0
    )
    if reserved_stock_qty > 0:
        production_qty = ship_target_qty - reserved_stock_qty
        if production_qty <= 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    "변경된 출고목표수량이 기존 예약재고 이하라 생산 LOT가 "
                    "불필요해집니다. 처리계획을 다시 수립하세요."
                ),
            )
    else:
        production_qty = (
            new_order_qty
            if plan_type == OrderLinePlanType.STOCK_REPLENISHMENT
            else ship_target_qty + extra_production_qty
        )

    if production_qty <= 0:
        raise HTTPException(
            status_code=409,
            detail="변경된 수량으로 계산된 생산수량이 0 이하입니다. 처리계획을 다시 확인하세요.",
        )

    old_lot_qty = int(lot.lot_qty or 0)
    if (
        reserved_stock_qty > 0
        and latest_plan is not None
        and old_lot_qty != int(latest_plan.production_qty or 0)
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "기존 처리계획 생산수량과 LOT 계획수량이 일치하지 않아 "
                "자동으로 변경할 수 없습니다."
            ),
        )

    lot.lot_qty = production_qty

    available_inventory_qty = get_available_inventory_qty(
        db,
        order_line.product_id,
    )
    if reserved_stock_qty > 0:
        available_inventory_qty += reserved_stock_qty

    create_plan_history(
        db,
        order_line=order_line,
        plan_type=plan_type,
        ship_target_qty=ship_target_qty,
        available_inventory_qty=available_inventory_qty,
        stock_ship_qty=reserved_stock_qty,
        production_qty=production_qty,
        is_short_close=False,
        memo=(
            f"{QUANTITY_CHANGE_PLAN_MEMO_PREFIX} {old_order_qty:,} → "
            f"{new_order_qty:,} / "
            + (
                f"예약재고 {reserved_stock_qty:,} 유지 / "
                if reserved_stock_qty > 0
                else ""
            )
            + f"LOT 계획수량 {old_lot_qty:,} → "
            f"{production_qty:,}"
        ),
        actor=actor,
    )
    _record_quantity_change(
        db,
        order_line=order_line,
        actor=actor,
        old_order_qty=old_order_qty,
        new_order_qty=new_order_qty,
        lot=lot,
        old_lot_qty=old_lot_qty,
        new_lot_qty=production_qty,
        before_plan_data=(
            {
                "ship_target_qty": int(latest_plan.ship_target_qty or 0),
                "stock_ship_qty": int(latest_plan.stock_ship_qty or 0),
                "production_qty": int(latest_plan.production_qty or 0),
            }
            if latest_plan is not None
            else None
        ),
        after_plan_data={
            "ship_target_qty": ship_target_qty,
            "stock_ship_qty": reserved_stock_qty,
            "production_qty": production_qty,
        },
    )


def _record_quantity_change(
    db: Session,
    *,
    order_line: OrderLine,
    actor: str,
    old_order_qty: int,
    new_order_qty: int,
    lot: Lot | None = None,
    old_lot_qty: int | None = None,
    new_lot_qty: int | None = None,
    before_plan_data: dict[str, int] | None = None,
    after_plan_data: dict[str, int] | None = None,
) -> None:
    before_data: dict[str, object] = {
        "order_qty": old_order_qty,
        "lot_qty": old_lot_qty,
    }
    after_data: dict[str, object] = {
        "order_qty": new_order_qty,
        "lot_qty": new_lot_qty,
    }
    if before_plan_data is not None:
        before_data["plan"] = before_plan_data
    if after_plan_data is not None:
        after_data["plan"] = after_plan_data

    record_order_line_change(
        db,
        order_line_id=order_line.order_line_id,
        lot_id=lot.lot_id if lot is not None else None,
        change_type=ORDER_LINE_QUANTITY_CHANGE,
        before_data=before_data,
        after_data=after_data,
        actor=actor,
    )


def _invalidate_unreleased_plan(db: Session, order_line: OrderLine) -> None:
    waiting_stock_lines = (
        db.execute(
            select(ShipmentLine)
            .where(
                ShipmentLine.order_line_id == order_line.order_line_id,
                ShipmentLine.source_type == "STOCK",
                ShipmentLine.status == "WAITING",
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )

    for line in waiting_stock_lines:
        line.status = "CANCELED"
        previous_memo = (line.memo or "").strip()
        cancel_memo = "수주수량 변경으로 처리계획 재확정 필요"
        line.memo = f"{previous_memo}\n{cancel_memo}" if previous_memo else cancel_memo

    order_line.decision_made = False
    order_line.decision_made_at = None
    order_line.decision_made_by = None
    if order_line.status == OrderLineStatus.CLOSED.value:
        order_line.status = OrderLineStatus.OPEN.value


def _has_started_lot_step(db: Session, lot_id: int) -> bool:
    return (
        db.execute(
            select(LotStep.lot_step_id)
            .where(LotStep.lot_id == lot_id, LotStep.status != "WAITING")
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _has_active_outsource_work(db: Session, lot_id: int) -> bool:
    return (
        db.execute(
            select(OutsourceWorkGroupItem.outsource_work_group_item_id)
            .join(
                OutsourceWorkGroup,
                OutsourceWorkGroup.outsource_work_group_id
                == OutsourceWorkGroupItem.outsource_work_group_id,
            )
            .where(
                OutsourceWorkGroupItem.lot_id == lot_id,
                (
                    OutsourceWorkGroup.status.is_(None)
                    | (OutsourceWorkGroup.status != "CANCELED")
                ),
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _has_active_inspection_or_result(db: Session, lot_id: int) -> bool:
    active_schedule_exists = (
        db.execute(
            select(InspectionSchedule.inspection_schedule_id)
            .where(
                InspectionSchedule.lot_id == lot_id,
                InspectionSchedule.status != "CANCELED",
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )
    if active_schedule_exists:
        return True

    return (
        db.execute(
            select(InspectionResult.inspection_result_id)
            .join(
                InspectionSchedule,
                InspectionSchedule.inspection_schedule_id
                == InspectionResult.inspection_schedule_id,
            )
            .where(InspectionSchedule.lot_id == lot_id)
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _get_active_shipment_lines_for_update(
    db: Session,
    order_line_id: int,
) -> list[ShipmentLine]:
    return (
        db.execute(
            select(ShipmentLine)
            .where(
                ShipmentLine.order_line_id == order_line_id,
                ShipmentLine.status != "CANCELED",
            )
            .order_by(ShipmentLine.shipment_line_id.asc())
            .with_for_update()
        )
        .scalars()
        .all()
    )


def _has_inventory_movement(db: Session, order_line_id: int) -> bool:
    return (
        db.execute(
            select(ProductInventoryMovement.inventory_movement_id)
            .where(ProductInventoryMovement.order_line_id == order_line_id)
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _get_reusable_partial_stock_qty(
    *,
    latest_plan: OrderLinePlanHistory | None,
    active_shipment_lines: list[ShipmentLine],
) -> int:
    is_partial_stock_plan = (
        latest_plan is not None
        and latest_plan.plan_type
        == OrderLinePlanType.PARTIAL_STOCK_PLUS_PRODUCTION.value
    )

    if not is_partial_stock_plan:
        if active_shipment_lines:
            raise HTTPException(
                status_code=409,
                detail=(
                    "출하대기 또는 출하완료 내역이 있어 수주수량을 직접 "
                    "변경할 수 없습니다."
                ),
            )
        if latest_plan is not None and int(latest_plan.stock_ship_qty or 0) > 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    "재고 출하가 포함된 처리계획은 수량을 직접 변경할 수 "
                    "없습니다. 처리계획을 다시 수립하세요."
                ),
            )
        return 0

    if not active_shipment_lines or any(
        line.source_type != "STOCK"
        or line.status != "WAITING"
        or int(line.shipped_qty or 0) != 0
        or line.inspection_result_id is not None
        for line in active_shipment_lines
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "부분재고 예약이 이미 출하 처리되었거나 변경되어 "
                "수주수량을 직접 변경할 수 없습니다."
            ),
        )

    expected_stock_qty = int(latest_plan.stock_ship_qty or 0)
    reserved_stock_qty = sum(
        int(line.ship_qty or 0)
        for line in active_shipment_lines
    )
    if expected_stock_qty <= 0 or reserved_stock_qty != expected_stock_qty:
        raise HTTPException(
            status_code=409,
            detail=(
                "처리계획의 예약재고와 실제 출하대기 수량이 일치하지 않아 "
                "자동으로 변경할 수 없습니다."
            ),
        )

    return reserved_stock_qty


def _resolve_quantity_change_plan_type(
    latest_plan: OrderLinePlanHistory | None,
    is_stock_replenishment: bool,
) -> OrderLinePlanType:
    if is_stock_replenishment:
        return OrderLinePlanType.STOCK_REPLENISHMENT

    if latest_plan is not None:
        try:
            return OrderLinePlanType(latest_plan.plan_type)
        except ValueError:
            pass

    return OrderLinePlanType.AUTO_PRODUCTION
