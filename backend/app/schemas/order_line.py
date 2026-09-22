# app/schemas/order_line.py
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional, List, Literal

from pydantic import BaseModel, ConfigDict, Field


class OrderLineStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    DONE = "DONE"
    CANCELED = "CANCELED"

class OrderLinePlanType(str, Enum):
    AUTO_PRODUCTION = "AUTO_PRODUCTION"
    AUTO_STOCK_SHIP = "AUTO_STOCK_SHIP"
    STOCK_SHIP_COMPLETE = "STOCK_SHIP_COMPLETE"
    PARTIAL_STOCK_ONLY_CLOSE = "PARTIAL_STOCK_ONLY_CLOSE"
    PARTIAL_STOCK_PLUS_PRODUCTION = "PARTIAL_STOCK_PLUS_PRODUCTION"
    STOCK_REPLENISHMENT = "STOCK_REPLENISHMENT"


class OrderLineBase(BaseModel):
    order_no: str = Field(..., max_length=40)
    line_no: int = Field(..., gt=0)

    partner_id: int
    product_id: int

    order_date: date
    due_date: date

    order_qty: int = Field(..., gt=0)
    uom: str = Field(..., max_length=10)

    customer_po: Optional[str] = Field(None, max_length=60)
    memo: Optional[str] = None


class OrderLineCreate(OrderLineBase):
    # status/is_active/priority는 서버 기본값 사용(입력 받지 않음)
    pass


class OrderLineUpdate(BaseModel):
    # OPEN일 때만 주요 필드 수정 허용 (검증은 router에서)
    order_no: Optional[str] = Field(None, max_length=40)
    line_no: Optional[int] = Field(None, gt=0)

    partner_id: Optional[int] = None
    product_id: Optional[int] = None

    order_date: Optional[date] = None
    due_date: Optional[date] = None

    order_qty: Optional[int] = Field(None, gt=0)
    uom: Optional[str] = Field(None, max_length=10)

    customer_po: Optional[str] = Field(None, max_length=60)
    memo: Optional[str] = None

    # 운영상 OPEN 이후에도 메모/PO는 변경 허용하고 싶으면 그대로 두고 router에서 허용 처리
    priority: Optional[int] = None  # 필요 시 허용 (기본은 OPEN에서만)


class OrderLineOut(OrderLineBase):
    model_config = ConfigDict(from_attributes=True)

    order_line_id: int
    status: OrderLineStatus
    is_active: bool
    priority: int
    created_at: datetime
    updated_at: datetime

        # join으로 붙여주는 표시용 필드(조회 성능/UX)
    partner_name: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    drawing_no: Optional[str] = None

    # OrderLineList 액션 버튼 분기용
    has_lot: bool = False
    lot_count: int = 0

    target_ship_qty: int = 0
    expected_ship_qty: int = 0
    expected_short_qty: int = 0
    
    fulfillment_mode: Optional[OrderLineFulfillmentMode] = None
    production_policy: Optional[OrderLineProductionPolicy] = None
    extra_production_qty: int = 0

    decision_made: bool = False
    decision_made_at: Optional[datetime] = None
    decision_made_by: Optional[str] = None

    available_inventory_qty: int = 0
    recommended_fulfillment_mode: Optional[OrderLineFulfillmentMode] = None
    recommended_production_qty: int = 0
    planned_production_qty: int = 0
    decision_required: bool = False
    allowed_plan_types: List[OrderLinePlanType] = Field(default_factory=list)

    plan_type: Optional[OrderLinePlanType] = None
    plan_type_display: Optional[str] = None

    ship_target_qty: int = 0
    already_shipped_qty: int = 0
    remaining_ship_qty: int = 0
    needs_shortage_action: bool = False
    shortage_closed: bool = False
    short_close_state: Literal["NONE", "CONFIRMED", "REVIEW_REQUIRED"] = "NONE"

    

class PageMeta(BaseModel):
    page: int
    size: int
    total: int


class OrderLineListOut(BaseModel):
    items: List[OrderLineOut]
    meta: PageMeta

#발주등록 벌크 등록

