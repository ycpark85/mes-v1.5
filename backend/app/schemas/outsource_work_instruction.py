from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal

class OutsourceWorkInstructionFileCreate(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_path: str = Field(..., min_length=1)
    content_type: Optional[str] = None

class OutsourceWorkInstructionGroupItemCreate(BaseModel):
    lot_id: int
    cuts_per_sheet: int = Field(..., gt=0)
    expected_output_qty: Optional[int] = Field(default=None, ge=0)
    remark: Optional[str] = None


class OutsourceWorkInstructionGroupCreate(BaseModel):
    group_seq: Optional[str] = None
    is_bundle: bool = False
    sheet_qty: int = Field(..., gt=0)
    length_m: Optional[Decimal] = Field(default=None, ge=0)
    sheet_cut_count: Optional[int] = Field(default=None, gt=0)
    fabric_lot_no: Optional[str] = None
    representative_lot_id: Optional[int] = None
    remark: Optional[str] = None
    items: List[OutsourceWorkInstructionGroupItemCreate] = Field(..., min_length=1)

class OutsourceWorkInstructionBatchGroupCreate(BaseModel):
    customer_partner_id: int
    lot_ids: List[int] = Field(..., min_length=1)
    memo: Optional[str] = None
    files: List[OutsourceWorkInstructionFileCreate] = Field(default_factory=list)
    groups: List[OutsourceWorkInstructionGroupCreate] = Field(default_factory=list)

class OutsourceWorkInstructionBatchCreate(BaseModel):
    instruction_date: date
    groups: List[OutsourceWorkInstructionBatchGroupCreate] = Field(..., min_length=1)


class OutsourceWorkInstructionFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    outsource_work_instruction_file_id: int
    file_name: str
    file_path: str
    content_type: Optional[str] = None
    created_at: datetime

class OutsourceWorkInstructionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    outsource_work_instruction_item_id: int
    lot_id: int
    lot_no: Optional[str] = None
    order_no: Optional[str] = None
    line_no: Optional[int] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    lot_qty: Optional[int] = None
    process_type: str

class OutsourceWorkInstructionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    outsource_work_instruction_id: int
    instruction_no: str
    instruction_date: date
    process_type: str
    partner_id: int
    is_bundle: bool
    memo: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: List[OutsourceWorkInstructionItemOut] = Field(default_factory=list)
    files: List[OutsourceWorkInstructionFileOut] = Field(default_factory=list)

class OutsourceWorkInstructionCandidateLotOut(BaseModel):
    lot_id: int
    lot_no: str
    order_line_id: int
    order_no: str
    line_no: int
    product_id: int
    product_code: str
    product_name: str
    customer_partner_id: int
    customer_partner_name: Optional[str] = None
    lot_qty: int
    current_stock_qty: int = 0
    available_process_types: List[str]
    panel_width_mm: int | None = None
    panel_length_mm: int | None = None
    product_spec: str | None = None
    cut_qty_per_panel: int | None = None

class OutsourceWorkInstructionPlateUploadOut(BaseModel):
    file_name: str
    file_path: str
    content_type: Optional[str] = None
    file_size: int
    uploaded_at: datetime

# =========================
# page 2 purchase order dto
# =========================   

class OutsourcePurchaseOrderTargetOut(BaseModel):
    outsource_work_instruction_id: int
    outsource_work_instruction_item_id: int
    outsource_work_group_id: int
    instruction_no: str
    instruction_date: date
    process_type: str
    group_seq: str

    lot_id: int
    lot_no: str
    is_rework: bool
    order_line_id: int
    order_no: str
    line_no: int

    product_id: int
    product_code: str
    product_name: str
    lot_qty: int
    representative_lot_id: Optional[int] = None

    outsource_partner_id: int
    outsource_partner_name: Optional[str] = None
    inbound_partner_name: str
    customer_partner_id: int
    customer_partner_name: str | None = None

    panel_width_mm: int | None = None
    panel_length_mm: int | None = None
    product_spec: str | None = None
    cut_qty_per_panel: int | None = None
    length_m: Decimal | None = None
    sheet_qty: int | None = None
    fabric_lot_no: str | None = None
    is_print_product: bool = False

    
    is_bundle: bool
    memo: Optional[str] = None

    files: List[OutsourceWorkInstructionFileOut] = Field(default_factory=list)

class OutsourceWorkInstructionBatchOut(BaseModel):
    items: List[OutsourceWorkInstructionOut] = Field(default_factory=list)


class OutsourceWorkGroupLotOut(BaseModel):
    outsource_work_group_item_id: int
    lot_id: int
    lot_no: str
    order_no: Optional[str] = None
    line_no: Optional[int] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    lot_qty: Optional[int] = None
    cuts_per_sheet: int
    expected_output_qty: Optional[int] = None


class OutsourceWorkGroupListItemOut(BaseModel):
    outsource_work_group_id: int
    outsource_work_instruction_id: int
    instruction_no: str
    instruction_date: date
    process_type: str
    partner_id: int
    partner_name: Optional[str] = None
    group_seq: str
    status: str
    status_name: str
    is_bundle: bool
    representative_lot_id: Optional[int] = None
    representative_lot_no: Optional[str] = None
    representative_product_name: Optional[str] = None
    lot_nos_text: str = ""
    product_names_text: str = ""
    sheet_qty: int
    length_m: Optional[Decimal] = None
    sheet_cut_count: int
    fabric_lot_no: Optional[str] = None
    can_cancel: bool
    cancel_block_reason: Optional[str] = None
    can_update: bool
    update_block_reason: Optional[str] = None
    memo: Optional[str] = None
    created_at: datetime


class OutsourceWorkGroupListOut(BaseModel):
    items: List[OutsourceWorkGroupListItemOut] = Field(default_factory=list)
    total_count: int = 0


class OutsourceWorkGroupDetailOut(OutsourceWorkGroupListItemOut):
    lots: List[OutsourceWorkGroupLotOut] = Field(default_factory=list)
    files: List[OutsourceWorkInstructionFileOut] = Field(default_factory=list)


class OutsourceWorkGroupCancelIn(BaseModel):
    reason: str = Field(..., min_length=1)


class OutsourceWorkGroupUpdateIn(BaseModel):
    sheet_qty: int = Field(..., gt=0)
    length_m: Optional[Decimal] = Field(default=None, ge=0)
    sheet_cut_count: int = Field(..., gt=0)
    fabric_lot_no: Optional[str] = None
    remark: Optional[str] = None
    reason: str = Field(..., min_length=1)


class OutsourcePurchaseOrderTargetListOut(BaseModel):
    items: List[OutsourcePurchaseOrderTargetOut] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    size: int = 100

class OutsourceWorkInstructionCandidateLotListOut(BaseModel):
    items: List[OutsourceWorkInstructionCandidateLotOut]

# =========================
# purchase order save/status dto
# =========================

class OutsourcePurchaseOrderCreateItem(BaseModel):
    lot_id: int
    outsource_work_instruction_id: Optional[int] = None
    item_seq: int
    qty: int = Field(..., gt=0)


class OutsourcePurchaseOrderCreate(BaseModel):
    purchase_order_date: date
    due_date: Optional[date] = None
    process_type: str
    outsource_partner_id: int
    inbound_partner_id: Optional[int] = None
    work_description: Optional[str] = None
    remark: Optional[str] = None
    qty: int = Field(..., gt=0)
    unit_price: Optional[Decimal] = Field(default=None, ge=0)
    supply_amount: Optional[Decimal] = Field(default=None, ge=0)
    vat_amount: Optional[Decimal] = Field(default=None, ge=0)
    total_amount: Optional[Decimal] = Field(default=None, ge=0)
    items: List[OutsourcePurchaseOrderCreateItem] = Field(..., min_length=1)
    form_snapshot: Optional[dict] = None


class OutsourcePurchaseOrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    outsource_purchase_order_item_id: int
    outsource_purchase_order_id: int
    lot_id: int
    outsource_work_instruction_id: Optional[int] = None
    item_seq: int
    qty: int
    status: Optional[str] = None
    vendor_received_at: Optional[datetime] = None
    work_done_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None
    work_done_qty: Optional[int] = None
    bad_qty: Optional[int] = None
    work_done_remark: Optional[str] = None
    created_at: datetime

    lot_no: Optional[str] = None
    order_no: Optional[str] = None
    line_no: Optional[int] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    lot_qty: Optional[int] = None

class OutsourcePurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    outsource_purchase_order_id: int
    purchase_order_no: str
    purchase_order_date: date
    due_date: Optional[date] = None
    process_type: str
    outsource_partner_id: int
    inbound_partner_id: Optional[int] = None
    work_description: Optional[str] = None
    remark: Optional[str] = None
    qty: int
    unit_price: Optional[Decimal] = None
    supply_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime

    outsource_partner_name: Optional[str] = None
    inbound_partner_name: Optional[str] = None
    items: List[OutsourcePurchaseOrderItemOut] = Field(default_factory=list)

class OutsourcePurchaseOrderCutSnapshotRow(BaseModel):
    no: int
    raw_material_text: Optional[str] = None
    length_m_text: Optional[str] = None
    inbound_place_text: Optional[str] = None
    cut_spec_text: Optional[str] = None
    sheet_qty_text: Optional[str] = None


class OutsourcePurchaseOrderCutSnapshot(BaseModel):
    request_company_name: Optional[str] = None
    requester_name: Optional[str] = None
    purchase_order_date: Optional[str] = None
    raw_material_inbound_text: Optional[str] = None
    stock_500_width_text: Optional[str] = None
    stock_600_width_text: Optional[str] = None
    stock_600_tpt0268_text: Optional[str] = None
    remark: Optional[str] = None
    rows: List[OutsourcePurchaseOrderCutSnapshotRow] = Field(default_factory=list)

class OutsourcePurchaseOrderPrintSnapshotRow(BaseModel):
    no: int
    customer_name: Optional[str] = None
    product_name: Optional[str] = None
    material_spec: Optional[str] = None
    print_sheet_qty: Optional[str] = None
    sample: Optional[str] = None
    plate_count: Optional[str] = None
    color_name: Optional[str] = None
    material_type: Optional[str] = None
    remark: Optional[str] = None


class OutsourcePurchaseOrderPrintSnapshot(BaseModel):
    vendor_name: Optional[str] = None
    request_company_name: Optional[str] = None
    requester_name: Optional[str] = None
    purchase_order_date: Optional[str] = None
    footer_remark: Optional[str] = None
    rows: List[OutsourcePurchaseOrderPrintSnapshotRow] = Field(default_factory=list)

class OutsourcePurchaseOrderListItemOut(BaseModel):
    outsource_purchase_order_id: int
    purchase_order_no: str
    purchase_order_date: date
    process_type: str
    outsource_partner_id: int
    outsource_partner_name: Optional[str] = None
    qty: int
    remark: Optional[str] = None
    created_at: datetime


class OutsourcePurchaseOrderListOut(BaseModel):
    items: List[OutsourcePurchaseOrderListItemOut] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    size: int = 100


# =========================
# bohyun outsource management dto
# =========================

class BohyunOutsourceGroupItemOut(BaseModel):
    outsource_work_group_item_id: int
    lot_id: int

    lot_no: Optional[str] = None
    order_no: Optional[str] = None
    line_no: Optional[int] = None

    product_id: Optional[int] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None

    cuts_per_sheet: int
    expected_output_qty: Optional[int] = None
    actual_output_qty: Optional[int] = None

    remark: Optional[str] = None


class BohyunOutsourceGroupListItemOut(BaseModel):
    outsource_work_group_id: int
    outsource_work_instruction_id: int
    representative_lot_id: Optional[int] = None
    representative_product_name: Optional[str] = None

    instruction_no: str
    instruction_date: date
    process_type: str

    partner_id: int
    partner_name: Optional[str] = None
    inbound_source_name: Optional[str] = None
    
    is_bundle: bool
    group_seq: str

    sheet_qty: int
    work_done_sheet_qty: Optional[int] = None

    length_m: Optional[Decimal] = None
    sheet_cut_count: int

    status: str

    vendor_received_at: Optional[datetime] = None
    work_done_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None

    outsource_processing_fee: Optional[Decimal] = None
    work_done_remark: Optional[str] = None

    lot_nos: List[str] = Field(default_factory=list)
    product_names: List[str] = Field(default_factory=list)

    items: List[BohyunOutsourceGroupItemOut] = Field(default_factory=list)


class BohyunOutsourceGroupListOut(BaseModel):
    items: List[BohyunOutsourceGroupListItemOut] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    size: int = 100
    processing_fee_total: Decimal = Decimal("0")
    


class BohyunOutsourceGroupWorkDone(BaseModel):
    work_done_sheet_qty: int = Field(..., ge=0)
    outsource_processing_fee: Optional[Decimal] = Field(default=None, ge=0)
    remark: Optional[str] = None


class BohyunOutsourceGroupShipBatch(BaseModel):
    group_ids: List[int] = Field(..., min_length=1)    





