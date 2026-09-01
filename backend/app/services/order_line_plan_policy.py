from __future__ import annotations

from dataclasses import dataclass

from app.schemas.order_line import OrderLinePlanType


@dataclass(frozen=True)
class OrderLinePlanPolicy:
    recommended_fulfillment_mode: str
    recommended_production_qty: int
    allowed_plan_types: tuple[OrderLinePlanType, ...]


def evaluate_order_line_plan_policy(
    *,
    available_inventory_qty: int,
    target_ship_qty: int,
) -> OrderLinePlanPolicy:
    available_qty = max(int(available_inventory_qty or 0), 0)
    target_qty = max(int(target_ship_qty or 0), 0)

    if available_qty <= 0:
        return OrderLinePlanPolicy(
            recommended_fulfillment_mode="PRODUCTION_FIRST",
            recommended_production_qty=target_qty,
            allowed_plan_types=(),
        )

    if available_qty >= target_qty:
        return OrderLinePlanPolicy(
            recommended_fulfillment_mode="INVENTORY_FIRST",
            recommended_production_qty=0,
            allowed_plan_types=(
                OrderLinePlanType.STOCK_SHIP_COMPLETE,
                OrderLinePlanType.STOCK_REPLENISHMENT,
            ),
        )

    return OrderLinePlanPolicy(
        recommended_fulfillment_mode="HYBRID",
        recommended_production_qty=target_qty - available_qty,
        allowed_plan_types=(
            OrderLinePlanType.PARTIAL_STOCK_PLUS_PRODUCTION,
            OrderLinePlanType.PARTIAL_STOCK_ONLY_CLOSE,
            OrderLinePlanType.STOCK_REPLENISHMENT,
        ),
    )
