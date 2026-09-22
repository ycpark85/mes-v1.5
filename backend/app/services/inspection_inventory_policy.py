"""Pure settlement changes. Inputs are snapshots; planning never edits ORM rows."""
from dataclasses import dataclass
from typing import Sequence


class InspectionInventoryPlanError(ValueError):
    pass


@dataclass(frozen=True)
class InspectionInventoryDelta:
    inventory_in: int
    stock_ship: int
    production_ship: int

    @property
    def has_changes(self) -> bool:
        return any((self.inventory_in, self.stock_ship, self.production_ship))


@dataclass(frozen=True)
class ShipmentAllocation:
    line_id: int
    inventory_lot_id: int
    source: str
    qty: int


@dataclass(frozen=True)
class ShipmentChange:
    line_id: int | None
    inventory_lot_id: int
    source: str
    qty: int


def build_inventory_delta(*, stock_ship_qty: int, result_ship_qty: int, stock_in_qty: int,
                          previous_inventory_in: int, previous_stock_ship: int,
                          previous_production_ship: int, posted_shipment: int) -> InspectionInventoryDelta:
    if posted_shipment != previous_stock_ship + previous_production_ship:
        raise InspectionInventoryPlanError("기존 출고 원장과 출고 실적이 다릅니다. 정산 자료를 점검하세요.")
    return InspectionInventoryDelta(
        inventory_in=result_ship_qty + stock_in_qty - previous_inventory_in,
        stock_ship=stock_ship_qty - previous_stock_ship,
        production_ship=result_ship_qty - previous_production_ship,
    )


def plan_shipment_changes(*, delta: InspectionInventoryDelta,
                          existing: Sequence[ShipmentAllocation], waiting: Sequence[ShipmentAllocation],
                          available_stock: Sequence[tuple[int, int]], production_lot_id: int) -> tuple[ShipmentChange, ...]:
    """Reverse latest shipments first; consume own reservations before FIFO stock.

    Existing and waiting allocations arrive in ascending shipment ID order.
    Available stock arrives in the established FIFO order, excluding other reservations.
    """
    changes = []
    for source, difference in (("STOCK", delta.stock_ship), ("INSPECTION_RESULT", delta.production_ship)):
        if difference >= 0:
            continue
        remaining = -difference
        for line in reversed(existing):
            if line.source != source:
                continue
            qty = min(line.qty, remaining)
            if qty:
                changes.append(ShipmentChange(line.line_id, line.inventory_lot_id, source, -qty))
                remaining -= qty
        if remaining:
            raise InspectionInventoryPlanError("기존 출고 배정과 수량이 일치하지 않습니다.")

    remaining = max(delta.stock_ship, 0)
    limits = {lot_id: max(qty, 0) for lot_id, qty in available_stock}
    for line in waiting:
        qty = min(line.qty, remaining, limits.get(line.inventory_lot_id, 0))
        if qty:
            changes.append(ShipmentChange(line.line_id, line.inventory_lot_id, "STOCK", qty))
            remaining -= qty
            limits[line.inventory_lot_id] -= qty
    for lot_id, _ in available_stock:
        qty = min(remaining, limits[lot_id])
        if qty:
            changes.append(ShipmentChange(None, lot_id, "STOCK", qty))
            remaining -= qty
    if remaining:
        raise InspectionInventoryPlanError("사용 가능한 FIFO LOT 재고가 부족합니다.")
    if delta.production_ship > 0:
        changes.append(ShipmentChange(None, production_lot_id, "INSPECTION_RESULT", delta.production_ship))
    return tuple(changes)


def inventory_lot_deltas(production_lot_id: int, delta: InspectionInventoryDelta,
                         changes: Sequence[ShipmentChange]) -> dict[int, int]:
    result = {production_lot_id: delta.inventory_in}
    for change in changes:
        result[change.inventory_lot_id] = result.get(change.inventory_lot_id, 0) - change.qty
    return result
