from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductInventoryOut(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    uom: str
    current_qty: int = 0
    updated_at: Optional[datetime] = None


class ProductInventoryListOut(BaseModel):
    items: list[ProductInventoryOut]
    total: int
    page: int
    size: int


class ProductInventoryMovementOut(BaseModel):
    inventory_movement_id: int
    product_id: int
    product_inventory_lot_id: Optional[int] = None
    stock_lot_no: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    movement_type: str
    qty: int
    balance_after: int
    lot_balance_after: Optional[int] = None
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    order_line_id: Optional[int] = None
    inspection_schedule_id: Optional[int] = None
    inspection_result_id: Optional[int] = None
    memo: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductInventoryLotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_inventory_lot_id: int
    product_id: int
    lot_no: str
    current_qty: int
    updated_at: datetime


class ProductInventoryLotListOut(BaseModel):
    items: list[ProductInventoryLotOut]
    product_id: int
    product_current_qty: int
    product_updated_at: Optional[datetime] = None
    total_qty: int
    total: int
    page: int
    size: int
    stock_warning: Optional[str] = None


class ProductInventoryMovementListOut(BaseModel):
    items: list[ProductInventoryMovementOut]
    total: int
    page: int
    size: int
    product_inventory_lot_id: Optional[int] = None
    stock_lot_no: Optional[str] = None
    current_qty: Optional[int] = None
    lot_updated_at: Optional[datetime] = None
    history_warning: Optional[str] = None
    stock_snapshot: Optional[ProductInventoryLotListOut] = None


class ProductInventoryLotAdjustmentIn(BaseModel):
    qty: int = Field(..., gt=0)
    memo: str = Field(..., min_length=1, max_length=1000)

    @field_validator("memo")
    @classmethod
    def require_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("재고 조정 사유를 입력해야 합니다.")
        return value


class ProductInventoryAdjustmentIn(ProductInventoryLotAdjustmentIn):
    stock_lot_no: Optional[str] = Field(default=None, max_length=100)
    product_inventory_lot_id: Optional[int] = Field(default=None, ge=1)


class ProductInventoryConsistencyOut(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    current_qty: int
    lot_qty: int
    movement_qty: int
    diff_qty: int


class ProductInventoryConsistencyListOut(BaseModel):
    items: list[ProductInventoryConsistencyOut]
    total: int

class InitialInventoryBulkItemIn(BaseModel):
    row_number: int
    product_code: str
    lot_no: str = Field(..., max_length=100)
    initial_qty: int = Field(..., ge=0)
    memo: Optional[str] = None


class InitialInventoryBulkIn(BaseModel):
    items: list[InitialInventoryBulkItemIn]


class InitialInventoryBulkErrorOut(BaseModel):
    row_number: int
    product_code: Optional[str] = None
    lot_no: Optional[str] = None
    message: str


class InitialInventoryBulkResultOut(BaseModel):
    total_count: int
    success_count: int
    skipped_count: int
    failure_count: int
    errors: list[InitialInventoryBulkErrorOut] = []
