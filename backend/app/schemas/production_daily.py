from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


ProductionDailyStatus = Literal["IN_PROGRESS", "COMPLETED"]


class ProductionDailyRowOut(BaseModel):
    order_line_id: int
    order_no: str
    line_no: int
    due_date: date
    due_slack_text: str
    due_slack_level: str
    due_days: int
    partner_id: int
    partner_name: str
    product_id: int
    product_code: str
    mes_product_code: str | None = None
    product_name: str
    order_qty: int
    available_inventory_qty: int
    production_qty: int
    work_type: str
    work_type_display: str
    current_process: str
    current_process_display: str
    progress_rate: int
    lot_count: int
    target_lot_count: int
    completed_lot_count: int
    lot_nos: list[str]


class ProductionDailyListOut(BaseModel):
    items: list[ProductionDailyRowOut]
    total: int
    page: int
    size: int
