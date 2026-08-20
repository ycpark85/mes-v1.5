from __future__ import annotations

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.drawing import Drawing
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.routing_template import RoutingTemplate
from app.schemas.product import ProductOut


def list_products_for_grid(
    db: Session,
    *,
    page: int,
    size: int,
    q: str | None,
    partner_q: str | None,
    is_active: bool | None,
) -> tuple[list[ProductOut], int]:
    filters = []

    if is_active is not None:
        filters.append(Product.is_active == is_active)

    normalized_q = (q or "").strip()
    if normalized_q:
        keyword = f"%{normalized_q}%"
        filters.append(
            or_(
                Product.product_code.ilike(keyword),
                Product.product_name.ilike(keyword),
            )
        )

    normalized_partner_q = (partner_q or "").strip()
    if normalized_partner_q:
        partner_keyword = f"%{normalized_partner_q}%"
        matching_order_line = (
            select(OrderLine.order_line_id)
            .join(Partner, Partner.partner_id == OrderLine.partner_id)
            .where(
                OrderLine.product_id == Product.product_id,
                OrderLine.is_active.is_(True),
                or_(
                    Partner.name.ilike(partner_keyword),
                    Partner.business_no.ilike(partner_keyword),
                ),
            )
            .limit(1)
        )
        filters.append(exists(matching_order_line))

    total = db.execute(
        select(func.count())
        .select_from(Product)
        .where(*filters)
    ).scalar_one()

    rows = db.execute(
        select(
            Product,
            Drawing.drawing_no,
            RoutingTemplate.template_name,
            func.coalesce(ProductInventory.current_qty, 0),
        )
        .join(Drawing, Drawing.drawing_id == Product.drawing_id)
        .join(
            RoutingTemplate,
            RoutingTemplate.routing_template_id == Product.routing_template_id,
        )
        .outerjoin(
            ProductInventory,
            ProductInventory.product_id == Product.product_id,
        )
        .where(*filters)
        .order_by(Product.product_id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    items: list[ProductOut] = []
    for product, drawing_no, routing_template_name, current_stock_qty in rows:
        item = ProductOut.model_validate(product, from_attributes=True)
        item.drawing_no = drawing_no
        item.routing_template_name = routing_template_name
        item.current_stock_qty = int(current_stock_qty or 0)
        items.append(item)

    return items, int(total or 0)
