from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.order_line import OrderLine
from app.models.order_line_plan_history import OrderLinePlanHistory
from app.models.partner import Partner
from app.models.product import Product
from app.schemas.order_line import OrderLineOut
from app.services.order_line_display import to_plan_type_display


def build_order_line_out(
    db: Session,
    order_line: OrderLine,
    *,
    plan_history: OrderLinePlanHistory | None = None,
    partner: Partner | None = None,
    product: Product | None = None,
) -> OrderLineOut:
    if partner is None:
        partner = db.get(Partner, order_line.partner_id)
    if product is None:
        product = db.get(Product, order_line.product_id)

    out = OrderLineOut.model_validate(order_line, from_attributes=True)
    out.shortage_closed = order_line.status == "DONE" and order_line.short_close_state == "CONFIRMED"
    out.partner_name = partner.name if partner else None
    out.product_code = product.product_code if product else None
    out.product_name = product.product_name if product else None

    if plan_history is not None:
        out.plan_type = plan_history.plan_type
        out.plan_type_display = to_plan_type_display(plan_history.plan_type)

    return out


def get_order_line_out_by_id(db: Session, order_line_id: int) -> OrderLineOut:
    order_line = db.get(OrderLine, order_line_id)
    if not order_line or not order_line.is_active:
        raise HTTPException(status_code=404, detail="OrderLine not found")

    return build_order_line_out(db, order_line)