class OrderLineBulkImportRowIn(BaseModel):
    row_number: int = Field(..., ge=1)
    erp_order_no: str = Field(..., max_length=40)
    product_code: str = Field(..., max_length=60)
    partner_name: str = Field(..., max_length=200)
    erp_product_display_name: str = Field(..., max_length=300)
    order_qty_text: str = Field(..., max_length=50)
    due_date_text: str = Field(..., max_length=20)
    remark: Optional[str] = None


class OrderLineBulkValidateRequest(BaseModel):
    items: List[OrderLineBulkImportRowIn] = Field(..., min_length=1)


class OrderLineBulkValidateMessage(BaseModel):
    field: str
    level: str
    message: str


class OrderLineBulkValidateRowOut(BaseModel):
    row_number: int
    erp_order_no: str
    line_no: Optional[int] = None

    order_date: Optional[date] = None
    due_date: Optional[date] = None

    partner_id: Optional[int] = None
    partner_name: Optional[str] = None

    product_id: Optional[int] = None
    product_code: str
    erp_product_display_name: str
    mes_product_display_name: Optional[str] = None

    parsed_product_name: Optional[str] = None
    parsed_product_spec: Optional[str] = None

    order_qty: Optional[int] = None

    status: str
    product_name_mismatch: bool = False
    can_apply_product_name_change: bool = False
    apply_product_name_change: bool = False

    messages: List[OrderLineBulkValidateMessage] = Field(default_factory=list)


class OrderLineBulkValidateGroupOut(BaseModel):
    erp_order_no: str
    order_date: Optional[date] = None
    due_date: Optional[date] = None

    partner_id: Optional[int] = None
    partner_name: Optional[str] = None

    status: str
    can_commit: bool

    messages: List[OrderLineBulkValidateMessage] = Field(default_factory=list)
    rows: List[OrderLineBulkValidateRowOut] = Field(default_factory=list)


class OrderLineBulkValidateResult(BaseModel):
    total_row_count: int
    ready_row_count: int
    review_row_count: int
    error_row_count: int
    duplicate_group_count: int
    groups: List[OrderLineBulkValidateGroupOut] = Field(default_factory=list)


class OrderLineBulkCommitRowChoice(BaseModel):
    row_number: int = Field(..., ge=1)
    apply_product_name_change: bool = False


class OrderLineBulkCommitRequest(BaseModel):
    items: List[OrderLineBulkImportRowIn] = Field(..., min_length=1)
    row_choices: List[OrderLineBulkCommitRowChoice] = Field(default_factory=list)


class OrderLineBulkCommitGroupResult(BaseModel):
    erp_order_no: str
    status: str
    message: Optional[str] = None
    created_order_line_ids: List[int] = Field(default_factory=list)


class OrderLineBulkCommitResult(BaseModel):
    total_group_count: int
    success_group_count: int
    failure_group_count: int
    groups: List[OrderLineBulkCommitGroupResult] = Field(default_factory=list)


class OrderLineFulfillmentMode(str, Enum):
    INVENTORY_FIRST = "INVENTORY_FIRST"
    PRODUCTION_FIRST = "PRODUCTION_FIRST"
    HYBRID = "HYBRID"


class OrderLineProductionPolicy(str, Enum):
    ORDER_ONLY = "ORDER_ONLY"
    ALLOW_STOCK_BUILD = "ALLOW_STOCK_BUILD"
    INVENTORY_ONLY_CLOSE = "INVENTORY_ONLY_CLOSE"

class OrderLinePlanConfirmRequest(BaseModel):
    plan_type: OrderLinePlanType
    memo: Optional[str] = None    


class OrderLinePlanHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_history_id: int
    order_line_id: int
    plan_type: OrderLinePlanType

    ship_target_qty: int
    available_inventory_qty: int
    stock_ship_qty: int
    production_qty: int

    is_short_close: bool
    memo: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime

class OrderLineBaseLotCreateResult(BaseModel):
    order_line_id: int
    planned_production_qty: int
    created_lot_id: int
    created_lot_no: str
    created_lot_qty: int
    order_status: str

class OrderLineShortCloseRequest(BaseModel):
    memo: Optional[str] = None
