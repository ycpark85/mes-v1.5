from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.services.inventory_lock_service import lock_product_inventory
from app.services.inventory_fifo_service import get_available_inventory_lots_fifo
from app.schemas.inventory import ProductInventoryAdjustmentIn, ProductInventoryMovementOut


@dataclass(frozen=True)
class ProductInventoryAdjustmentResult:
    product: Product
    movement: ProductInventoryMovement


def adjust_product_inventory_in_session(
    db: Session,
    *,
    product_id: int,
    payload: ProductInventoryAdjustmentIn,
    direction: str,
) -> ProductInventoryAdjustmentResult:
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found")

    normalized_direction = direction.strip().upper()
    if normalized_direction not in {"IN", "OUT"}:
        raise HTTPException(status_code=422, detail="direction must be IN or OUT")

    if not payload.memo or not payload.memo.strip() or len(payload.memo) > 1000:
        raise HTTPException(status_code=422, detail="재고 조정 사유를 1~1000자로 입력해야 합니다.")

    inventory = lock_product_inventory(db, product_id)

    if payload.product_inventory_lot_id is not None:
        lot = db.get(ProductInventoryLot, payload.product_inventory_lot_id)
        if lot is None or lot.product_id != product_id:
            raise HTTPException(status_code=404, detail="선택한 품목의 재고 LOT를 찾을 수 없습니다.")

    movements: list[ProductInventoryMovement] = []

    if normalized_direction == "IN":
        movements.append(_adjust_inventory_in(db, product_id, payload, inventory))
    else:
        movements.extend(_adjust_inventory_out(db, product_id, payload, inventory))

    for movement in movements:
        db.add(movement)

    db.flush()

    return ProductInventoryAdjustmentResult(product=product, movement=movements[-1])


def build_product_inventory_movement_out(
    *,
    movement: ProductInventoryMovement,
    product: Product,
) -> ProductInventoryMovementOut:
    return ProductInventoryMovementOut(
        inventory_movement_id=movement.inventory_movement_id,
        product_id=movement.product_id,
        product_inventory_lot_id=movement.product_inventory_lot_id,
        stock_lot_no=movement.stock_lot_no,
        product_code=product.product_code,
        product_name=product.product_name,
        movement_type=movement.movement_type,
        qty=movement.qty,
        balance_after=movement.balance_after,
        source_type=movement.source_type,
        source_id=movement.source_id,
        order_line_id=movement.order_line_id,
        inspection_schedule_id=movement.inspection_schedule_id,
        inspection_result_id=movement.inspection_result_id,
        memo=movement.memo,
        created_at=movement.created_at,
    )


def _adjust_inventory_in(
    db: Session,
    product_id: int,
    payload: ProductInventoryAdjustmentIn,
    inventory: ProductInventory,
) -> ProductInventoryMovement:
    lot_no = (payload.stock_lot_no or "").strip().upper()
    if not lot_no and payload.product_inventory_lot_id is None:
        raise HTTPException(status_code=422, detail="재고증가 시 조정 LOT 번호를 입력해야 합니다.")

    lot_condition = (ProductInventoryLot.product_inventory_lot_id == payload.product_inventory_lot_id
                     if payload.product_inventory_lot_id is not None else func.upper(ProductInventoryLot.lot_no) == lot_no)
    inventory_lot = (
        db.execute(
            select(ProductInventoryLot)
            .where(
                ProductInventoryLot.product_id == product_id,
                lot_condition,
            )
            .with_for_update()
        )
        .scalar_one_or_none()
    )

    if inventory_lot is None:
        inventory_lot = ProductInventoryLot(
            product_id=product_id,
            lot_no=lot_no,
            current_qty=0,
        )
        db.add(inventory_lot)
        db.flush()

    inventory.current_qty = int(inventory.current_qty or 0) + payload.qty
    inventory_lot.current_qty = int(inventory_lot.current_qty or 0) + payload.qty

    return ProductInventoryMovement(
        product_id=product_id,
        product_inventory_lot_id=inventory_lot.product_inventory_lot_id,
        stock_lot_no=inventory_lot.lot_no,
        movement_type="ADJUST_IN",
        qty=payload.qty,
        balance_after=inventory.current_qty,
        source_type="MANUAL_ADJUST",
        source_id=None,
        memo=payload.memo,
    )


def _adjust_inventory_out(
    db: Session,
    product_id: int,
    payload: ProductInventoryAdjustmentIn,
    inventory: ProductInventory,
) -> list[ProductInventoryMovement]:
    current_qty = int(inventory.current_qty or 0)
    if current_qty < payload.qty:
        raise HTTPException(
            status_code=409,
            detail=f"재고감소 수량이 현재 재고보다 큽니다. 현재고={current_qty}",
        )

    inventory_lots = get_available_inventory_lots_fifo(db, product_id=product_id, for_update=True)
    if payload.product_inventory_lot_id is not None:
        inventory_lots = [(lot, qty) for lot, qty in inventory_lots
                          if lot.product_inventory_lot_id == payload.product_inventory_lot_id]
    if sum(qty for _, qty in inventory_lots) < payload.qty:
        raise HTTPException(status_code=409,
            detail="미예약 LOT 재고가 부족합니다. 예약 물량의 실사 차이는 해당 발주의 예약 정리 후 조정하세요.")

    remaining_qty = payload.qty
    movements: list[ProductInventoryMovement] = []

    for inventory_lot, available_qty in inventory_lots:
        if remaining_qty <= 0:
            break

        lot_qty = int(inventory_lot.current_qty or 0)
        adjust_qty = min(available_qty, remaining_qty)
        if adjust_qty <= 0:
            continue

        inventory.current_qty = int(inventory.current_qty or 0) - adjust_qty
        inventory_lot.current_qty = lot_qty - adjust_qty
        remaining_qty -= adjust_qty

        movements.append(
            ProductInventoryMovement(
                product_id=product_id,
                product_inventory_lot_id=inventory_lot.product_inventory_lot_id,
                stock_lot_no=inventory_lot.lot_no,
                movement_type="ADJUST_OUT",
                qty=-adjust_qty,
                balance_after=inventory.current_qty,
                source_type="MANUAL_ADJUST",
                source_id=None,
                memo=payload.memo,
            )
        )

    if remaining_qty > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "LOT별 재고가 부족하여 재고감소를 처리할 수 없습니다. "
                "재고 정합성 점검 후 보정이 필요합니다."
            ),
        )

    return movements
