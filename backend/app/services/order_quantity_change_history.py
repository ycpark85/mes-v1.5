from __future__ import annotations

import re
from dataclasses import dataclass


ORDER_QUANTITY_CHANGE_PREFIX = "[ORDER_QUANTITY_CHANGED]"
_ORDER_QUANTITY_CHANGE_PATTERN = re.compile(
    r"^\[ORDER_QUANTITY_CHANGED\] "
    r"lot_id=(?P<lot_id>\d+); "
    r"order_qty=(?P<old_order_qty>\d+)->(?P<new_order_qty>\d+); "
    r"lot_qty=(?P<old_lot_qty>\d+)->(?P<new_lot_qty>\d+)$"
)
_LEGACY_ORDER_QUANTITY_CHANGE_PATTERN = re.compile(
    r"^수주수량 정정 (?P<old_order_qty>[\d,]+) -> "
    r"(?P<new_order_qty>[\d,]+); "
    r"LOT 계획수량 정정 (?P<old_lot_qty>[\d,]+) -> "
    r"(?P<new_lot_qty>[\d,]+)$"
)


@dataclass(frozen=True, slots=True)
class OrderQuantityChangeHistory:
    lot_id: int | None
    old_order_qty: int
    new_order_qty: int
    old_lot_qty: int
    new_lot_qty: int


def build_order_quantity_change_memo(
    *,
    lot_id: int,
    old_order_qty: int,
    new_order_qty: int,
    old_lot_qty: int,
    new_lot_qty: int,
) -> str:
    return (
        f"{ORDER_QUANTITY_CHANGE_PREFIX} "
        f"lot_id={lot_id}; "
        f"order_qty={old_order_qty}->{new_order_qty}; "
        f"lot_qty={old_lot_qty}->{new_lot_qty}"
    )


def parse_order_quantity_change_memo(
    memo: str | None,
) -> OrderQuantityChangeHistory | None:
    if not memo:
        return None

    normalized_memo = memo.strip()
    match = _ORDER_QUANTITY_CHANGE_PATTERN.fullmatch(normalized_memo)
    is_legacy = False
    if match is None:
        match = _LEGACY_ORDER_QUANTITY_CHANGE_PATTERN.fullmatch(normalized_memo)
        is_legacy = match is not None
    if match is None:
        return None

    lot_id = None if is_legacy else int(match.group("lot_id"))
    old_order_qty = _parse_quantity(match.group("old_order_qty"))
    new_order_qty = _parse_quantity(match.group("new_order_qty"))
    old_lot_qty = _parse_quantity(match.group("old_lot_qty"))
    new_lot_qty = _parse_quantity(match.group("new_lot_qty"))
    if any(
        value <= 0
        for value in (
            old_order_qty,
            new_order_qty,
            old_lot_qty,
            new_lot_qty,
        )
    ) or (lot_id is not None and lot_id <= 0):
        return None

    return OrderQuantityChangeHistory(
        lot_id=lot_id,
        old_order_qty=old_order_qty,
        new_order_qty=new_order_qty,
        old_lot_qty=old_lot_qty,
        new_lot_qty=new_lot_qty,
    )


def _parse_quantity(value: str) -> int:
    return int(value.replace(",", ""))
