from __future__ import annotations


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
