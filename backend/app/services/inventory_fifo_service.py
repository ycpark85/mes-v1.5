from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.product_inventory_lot import ProductInventoryLot
from app.models.shipment_line import ShipmentLine


def get_available_inventory_lots_fifo(
    db: Session,
    *,
    product_id: int,
    exclude_lot_no: str | None = None,
    exclude_inspection_result_id: int | None = None,
    for_update: bool = False,
) -> list[tuple[ProductInventoryLot, int]]:
    query = (
        select(ProductInventoryLot)
        .where(
            ProductInventoryLot.product_id == product_id,
            ProductInventoryLot.current_qty > 0,
        )
        .order_by(
            ProductInventoryLot.created_at.asc(),
            ProductInventoryLot.product_inventory_lot_id.asc(),
        )
    )

    if exclude_lot_no:
        query = query.where(ProductInventoryLot.lot_no != exclude_lot_no)

    if for_update:
        query = query.with_for_update()

    lots = db.execute(query).scalars().all()
    if not lots:
        return []

    lot_ids = [lot.product_inventory_lot_id for lot in lots]
    allocated_conditions = [
        ShipmentLine.product_inventory_lot_id.in_(lot_ids),
        ShipmentLine.source_type == "STOCK",
        ShipmentLine.status == "WAITING",
    ]

    if exclude_inspection_result_id is not None:
        allocated_conditions.append(
            (ShipmentLine.inspection_result_id.is_(None))
            | (ShipmentLine.inspection_result_id != exclude_inspection_result_id)
        )

    allocated_rows = (
        db.execute(
            select(
                ShipmentLine.product_inventory_lot_id,
                func.coalesce(func.sum(ShipmentLine.ship_qty), 0).label("allocated_qty"),
            )
            .where(*allocated_conditions)
            .group_by(ShipmentLine.product_inventory_lot_id)
        )
        .mappings()
        .all()
    )

    allocated_map = {
        int(row["product_inventory_lot_id"]): int(row["allocated_qty"] or 0)
        for row in allocated_rows
        if row["product_inventory_lot_id"] is not None
    }

    available_lots: list[tuple[ProductInventoryLot, int]] = []
    for lot in lots:
        allocated_qty = allocated_map.get(lot.product_inventory_lot_id, 0)
        available_qty = max(int(lot.current_qty or 0) - allocated_qty, 0)
        if available_qty > 0:
            available_lots.append((lot, available_qty))

    return available_lots


def allocate_inventory_lots_fifo(
    db: Session,
    *,
    product_id: int,
    ship_qty: int,
    exclude_lot_no: str | None = None,
    exclude_inspection_result_id: int | None = None,
    for_update: bool = False,
) -> tuple[list[tuple[ProductInventoryLot, int]], int]:
    if ship_qty <= 0:
        return [], 0

    remaining_qty = ship_qty
    allocations: list[tuple[ProductInventoryLot, int]] = []

    for inventory_lot, available_qty in get_available_inventory_lots_fifo(
        db,
        product_id=product_id,
        exclude_lot_no=exclude_lot_no,
        exclude_inspection_result_id=exclude_inspection_result_id,
        for_update=for_update,
    ):
        allocated_qty = min(available_qty, remaining_qty)
        if allocated_qty > 0:
            allocations.append((inventory_lot, allocated_qty))
            remaining_qty -= allocated_qty

        if remaining_qty <= 0:
            break

    return allocations, remaining_qty


def release_order_stock_reservations(db: Session, order_line) -> None:
    from app.services.inventory_lock_service import lock_product_inventory

    lock_product_inventory(db, order_line.product_id)
    lines = db.execute(select(ShipmentLine).where(
        ShipmentLine.order_line_id == order_line.order_line_id,
        ShipmentLine.source_type == "STOCK", ShipmentLine.status == "WAITING",
        ShipmentLine.inspection_result_id.is_(None),
    ).with_for_update()).scalars().all()
    for line in lines:
        line.status = "CANCELED"
        line.memo = f"{line.memo or ''} / 발주 취소·부족종결로 미사용 예약 해제"
