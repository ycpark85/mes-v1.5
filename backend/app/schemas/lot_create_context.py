from __future__ import annotations

from datetime import date
from typing import Optional, List

from pydantic import BaseModel


class LotCreatePrimaryCandidateDto(BaseModel):
    lot_id: int
    lot_no: str
    lot_qty: int
    uom: str
    status: str
    memo: Optional[str] = None
    can_create_rework: bool


class LotCreateDrawingDto(BaseModel):
    drawing_id: Optional[int] = None
    drawing_no: Optional[str] = None
    current_revision_id: Optional[int] = None
    current_revision_no: Optional[str] = None

    drawing_file_id: Optional[int] = None
    drawing_file_name: Optional[str] = None

    original_file_id: Optional[int] = None
    original_file_name: Optional[str] = None

    plate_file_id: Optional[int] = None
    plate_file_name: Optional[str] = None


class LotCreateContextDto(BaseModel):
    order_line_id: int
    order_no: str
    partner_id: int
    partner_name: str

    product_id: int
    product_code: str
    mes_product_code: str | None = None
    product_name: str

    order_qty: int
    uom: str
    due_date: date
    status: str

    panel_width_mm: Optional[int] = None
    panel_length_mm: Optional[int] = None
    cut_qty_per_panel: Optional[int] = None
    product_spec: Optional[str] = None

    drawing: LotCreateDrawingDto
    primary_lot_candidates: List[LotCreatePrimaryCandidateDto]

    can_create_primary_lot: bool