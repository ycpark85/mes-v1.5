from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.order_line import OrderLine
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.shipment_line import ShipmentLine
from app.schemas.order_line import (
    OrderLineFulfillmentMode,
    OrderLinePlanConfirmRequest,
    OrderLinePlanType,
    OrderLineProductionPolicy,
    OrderLineStatus,
)
from app.services.inventory_fifo_service import allocate_inventory_lots_fifo, get_available_inventory_lots_fifo
from app.services.inventory_lock_service import lock_product_inventory
from app.services.production_daily_query import (
    refresh_order_line_snapshot,
    refresh_order_line_snapshots_for_product,
)
from app.services.shipment_confirm_service import confirm_shipment_lines_in_session
from app.services.ship_qty_policy import calculate_ship_qty


def get_available_inventory_qty(db: Session, product_id: int) -> int:
    inventory = (
        db.execute(
            select(ProductInventory)
            .where(ProductInventory.product_id == product_id)
        )
        .scalar_one_or_none()
    )
    current_qty = int(inventory.current_qty or 0) if inventory else 0
    reserved_qty = get_reserved_stock_shipment_qty(db, product_id=product_id)
    lot_available = sum(qty for _, qty in get_available_inventory_lots_fifo(db, product_id=product_id))
    return min(max(current_qty - reserved_qty, 0), lot_available)


def get_reserved_stock_shipment_qty(
    db: Session,
    *,
    product_id: int,
    order_line_id: int | None = None,
) -> int:
    conditions = [
        ShipmentLine.product_id == product_id,
        ShipmentLine.source_type == "STOCK",
        ShipmentLine.status == "WAITING",
    ]

    if order_line_id is not None:
        conditions.append(ShipmentLine.order_line_id == order_line_id)

    reserved_qty = db.execute(
        select(func.coalesce(func.sum(ShipmentLine.ship_qty), 0)).where(*conditions)
    ).scalar_one()

    return int(reserved_qty or 0)


def get_target_ship_qty(order_line: OrderLine, partner_name: str) -> int:
    return int(calculate_ship_qty(partner_name, int(order_line.order_qty or 0)) or 0)


def get_already_shipped_qty(db: Session, order_line_id: int) -> int:
    shipped_qty = db.execute(
        select(func.coalesce(func.sum(-ProductInventoryMovement.qty), 0)).where(
            ProductInventoryMovement.order_line_id == order_line_id,
            ProductInventoryMovement.movement_type == "SHIP_OUT",
        )
    ).scalar_one()

    return int(shipped_qty or 0)


def get_fifo_inventory_lot_allocations(
    db: Session,
    *,
    product_id: int,
    ship_qty: int,
) -> tuple[list[tuple[ProductInventoryLot, int]], int]:
    return allocate_inventory_lots_fifo(
        db,
        product_id=product_id,
        ship_qty=ship_qty,
        for_update=True,
    )


def add_stock_shipment_lines_by_inventory_lot(
    db: Session,
    *,
    order_line: OrderLine,
    ship_qty: int,
    memo: str,
) -> list[ShipmentLine]:
    lock_product_inventory(db, order_line.product_id)
    allocations, remaining_qty = get_fifo_inventory_lot_allocations(
        db,
        product_id=order_line.product_id,
        ship_qty=ship_qty,
    )

    created_lines: list[ShipmentLine] = []

    for inventory_lot, allocated_qty in allocations:
        line = ShipmentLine(
            order_line_id=order_line.order_line_id,
            product_id=order_line.product_id,
            product_inventory_lot_id=inventory_lot.product_inventory_lot_id,
            stock_lot_no=inventory_lot.lot_no,
            lot_id=None,
            inspection_result_id=None,
            source_type="STOCK",
            status="WAITING",
            ship_qty=allocated_qty,
            shipped_qty=0,
            memo=memo,
        )
        db.add(line)
        created_lines.append(line)

    if remaining_qty > 0:
        raise HTTPException(
            status_code=409,
            detail="가용 재고 LOT가 부족하여 재고 출하대기를 생성할 수 없습니다.",
        )

    db.flush()
    return created_lines


def get_latest_plan_history(
    db: Session,
    order_line_id: int,
) -> OrderLinePlanHistory | None:
    return (
        db.execute(
            select(OrderLinePlanHistory)
            .where(OrderLinePlanHistory.order_line_id == order_line_id)
            .order_by(
                OrderLinePlanHistory.created_at.desc(),
                OrderLinePlanHistory.plan_history_id.desc(),
            )
            .limit(1)
        )
        .scalar_one_or_none()
    )


