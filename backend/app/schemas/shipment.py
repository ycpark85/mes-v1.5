from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ShipmentLineOut(BaseModel):
    shipment_line_id: int

    order_line_id: int
    order_no: str
    partner_name: Optional[str] = None

    product_id: int
    product_code: Optional[str] = None
    mes_product_code: str | None = None
    product_name: Optional[str] = None

    product_inventory_lot_id: Optional[int] = None
    stock_lot_no: Optional[str] = None
    lot_id: Optional[int] = None
    lot_no: Optional[str] = None
    inspection_result_id: Optional[int] = None

    source_type: str
    status: str

    ship_qty: int
    shipped_qty: int

    current_stock_qty: int = 0
    stock_after_ship_qty: int = 0

    ship_target_qty: int = 0
    already_shipped_qty: int = 0
    remaining_ship_qty: int = 0

    memo: Optional[str] = None
    created_at: datetime
    shipped_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ShipmentLineListOut(BaseModel):
    items: List[ShipmentLineOut]
    total: int
    page: int
    size: int


class ShipmentConfirmRequest(BaseModel):
    shipment_line_ids: List[int] = Field(..., min_length=1)


class ShipmentConfirmResult(BaseModel):
    confirmed_count: int
    confirmed_shipment_line_ids: List[int]
