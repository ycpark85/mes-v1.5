from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class OrderLineDetailLotDto(BaseModel):
    lot_id: int
    lot_no: str
    lot_type: str  # NORMAL / REWORK
    parent_lot_id: Optional[int] = None

    lot_qty: int
    status: str
    current_process_name: Optional[str] = None

    is_editable: bool = False
    can_cancel: bool = False
    can_create_rework: bool = False


class OrderLineTimelineItemDto(BaseModel):
    event_type: str
    event_label: str
    event_at: datetime
    message: str

    ref_type: Optional[str] = None   # ORDER_LINE / LOT / INSPECTION
    ref_id: Optional[int] = None


class OrderLineDetailDto(BaseModel):
    order_line_id: int
    order_no: str
    line_no: int

    partner_id: int
    partner_name: str

    product_id: int
    source_erp_product_code: Optional[str] = None
    source_product_name: Optional[str] = None
    source_product_spec: Optional[str] = None
    product_code: str
    mes_product_code: str | None = None
    product_name: str

    order_date: date
    due_date: date
    order_qty: int
    uom: str

    customer_po: Optional[str] = None
    memo: Optional[str] = None

    status: str
    status_display: str
    is_active: bool

    can_edit: bool = False
    can_save: bool = False
    can_cancel_order: bool = False
    can_create_base_lot: bool = False

    lots: List[OrderLineDetailLotDto] = Field(default_factory=list)
    timeline: List[OrderLineTimelineItemDto] = Field(default_factory=list)


class OrderLineDetailUpdate(BaseModel):
    due_date: date
    order_qty: int
    memo: Optional[str] = None