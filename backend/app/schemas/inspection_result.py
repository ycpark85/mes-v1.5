from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Disposition = Literal["SHIP_AS_IS", "NOT_SHIPPABLE"]


class DefectAttachmentIn(BaseModel):
    file_uri: str = Field(..., min_length=1, max_length=600)
    file_name: Optional[str] = Field(default=None, max_length=255)
    mime_type: Optional[str] = Field(default=None, max_length=100)
    memo: Optional[str] = None


class DefectLineIn(BaseModel):
    defect_type_id: int = Field(..., ge=1)
    defect_qty: int = Field(..., ge=0)
    disposition: Disposition = "NOT_SHIPPABLE"
    memo: Optional[str] = None
    attachments: List[DefectAttachmentIn] = Field(default_factory=list)


class InspectionResultUpsertIn(BaseModel):
    good_qty: int = Field(..., ge=0)
    defect_ship_qty: int = Field(0, ge=0)
    defect_qty: int = Field(..., ge=0)
    uninspected_qty: int = Field(0, ge=0)

    stock_ship_qty: int = Field(0, ge=0)
    result_ship_qty: int = Field(0, ge=0)
    stock_in_qty: int = Field(0, ge=0)
    discard_qty: int = Field(0, ge=0)
    
    is_partial: bool = False
    next_inspection_date: Optional[date] = None
    partial_reason: Optional[str] = None
    memo: Optional[str] = None
    expected_updated_at: Optional[datetime] = None

    defects: List[DefectLineIn] = Field(default_factory=list)


class DefectAttachmentUploadOut(BaseModel):
    file_uri: str
    file_name: str
    mime_type: Optional[str] = None
    file_size: int


class DefectAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inspection_defect_attachment_id: int
    file_uri: str
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    memo: Optional[str] = None
    created_at: datetime

class DefectLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inspection_defect_id: int
    defect_type_id: int
    defect_qty: int
    disposition: str
    memo: Optional[str] = None
    created_at: datetime
    attachments: List[DefectAttachmentOut] = Field(default_factory=list)

class InspectionResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inspection_result_id: int
    inspection_schedule_id: int
    good_qty: int
    defect_ship_qty: int
    defect_qty: int
    inspected_qty: int
    uninspected_qty: int = 0
    received_qty: int = 0
    discard_qty: int = 0

    is_partial: bool
    next_inspection_date: Optional[date] = None
    partial_reason: Optional[str] = None
    memo: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    defects: List[DefectLineOut] = Field(default_factory=list)

class InspectionAccumulatedSummaryOut(BaseModel):
    good_qty: int = 0
    defect_qty: int = 0
    defect_ship_qty: int = 0
    inspected_qty: int = 0
    uninspected_qty: int = 0
    received_qty: int = 0
    discard_qty: int = 0
    
    current_result_stock_ship_qty: int = 0
    current_result_result_ship_qty: int = 0
    current_result_stock_in_qty: int = 0
    current_result_discard_qty: int = 0


class InspectionInventorySummaryOut(BaseModel):
    product_id: int
    order_line_id: int

    current_stock_qty: int = 0
    order_qty: int = 0
    ship_target_qty: int = 0
    already_shipped_qty: int = 0
    remaining_ship_target_qty: int = 0

    current_result_stock_ship_qty: int = 0
    current_result_result_ship_qty: int = 0
    current_result_stock_in_qty: int = 0
    current_result_discard_qty: int = 0


class InspectionResultGetOut(BaseModel):
    result: Optional[InspectionResultOut] = None
    schedule_status: Optional[str] = None
    inspection_round: int = 0
    inspection_round_count: int = 0
    rounds: List["InspectionRoundSummaryOut"] = Field(default_factory=list)
    accumulated: InspectionAccumulatedSummaryOut = Field(default_factory=InspectionAccumulatedSummaryOut)
    inventory: InspectionInventorySummaryOut | None = None


class InspectionResultUpsertOut(BaseModel):
    result: InspectionResultOut
    schedule_status: str
    created_next_schedule_id: Optional[int] = None


class InspectionResultListItemOut(BaseModel):
    inspection_result_id: int
    inspection_schedule_id: int
    lot_id: int
    lot_no: str
    inspection_date: date
    schedule_status: str
    inspection_round: int
    inspection_round_count: int
    is_partial: bool
    next_inspection_date: Optional[date] = None
    partial_reason: Optional[str] = None
    due_date: date
    partner_name: str
    product_code: str
    product_name: str
    lot_qty: int
    order_qty: int
    good_qty: int
    uninspected_qty: int
    received_qty: int
    result_ship_qty: int
    discard_qty: int
    stock_in_qty: int
    defect_qty: int
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    memo: Optional[str] = None


class InspectionRoundSummaryOut(BaseModel):
    inspection_result_id: int
    inspection_schedule_id: int
    inspection_date: date
    schedule_status: str
    inspection_round: int
    is_partial: bool
    next_inspection_date: Optional[date] = None
    partial_reason: Optional[str] = None
    good_qty: int = 0
    defect_ship_qty: int = 0
    defect_qty: int = 0
    inspected_qty: int = 0
    uninspected_qty: int = 0
    received_qty: int = 0
    memo: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime


class InspectionResultListOut(BaseModel):
    items: List[InspectionResultListItemOut] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    size: int = 100
    total_good_qty: int = 0
    total_uninspected_qty: int = 0
    total_received_qty: int = 0
    total_result_ship_qty: int = 0
    total_discard_qty: int = 0
    total_stock_in_qty: int = 0
    total_defect_qty: int = 0
