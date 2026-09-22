from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.time import utc_now
from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.shipment_line import ShipmentLine
from app.services.inspection_stock_service import get_inspection_stock_context
from app.services.inspection_result_history_service import ensure_no_issued_documents
from app.services.inspection_inventory_policy import (
    InspectionInventoryPlanError, ShipmentAllocation, build_inventory_delta,
    inventory_lot_deltas, plan_shipment_changes,
)

def apply_inventory_for_result(
    db: Session, *, result: InspectionResult, schedule: InspectionSchedule,
    stock_ship_qty: int, result_ship_qty: int, stock_in_qty: int,
) -> None:
    lot = db.get(Lot, schedule.lot_id)
    order = db.get(OrderLine, lot.order_line_id)
    inventory = db.execute(select(ProductInventory).where(
        ProductInventory.product_id == lot.product_id,
    )).scalar_one()
    result_id = result.inspection_result_id
    existing = db.execute(select(ShipmentLine).where(
        ShipmentLine.inspection_result_id == result_id, ShipmentLine.status == "DONE",
    ).order_by(ShipmentLine.shipment_line_id)).scalars().all()
    old_in = int(db.execute(select(func.coalesce(func.sum(ProductInventoryMovement.qty), 0)).where(
        ProductInventoryMovement.inspection_result_id == result_id,
        ProductInventoryMovement.movement_type == "INSPECTION_IN",
    )).scalar_one())
    old_stock = sum(int(line.shipped_qty) for line in existing if line.source_type == "STOCK")
    old_production = sum(int(line.shipped_qty) for line in existing if line.source_type == "INSPECTION_RESULT")
    posted_shipment = int(db.execute(select(func.coalesce(func.sum(-ProductInventoryMovement.qty), 0)).where(
        ProductInventoryMovement.inspection_result_id == result_id,
        ProductInventoryMovement.movement_type == "SHIP_OUT",
    )).scalar_one())
    try:
        delta = build_inventory_delta(stock_ship_qty=stock_ship_qty, result_ship_qty=result_ship_qty,
            stock_in_qty=stock_in_qty, previous_inventory_in=old_in, previous_stock_ship=old_stock,
            previous_production_ship=old_production, posted_shipment=posted_shipment)
    except InspectionInventoryPlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Metadata and equal-value saves preserve inventory, allocation IDs, and movement timestamps.
    if not delta.has_changes:
        if result.settled_at is None and not result.is_partial:
            other_active_lot = db.execute(select(Lot.lot_id).where(
                Lot.order_line_id == order.order_line_id, Lot.lot_id != lot.lot_id,
                Lot.status.not_in(("DONE", "CANCELED")),
            ).limit(1)).scalar_one_or_none()
            if other_active_lot is None:
                from app.services.inventory_fifo_service import release_order_stock_reservations
                release_order_stock_reservations(db, order)
        return
    if result.settled_at is not None:
        ensure_no_issued_documents(db, result_id, order.order_line_id)

    stock = get_inspection_stock_context(db, product_id=lot.product_id,
        order_line_id=order.order_line_id, result_id=result_id if existing or old_in else None)
    if stock.error:
        raise HTTPException(status_code=409, detail="재고 정합성 확인 필요: " + stock.error)
    if delta.stock_ship > 0 and stock_ship_qty > stock.available_qty:
        raise HTTPException(status_code=422, detail=f"재고 출고수량이 사용 가능량 {stock.available_qty:,}를 초과합니다.")

    inventory_lots = {row.lot.product_inventory_lot_id: row.lot for row in stock.lots}
    production_lot = db.execute(select(ProductInventoryLot).where(
        ProductInventoryLot.product_id == lot.product_id, ProductInventoryLot.lot_no == lot.lot_no,
    )).scalar_one_or_none()
    if production_lot is None:
        production_lot = ProductInventoryLot(product_id=lot.product_id, lot_no=lot.lot_no, current_qty=0)
        db.add(production_lot)
        db.flush()
    inventory_lots[production_lot.product_inventory_lot_id] = production_lot

    waiting = db.execute(select(ShipmentLine).where(
        ShipmentLine.order_line_id == order.order_line_id, ShipmentLine.product_id == lot.product_id,
        ShipmentLine.source_type == "STOCK", ShipmentLine.status == "WAITING",
        ShipmentLine.inspection_result_id.is_(None),
    ).order_by(ShipmentLine.shipment_line_id).with_for_update()).scalars().all()
    try:
        changes = plan_shipment_changes(delta=delta,
            existing=[ShipmentAllocation(line.shipment_line_id, line.product_inventory_lot_id,
                line.source_type, int(line.shipped_qty)) for line in existing],
            waiting=[ShipmentAllocation(line.shipment_line_id, line.product_inventory_lot_id,
                line.source_type, int(line.ship_qty)) for line in waiting],
            available_stock=[(row.lot.product_inventory_lot_id, max(row.stock_qty - row.current_shipped_qty, 0))
                for row in stock.lots], production_lot_id=production_lot.product_inventory_lot_id)
    except InspectionInventoryPlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    lines_by_id = {line.shipment_line_id: line for line in [*existing, *waiting]}
    actions: list[tuple[ShipmentLine, int]] = []
    for change in changes:
        line = lines_by_id.get(change.line_id)
        if line is None:
            line = ShipmentLine(order_line_id=order.order_line_id, product_id=lot.product_id,
                product_inventory_lot_id=change.inventory_lot_id,
                stock_lot_no=inventory_lots[change.inventory_lot_id].lot_no,
                lot_id=lot.lot_id if change.source == "INSPECTION_RESULT" else None,
                inspection_result_id=result_id, source_type=change.source,
                status="DONE", ship_qty=0, shipped_qty=0)
        actions.append((line, change.qty))

    release_reservations = not result.is_partial and db.execute(select(Lot.lot_id).where(
        Lot.order_line_id == order.order_line_id, Lot.lot_id != lot.lot_id,
        Lot.status.not_in(("DONE", "CANCELED")),
    ).limit(1)).scalar_one_or_none() is None
    deltas = inventory_lot_deltas(production_lot.product_inventory_lot_id, delta, changes)
    for line, _ in actions:
        key = line.product_inventory_lot_id
        if key not in inventory_lots:
            inventory_lots[key] = db.get(ProductInventoryLot, key)
        if inventory_lots.get(key) is None:
            raise HTTPException(status_code=409, detail="출고 원본 LOT 연결을 확인해야 합니다.")
    if int(inventory.current_qty) + sum(deltas.values()) < 0:
        raise HTTPException(status_code=409, detail="이미 사용한 재고를 줄일 수 없습니다.")
    for key, quantity_delta in deltas.items():
        reserved = int(db.execute(select(func.coalesce(func.sum(ShipmentLine.ship_qty), 0)).where(
            ShipmentLine.product_inventory_lot_id == key, ShipmentLine.source_type == "STOCK",
            ShipmentLine.status == "WAITING",
        )).scalar_one())
        reserved -= sum(qty for line, qty in actions if line.status == "WAITING" and line.product_inventory_lot_id == key)
        if release_reservations:
            reserved -= sum(int(line.ship_qty) - next((qty for action, qty in actions if action is line), 0)
                            for line in waiting if line.product_inventory_lot_id == key)
        if int(inventory_lots[key].current_qty) + quantity_delta < max(reserved, 0):
            raise HTTPException(status_code=409, detail="이미 출고되었거나 다른 발주가 예약한 LOT 재고를 줄일 수 없습니다.")

    _post_inventory_movements(db, result=result, schedule=schedule, lot=lot, order=order,
        inventory=inventory, production_lot=production_lot, inventory_lots=inventory_lots,
        delta_in=delta.inventory_in, actions=actions, waiting=waiting, release_reservations=release_reservations)


