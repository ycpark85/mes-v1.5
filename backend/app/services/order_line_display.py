from __future__ import annotations

from app.models.order_line import OrderLine
from app.models.product import Product


def order_product_code(order_line: OrderLine | None, product: Product | None) -> str:
    """Use the order's immutable business code; never guess from today's mappings."""
    return (order_line.source_erp_product_code if order_line else None) or (product.product_code if product else "")


def order_product_name(order_line: OrderLine | None, product: Product | None) -> str:
    return (order_line.source_product_name if order_line else None) or (product.product_name if product else "")


def order_product_spec(order_line: OrderLine | None, product: Product | None) -> str | None:
    # A missing specification in a saved order is not today's master specification.
    if order_line and order_line.source_erp_product_code is not None:
        return order_line.source_product_spec
    return product.product_spec if product else None


def to_plan_type_display(plan_type: str | None) -> str | None:
    if not plan_type:
        return None

    mapping = {
        "AUTO_PRODUCTION": "자동 생산",
        "AUTO_STOCK_SHIP": "재고 출고",
        "STOCK_SHIP_COMPLETE": "재고 출고완료",
        "PARTIAL_STOCK_ONLY_CLOSE": "재고만 출고 후 종료",
        "PARTIAL_STOCK_PLUS_PRODUCTION": "부분재고 + 부족분 생산",
        "STOCK_REPLENISHMENT": "발주수량 전체 재고생산",
    }

    return mapping.get(plan_type, plan_type)