def create_plan_history(
    db: Session,
    *,
    order_line: OrderLine,
    plan_type: OrderLinePlanType,
    ship_target_qty: int,
    available_inventory_qty: int,
    stock_ship_qty: int,
    production_qty: int,
    is_short_close: bool,
    memo: str | None,
    actor: str | None,
) -> OrderLinePlanHistory:
    history = OrderLinePlanHistory(
        order_line_id=order_line.order_line_id,
        plan_type=plan_type.value,
        ship_target_qty=ship_target_qty,
        available_inventory_qty=available_inventory_qty,
        stock_ship_qty=stock_ship_qty,
        production_qty=production_qty,
        is_short_close=is_short_close,
        memo=memo.strip() if memo and memo.strip() else None,
        created_by=actor,
    )

    db.add(history)
    db.flush()
    return history


def create_stock_shipment_waiting_for_plan(
    db: Session,
    *,
    order_line: OrderLine,
    ship_qty: int,
    memo: str,
) -> list[ShipmentLine]:
    if ship_qty <= 0:
        return []

    existing = (
        db.execute(
            select(ShipmentLine)
            .where(
                ShipmentLine.order_line_id == order_line.order_line_id,
                ShipmentLine.status != "CANCELED",
                ShipmentLine.source_type == "STOCK",
                ShipmentLine.inspection_result_id.is_(None),
            )
            .limit(1)
        )
        .scalar_one_or_none()
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="이미 생성된 재고 출하대기가 있습니다.",
        )

    return add_stock_shipment_lines_by_inventory_lot(
        db,
        order_line=order_line,
        ship_qty=ship_qty,
        memo=memo,
    )


def get_planned_production_qty(
    db: Session,
    order_line: OrderLine,
    partner_name: str,
) -> int:
    available_inventory_qty = get_available_inventory_qty(db, order_line.product_id)
    target_ship_qty = get_target_ship_qty(order_line, partner_name)

    fulfillment_mode = order_line.fulfillment_mode or "INVENTORY_FIRST"
    production_policy = order_line.production_policy or "ORDER_ONLY"
    extra_production_qty = int(order_line.extra_production_qty or 0)

    if fulfillment_mode == "PRODUCTION_FIRST":
        base_planned_production_qty = target_ship_qty
    else:
        base_planned_production_qty = max(target_ship_qty - available_inventory_qty, 0)

    if production_policy != "ALLOW_STOCK_BUILD":
        extra_production_qty = 0

    return base_planned_production_qty + extra_production_qty