def _post_inventory_movements(
    db: Session, *, result: InspectionResult, schedule: InspectionSchedule, lot: Lot, order: OrderLine,
    inventory: ProductInventory, production_lot: ProductInventoryLot,
    inventory_lots: dict[int, ProductInventoryLot], delta_in: int,
    actions: list[tuple[ShipmentLine, int]], waiting: list[ShipmentLine], release_reservations: bool,
) -> None:
    """Apply the already validated changes in the caller's transaction; never commit here."""
    result_id = result.inspection_result_id
    movements: list[tuple[ProductInventoryLot, int, str, ShipmentLine | None]] = []
    if delta_in:
        movements.append((production_lot, delta_in, "INSPECTION_IN", None))
    for line, qty in actions:
        if line.source_type == "STOCK" and line.lot_id is None:
            line.lot_id = db.execute(select(Lot.lot_id).where(
                Lot.product_id == lot.product_id, Lot.lot_no == line.stock_lot_no,
            ).limit(1)).scalar_one_or_none()
        if line.status == "WAITING":
            unused = int(line.ship_qty) - qty
            if unused and not release_reservations:
                db.add(ShipmentLine(order_line_id=line.order_line_id, product_id=line.product_id,
                    product_inventory_lot_id=line.product_inventory_lot_id, stock_lot_no=line.stock_lot_no,
                    source_type="STOCK", status="WAITING", ship_qty=unused, shipped_qty=0,
                    memo="검수 후 잔여 예약 유지"))
            line.ship_qty = line.shipped_qty = qty
            line.inspection_result_id = result_id
            line.status = "DONE"
        else:
            line.ship_qty = int(line.ship_qty) + qty
            line.shipped_qty = int(line.shipped_qty) + qty
            if line.shipped_qty == 0:
                line.status = "CANCELED"
        if line.shipped_at is None:
            line.shipped_at = utc_now()
        db.add(line)
        movements.append((inventory_lots[line.product_inventory_lot_id], -qty, "SHIP_OUT", line))
    if release_reservations:
        for line in waiting:
            if line.status == "WAITING":
                line.status = "CANCELED"
                line.memo = f"{line.memo or ''} / 최종검수 미사용 예약 해제"
    db.flush()
    # Credits before debits avoid transient negative balances during a valid correction.
    movements.sort(key=lambda item: item[1] < 0)
    for stock_lot, qty, movement_type, line in movements:
        inventory.current_qty += qty
        stock_lot.current_qty += qty
        db.add(ProductInventoryMovement(product_id=lot.product_id,
            product_inventory_lot_id=stock_lot.product_inventory_lot_id, stock_lot_no=stock_lot.lot_no,
            movement_type=movement_type, qty=qty, balance_after=inventory.current_qty,
            source_type="SHIPMENT_LINE" if line is not None else "INSPECTION_RESULT_IN",
            source_id=line.shipment_line_id if line is not None else result_id,
            order_line_id=order.order_line_id, inspection_schedule_id=schedule.inspection_schedule_id,
            inspection_result_id=result_id, memo="검수 정산" if result.settled_at is None else "검수실적 수정 차이 반영"))
    db.flush()
