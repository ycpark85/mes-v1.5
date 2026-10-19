from __future__ import annotations

from app.services.order_line_display import order_product_code

from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud.lot import lot_crud
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.product import Product
from app.schemas.lot import LotDetailOut, LotListOut, LotOut, PageMeta


def list_lots(
    db: Session,
    *,
    page: int,
    size: int,
    q: Optional[str] = None,
    status: Optional[str] = None,
    order_line_id: Optional[int] = None,
    product_id: Optional[int] = None,
    partner_id: Optional[int] = None,
    due_date_from: Optional[date] = None,
    due_date_to: Optional[date] = None,
    created_date_from: Optional[date] = None,
    created_date_to: Optional[date] = None,
    inspection_schedule_registered: Optional[bool] = None,
    sort: Optional[str] = None,
) -> LotListOut:
    items, total = lot_crud.list_with_joins(
        db,
        page=page,
        size=size,
        status=status,
        q=q,
        order_line_id=order_line_id,
        product_id=product_id,
        partner_id=partner_id,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
        created_date_from=created_date_from,
        created_date_to=created_date_to,
        inspection_schedule_registered=inspection_schedule_registered,
        sort=sort,
    )

    return LotListOut(
        items=[LotOut(**item) for item in items],
        meta=PageMeta(page=page, size=size, total=total),
    )


def get_lot_detail(db: Session, lot_id: int) -> LotDetailOut:
    lot = lot_crud.get(db, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="LOT not found")

    order_line = db.get(OrderLine, lot.order_line_id)
    product = db.get(Product, lot.product_id)
    partner = db.get(Partner, order_line.partner_id) if order_line else None

    result = LotDetailOut.model_validate(lot, from_attributes=True)

    if order_line:
        result.order_no = order_line.order_no
        result.line_no = order_line.line_no
        result.partner_id = order_line.partner_id
        result.partner_name = partner.name if partner else None

    if product:
        result.product_code = order_product_code(order_line, product)
        result.mes_product_code = product.product_code
        result.product_name = product.product_name

    result.steps = [step for step in lot.steps]
    return result
