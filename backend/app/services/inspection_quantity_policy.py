from __future__ import annotations

from dataclasses import dataclass


class InspectionQuantityError(ValueError):
    """Raised when inspection quantities violate the allocation invariant."""


@dataclass(frozen=True)
class InspectionQuantityPlan:
    inspected_qty: int
    sellable_qty: int
    settlement_sellable_qty: int
    prior_unsettled_sellable_qty: int
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
    prior_unsettled_sellable_qty: int,
) -> InspectionQuantityPlan:
    if min(good_qty, defect_ship_qty, defect_qty, stock_ship_qty, result_ship_qty,
           stock_in_qty, discard_qty, uninspected_qty, prior_unsettled_sellable_qty) < 0:
        raise InspectionQuantityError("수량은 0 이상이어야 합니다.")
    inspected_qty = good_qty + defect_ship_qty + defect_qty
    sellable_qty = good_qty + defect_ship_qty

    if is_partial:
        if uninspected_qty != 0:
            raise InspectionQuantityError(
                "uninspected_qty must be 0 when is_partial=true"
            )

    settlement_sellable_qty = sellable_qty + prior_unsettled_sellable_qty
    requested_sellable_qty = result_ship_qty + stock_in_qty + discard_qty

    if requested_sellable_qty != settlement_sellable_qty:
        raise InspectionQuantityError(
            f"생산출고 + 재고편입 + 폐기는 정산대상과 같아야 합니다. "
            f"이번 판매가능 {sellable_qty:,}, 이월 {prior_unsettled_sellable_qty:,}, "
            f"정산대상 {settlement_sellable_qty:,}, 배분 {requested_sellable_qty:,}, "
            f"차이 {settlement_sellable_qty - requested_sellable_qty:,}"
        )

    return InspectionQuantityPlan(
        inspected_qty=inspected_qty,
        sellable_qty=sellable_qty,
        settlement_sellable_qty=settlement_sellable_qty,
        prior_unsettled_sellable_qty=prior_unsettled_sellable_qty,
        stock_ship_qty=stock_ship_qty,
        result_ship_qty=result_ship_qty,
        stock_in_qty=stock_in_qty,
        discard_qty=discard_qty,
        uninspected_qty=uninspected_qty,
    )