def confirm_order_line_plan_decision(
    db: Session,
    *,
    order_line_id: int,
    payload: OrderLinePlanConfirmRequest,
) -> tuple[OrderLine, OrderLinePlanHistory, Partner, Product]:
    order_line = db.execute(select(OrderLine).where(OrderLine.order_line_id == order_line_id)
        .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()

    if not order_line or not order_line.is_active:
        raise HTTPException(status_code=404, detail="OrderLine not found")

    if order_line.status in {OrderLineStatus.DONE.value, OrderLineStatus.CANCELED.value}:
        raise HTTPException(
            status_code=409,
            detail="DONE 또는 CANCELED 상태의 수주는 처리계획을 확정할 수 없습니다.",
        )

    if order_line.decision_made:
        raise HTTPException(
            status_code=409,
            detail="이미 처리계획이 확정된 수주입니다.",
        )

    partner = db.get(Partner, order_line.partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    product = db.get(Product, order_line.product_id)
    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found or inactive")

    lock_product_inventory(db, order_line.product_id)
    actor = "system"
    plan_type = payload.plan_type
    available_inventory_qty = get_available_inventory_qty(db, order_line.product_id)

    if plan_type == OrderLinePlanType.STOCK_REPLENISHMENT:
        if available_inventory_qty <= 0:
            raise HTTPException(
                status_code=409,
                detail="현재고가 없는 발주는 기존 자동 생산 규칙을 사용합니다.",
            )

        ship_target_qty = 0
        stock_ship_qty = 0
        production_qty = int(order_line.order_qty or 0)
        is_short_close = False

        order_line.fulfillment_mode = OrderLineFulfillmentMode.PRODUCTION_FIRST.value
        order_line.production_policy = OrderLineProductionPolicy.ALLOW_STOCK_BUILD.value
        order_line.extra_production_qty = 0

    else:
        ship_target_qty = get_target_ship_qty(order_line, partner.name)
        already_shipped_qty = get_already_shipped_qty(db, order_line.order_line_id)
        remaining_ship_qty = max(ship_target_qty - already_shipped_qty, 0)

        if remaining_ship_qty <= 0:
            raise HTTPException(
                status_code=409,
                detail="이미 출고목표수량을 충족한 수주입니다.",
            )

        stock_ship_qty = 0
        production_qty = 0
        is_short_close = False

        if available_inventory_qty <= 0:
            if plan_type != OrderLinePlanType.AUTO_PRODUCTION:
                raise HTTPException(
                    status_code=409,
                    detail="현재고가 없는 수주는 자동 생산 처리만 가능합니다.",
                )

            production_qty = remaining_ship_qty
            order_line.fulfillment_mode = OrderLineFulfillmentMode.PRODUCTION_FIRST.value
            order_line.production_policy = OrderLineProductionPolicy.ORDER_ONLY.value
            order_line.extra_production_qty = 0

        elif available_inventory_qty >= remaining_ship_qty:
            if plan_type not in {
                OrderLinePlanType.STOCK_SHIP_COMPLETE,
                OrderLinePlanType.AUTO_STOCK_SHIP,
            }:
                raise HTTPException(
                    status_code=409,
                    detail="현재고가 출고목표수량 이상인 수주는 재고 출고완료 또는 재고생산만 선택할 수 있습니다.",
                )

            stock_ship_qty = remaining_ship_qty
            stock_lines = create_stock_shipment_waiting_for_plan(
                db,
                order_line=order_line,
                ship_qty=stock_ship_qty,
                memo="처리계획 확정: 재고 출고",
            )
            confirm_shipment_lines_in_session(
                db,
                [line.shipment_line_id for line in stock_lines],
            )

            order_line.fulfillment_mode = OrderLineFulfillmentMode.INVENTORY_FIRST.value
            order_line.production_policy = OrderLineProductionPolicy.INVENTORY_ONLY_CLOSE.value
            order_line.extra_production_qty = 0
            order_line.status = OrderLineStatus.DONE.value

        else:
            if plan_type == OrderLinePlanType.PARTIAL_STOCK_ONLY_CLOSE:
                stock_ship_qty = available_inventory_qty
                production_qty = 0
                is_short_close = True

                stock_lines = create_stock_shipment_waiting_for_plan(
                    db,
                    order_line=order_line,
                    ship_qty=stock_ship_qty,
                    memo="처리계획 확정: 부분재고만 출고 후 종료",
                )
                confirm_shipment_lines_in_session(
                    db,
                    [line.shipment_line_id for line in stock_lines],
                )

                order_line.fulfillment_mode = OrderLineFulfillmentMode.INVENTORY_FIRST.value
                order_line.production_policy = OrderLineProductionPolicy.INVENTORY_ONLY_CLOSE.value
                order_line.extra_production_qty = 0
                order_line.status = OrderLineStatus.DONE.value

            elif plan_type == OrderLinePlanType.PARTIAL_STOCK_PLUS_PRODUCTION:
                stock_ship_qty = available_inventory_qty
                production_qty = remaining_ship_qty - available_inventory_qty
                is_short_close = False

                create_stock_shipment_waiting_for_plan(
                    db,
                    order_line=order_line,
                    ship_qty=stock_ship_qty,
                    memo="처리계획 확정: 부족분 생산 전 기존 재고 예약",
                )

                order_line.fulfillment_mode = OrderLineFulfillmentMode.INVENTORY_FIRST.value
                order_line.production_policy = OrderLineProductionPolicy.ORDER_ONLY.value
                order_line.extra_production_qty = 0

            else:
                raise HTTPException(
                    status_code=409,
                    detail="부분재고 수주는 재고만 출고 후 종료 또는 부족분 생산 처리만 가능합니다.",
                )

    order_line.decision_made = True
    order_line.short_close_state = "CONFIRMED" if is_short_close else "NONE"
    order_line.decision_made_at = utc_now()
    order_line.decision_made_by = actor

    history = create_plan_history(
        db,
        order_line=order_line,
        plan_type=plan_type,
        ship_target_qty=ship_target_qty,
        available_inventory_qty=available_inventory_qty,
        stock_ship_qty=stock_ship_qty,
        production_qty=production_qty,
        is_short_close=is_short_close,
        memo=payload.memo,
        actor=actor,
    )

    refresh_order_line_snapshot(db, order_line.order_line_id)
    refresh_order_line_snapshots_for_product(db, order_line.product_id)

    return order_line, history, partner, product
