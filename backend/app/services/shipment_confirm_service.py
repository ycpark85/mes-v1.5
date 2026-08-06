from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.shipment_line import ShipmentLine
from app.schemas.shipment import ShipmentConfirmResult
from app.services.production_daily_query import (
    refresh_order_line_snapshot,
    refresh_order_line_snapshots_for_product,
)
from app.services.ship_qty_policy import calculate_ship_qty


def _get_ship_target_qty(db: Session, order_line: OrderLine) -> int:
    partner = db.get(Partner, order_line.partner_id)
    partner_name = partner.name if partner else ""
    return int(calculate_ship_qty(partner_name, int(order_line.order_qty or 0)) or 0)


def _get_already_shipped_qty(db: Session, order_line_id: int) -> int:
    shipped_qty = db.execute(
        select(func.coalesce(func.sum(-ProductInventoryMovement.qty), 0)).where(
            ProductInventoryMovement.order_line_id == order_line_id,
            ProductInventoryMovement.movement_type == "SHIP_OUT",
        )
    ).scalar_one()

    return int(shipped_qty or 0)


def _sync_order_line_status_after_shipment(db: Session, order_line: OrderLine) -> None:
    if order_line.status in {"CANCELED", "DONE"}:
        return

    ship_target_qty = _get_ship_target_qty(db, order_line)
    already_shipped_qty = _get_already_shipped_qty(db, order_line.order_line_id)

    if already_shipped_qty >= ship_target_qty:
        order_line.status = "DONE"


def _resolve_inventory_lot_for_shipment_line(
    db: Session,
    line: ShipmentLine,
) -> ProductInventoryLot | None:
    if line.product_inventory_lot_id:
        return (
            db.execute(
                select(ProductInventoryLot)
                .where(ProductInventoryLot.product_inventory_lot_id == line.product_inventory_lot_id)
                .with_for_update()
            )
            .scalar_one_or_none()
        )

    lot_no = line.stock_lot_no

    if not lot_no and line.lot_id:
        lot = db.get(Lot, line.lot_id)
        lot_no = lot.lot_no if lot else None

    if not lot_no:
        return None

    return (
        db.execute(
            select(ProductInventoryLot)
            .where(
                ProductInventoryLot.product_id == line.product_id,
                ProductInventoryLot.lot_no == lot_no,
            )
            .with_for_update()
        )
        .scalar_one_or_none()
    )


def confirm_shipment_lines_in_session(
    db: Session,
    shipment_line_ids: list[int],
) -> ShipmentConfirmResult:
    target_ids = sorted(set(shipment_line_ids))

    # Keep the same order-line -> shipment-line lock order used by quantity changes.
    order_line_ids = sorted(
        db.execute(
            select(ShipmentLine.order_line_id)
            .where(ShipmentLine.shipment_line_id.in_(target_ids))
            .distinct()
        )
        .scalars()
        .all()
    )
    if order_line_ids:
        db.execute(
            select(OrderLine.order_line_id)
            .where(OrderLine.order_line_id.in_(order_line_ids))
            .order_by(OrderLine.order_line_id.asc())
            .with_for_update()
        ).all()

    lines = (
        db.execute(
            select(ShipmentLine)
            .where(
                ShipmentLine.shipment_line_id.in_(target_ids),
                ShipmentLine.status == "WAITING",
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )

    if len(lines) != len(target_ids):
        raise HTTPException(status_code=409, detail="출하대기 상태가 아닌 항목이 포함되어 있습니다.")

    confirmed_ids: list[int] = []
    affected_order_line_ids: set[int] = set()
    affected_product_ids: set[int] = set()

    for line in lines:
        ship_qty = int(line.ship_qty or 0)

        if ship_qty <= 0:
            raise HTTPException(status_code=422, detail="출하수량이 0 이하인 항목은 출하할 수 없습니다.")

        inventory = (
            db.execute(
                select(ProductInventory)
                .where(ProductInventory.product_id == line.product_id)
                .with_for_update()
            )
            .scalar_one_or_none()
        )

        if inventory is None:
            inventory = ProductInventory(
                product_id=line.product_id,
                current_qty=0,
            )
            db.add(inventory)
            db.flush()

        if int(inventory.current_qty or 0) < ship_qty:
            raise HTTPException(
                status_code=409,
                detail=f"재고가 부족합니다. shipment_line_id={line.shipment_line_id}",
            )

        inventory_lot = _resolve_inventory_lot_for_shipment_line(db, line)

        if inventory_lot is not None:
            if int(inventory_lot.current_qty or 0) < ship_qty:
                raise HTTPException(
                    status_code=409,
                    detail=f"LOT 재고가 부족합니다. shipment_line_id={line.shipment_line_id}",
                )

            inventory_lot.current_qty -= ship_qty
            line.product_inventory_lot_id = inventory_lot.product_inventory_lot_id
            line.stock_lot_no = inventory_lot.lot_no

        inventory.current_qty -= ship_qty

        movement = ProductInventoryMovement(
            product_id=line.product_id,
            product_inventory_lot_id=line.product_inventory_lot_id,
            stock_lot_no=line.stock_lot_no,
            movement_type="SHIP_OUT",
            qty=-ship_qty,
            balance_after=inventory.current_qty,
            source_type="SHIPMENT_LINE",
            source_id=line.shipment_line_id,
            order_line_id=line.order_line_id,
            inspection_result_id=line.inspection_result_id,
            memo=f"출하관리 출하확정 / shipment_line_id={line.shipment_line_id}",
        )
        db.add(movement)

        line.shipped_qty = ship_qty
        line.status = "DONE"
        line.shipped_at = utc_now()

        confirmed_ids.append(line.shipment_line_id)
        affected_order_line_ids.add(line.order_line_id)
        affected_product_ids.add(line.product_id)

    for order_line_id in affected_order_line_ids:
        order_line = (
            db.execute(
                select(OrderLine)
                .where(OrderLine.order_line_id == order_line_id)
                .with_for_update()
            )
            .scalar_one_or_none()
        )

        if order_line is not None:
            _sync_order_line_status_after_shipment(db, order_line)
            refresh_order_line_snapshot(db, order_line.order_line_id)

    for product_id in affected_product_ids:
        refresh_order_line_snapshots_for_product(db, product_id)

    return ShipmentConfirmResult(
        confirmed_count=len(confirmed_ids),
        confirmed_shipment_line_ids=confirmed_ids,
    )


def confirm_shipment_lines(
    db: Session,
    shipment_line_ids: list[int],
) -> ShipmentConfirmResult:
    try:
        result = confirm_shipment_lines_in_session(db, shipment_line_ids)
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
