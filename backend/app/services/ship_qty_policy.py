import math
import re
from dataclasses import dataclass


DIRECT_SHIP_KEYWORDS = (
    "덴티움",
    "오스템임플란트",
    "네오바이오텍",
    "제이시스메디칼",
)

CAREGEN_KEYWORD = "케어젠"

STOCK_REPLENISHMENT_PARTNER_NAME = "세미산업"
STOCK_REPLENISHMENT_BUSINESS_NO = "1390178012"


@dataclass(frozen=True)
class ShipmentProgress:
    ship_target_qty: int
    prior_shipped_qty: int
    current_result_shipped_qty: int
    total_shipped_qty: int
    remaining_before_current_result_qty: int
    remaining_after_current_result_qty: int


def normalize_partner_name(name: str) -> str:
    if not name:
        return ""

    normalized = name.strip()
    normalized = normalized.replace("주식회사", "")
    normalized = normalized.replace("(주)", "")
    normalized = normalized.replace("㈜", "")
    normalized = re.sub(r"\s+", "", normalized)

    return normalized


def normalize_business_no(business_no: str | None) -> str:
    if not business_no:
        return ""

    return re.sub(r"[^0-9]", "", business_no)


def is_stock_replenishment_partner(
    partner_name: str | None,
    business_no: str | None,
) -> bool:
    normalized_name = normalize_partner_name(partner_name or "")
    normalized_business_no = normalize_business_no(business_no)

    return (
        normalized_name == STOCK_REPLENISHMENT_PARTNER_NAME
        and normalized_business_no == STOCK_REPLENISHMENT_BUSINESS_NO
    )


def calculate_ship_qty(partner_name: str, order_qty: int) -> int:
    normalized_name = normalize_partner_name(partner_name)

    if any(keyword in normalized_name for keyword in DIRECT_SHIP_KEYWORDS):
        return order_qty

    if CAREGEN_KEYWORD in normalized_name:
        return order_qty + 100

    return math.ceil(order_qty * 1.02)


def ship_target_sql(partner_name, order_qty):
    """Read-only SQL equivalent of calculate_ship_qty, for filtering before pagination."""
    from sqlalchemy import Float, Integer, case, cast, func, or_

    normalized = func.coalesce(partner_name, "")
    for token in ("주식회사", "(주)", "㈜"):
        normalized = func.replace(normalized, token, "")
    for token in "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000":
        normalized = func.replace(normalized, token, "")
    return case(
        (or_(*(normalized.contains(keyword) for keyword in DIRECT_SHIP_KEYWORDS)), order_qty),
        (normalized.contains(CAREGEN_KEYWORD), order_qty + 100),
        else_=cast(func.ceil(cast(order_qty, Float) * 1.02), Integer),
    )


def build_shipment_progress(
    *,
    ship_target_qty: int,
    total_shipped_qty: int,
    current_result_shipped_qty: int,
) -> ShipmentProgress:
    target_qty = max(int(ship_target_qty or 0), 0)
    total_qty = max(int(total_shipped_qty or 0), 0)
    current_qty = min(
        max(int(current_result_shipped_qty or 0), 0),
        total_qty,
    )
    prior_qty = total_qty - current_qty

    return ShipmentProgress(
        ship_target_qty=target_qty,
        prior_shipped_qty=prior_qty,
        current_result_shipped_qty=current_qty,
        total_shipped_qty=total_qty,
        remaining_before_current_result_qty=max(target_qty - prior_qty, 0),
        remaining_after_current_result_qty=max(target_qty - total_qty, 0),
    )
