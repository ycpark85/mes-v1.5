from __future__ import annotations

from dataclasses import dataclass


class InspectionQuantityError(ValueError):
    """Raised when inspection quantities violate the allocation invariant."""


@dataclass(frozen=True)
class InspectionQuantityPlan:
    inspected_qty: int
    sellable_qty: int
    stock_ship_qty: int
    result_ship_qty: int
    stock_in_qty: int
    discard_qty: int
    uninspected_qty: int


def build_inspection_quantity_plan(
    *,
    is_partial: bool,
    good_qty: int,
    defect_ship_qty: int,
    defect_qty: int,
    stock_ship_qty: int,
    result_ship_qty: int,
    stock_in_qty: int,
    discard_qty: int,
    uninspected_qty: int,
    prior_good_qty: int,
    prior_defect_ship_qty: int,
) -> InspectionQuantityPlan:
    inspected_qty = good_qty + defect_ship_qty + defect_qty
    sellable_qty = good_qty + defect_ship_qty

    if is_partial:
        return InspectionQuantityPlan(
            inspected_qty=inspected_qty,
            sellable_qty=sellable_qty,
            stock_ship_qty=0,
            result_ship_qty=0,
            stock_in_qty=0,
            discard_qty=0,
            uninspected_qty=0,
        )

    prior_sellable_qty = prior_good_qty + prior_defect_ship_qty
    requested_sellable_qty = result_ship_qty + stock_in_qty + discard_qty
    required_sellable_qty = sellable_qty + prior_sellable_qty

    # Older clients sent only the current round quantities. Preserve that
    # contract by allocating previously inspected sellable stock to inventory.
    if prior_sellable_qty > 0 and requested_sellable_qty == sellable_qty:
        stock_in_qty += prior_sellable_qty
        requested_sellable_qty += prior_sellable_qty

    if requested_sellable_qty != required_sellable_qty:
        raise InspectionQuantityError(
            "result_ship_qty + stock_in_qty + discard_qty must equal sellable inspection qty"
        )

    return InspectionQuantityPlan(
        inspected_qty=inspected_qty,
        sellable_qty=sellable_qty,
        stock_ship_qty=stock_ship_qty,
        result_ship_qty=result_ship_qty,
        stock_in_qty=stock_in_qty,
        discard_qty=discard_qty,
        uninspected_qty=uninspected_qty,
    )
