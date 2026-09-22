from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.shipment_line import ShipmentLine


@dataclass(frozen=True)
class InspectionStockLot:
    lot: ProductInventoryLot
    stock_qty: int
    reserved_qty: int
    other_reserved_qty: int
    current_shipped_qty: int


@dataclass(frozen=True)
class InspectionStockContext:
    lots: list[InspectionStockLot]
    physical_qty: int
    available_qty: int
    reserved_qty: int
    error: str | None


def get_inspection_stock_context(
    db: Session, *, product_id: int, order_line_id: int, result_id: int | None = None,
) -> InspectionStockContext:
    """One order/LOT basis for summary, detail and stock-shipment validation."""
    lots = db.execute(select(ProductInventoryLot).where(
        ProductInventoryLot.product_id == product_id,
    ).order_by(ProductInventoryLot.created_at, ProductInventoryLot.product_inventory_lot_id)).scalars().all()
    physical_qty = int(db.execute(select(ProductInventory.current_qty).where(
        ProductInventory.product_id == product_id,
    )).scalar_one_or_none() or 0)
    reservations = db.execute(select(ShipmentLine).where(
        ShipmentLine.product_id == product_id, ShipmentLine.source_type == "STOCK",
        ShipmentLine.status == "WAITING",
    )).scalars().all()
    movements = [] if result_id is None else db.execute(select(ProductInventoryMovement).where(
        ProductInventoryMovement.inspection_result_id == result_id,
        ProductInventoryMovement.movement_type.in_(("INSPECTION_IN", "SHIP_OUT")),
    )).scalars().all()
    current_lines = [] if result_id is None else db.execute(select(ShipmentLine).where(
        ShipmentLine.inspection_result_id == result_id, ShipmentLine.source_type == "STOCK",
        ShipmentLine.status == "DONE",
    )).scalars().all()
    own_reserved = defaultdict(int)
    other_reserved = defaultdict(int)
    movement_qty = defaultdict(int)
    shipped_qty = defaultdict(int)
    for line in reservations:
        quantities = own_reserved if line.order_line_id == order_line_id else other_reserved
        quantities[line.product_inventory_lot_id] += int(line.ship_qty)
    for movement in movements:
        movement_qty[movement.product_inventory_lot_id] += int(movement.qty)
    for line in current_lines:
        shipped_qty[line.product_inventory_lot_id] += int(line.shipped_qty)

    issues: list[str] = []
    lot_total = sum(int(lot.current_qty) for lot in lots)
    if physical_qty != lot_total:
        issues.append(f"전체재고 {physical_qty:,}와 LOT 합계 {lot_total:,}가 다릅니다")
    lot_ids = {lot.product_inventory_lot_id for lot in lots}
    if any(line.product_inventory_lot_id not in lot_ids for line in reservations):
        issues.append("재고 LOT에 연결되지 않은 예약이 있습니다")
    rows = []
    for lot in lots:
        lot_id = lot.product_inventory_lot_id
        own = own_reserved[lot_id]
        other = other_reserved[lot_id]
        if lot.current_qty < 0 or own + other > lot.current_qty:
            issues.append(f"{lot.lot_no}: 재고 {lot.current_qty:,}, 자기예약 {own:,}, 다른예약 {other:,}")
        # Remove only this result's posted effect; previous rounds on the same LOT remain usable.
        basis = int(lot.current_qty) - movement_qty[lot_id]
        shipped = shipped_qty[lot_id]
        available = max(basis - other, 0)
        if lot.current_qty or own or other or available or shipped:
            rows.append(InspectionStockLot(lot, available, own, other, shipped))
    # Match saving: retain an edit's existing allocation, then use own reservation, then free FIFO.
    rows.sort(key=lambda row: (not bool(row.current_shipped_qty), not bool(row.reserved_qty)))
    basis_total = max(physical_qty - sum(movement_qty.values()), 0)
    remaining = basis_total
    capped_rows = []
    for row in rows:
        qty = min(row.stock_qty, remaining)
        capped_rows.append(InspectionStockLot(row.lot, qty, row.reserved_qty,
                                             row.other_reserved_qty, row.current_shipped_qty))
        remaining -= qty
    return InspectionStockContext(capped_rows, physical_qty,
                                  sum(row.stock_qty for row in capped_rows),
                                  sum(row.reserved_qty for row in capped_rows),
                                  " / ".join(issues) or None)
