from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.time import korea_day_bounds_utc

from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.shipment_line import ShipmentLine
from app.schemas.shipment import ShipmentLineOut
from app.services.ship_qty_policy import calculate_ship_qty


def list_shipments_for_grid(
    db: Session,
    *,
    status: str,
    page: int,
    size: int,
    q: Optional[str] = None,
    shipped_from: Optional[date] = None,
    shipped_to: Optional[date] = None,
) -> tuple[list[ShipmentLineOut], int]:
    base = (
        select(
            ShipmentLine,
            OrderLine.order_no.label("order_no"),
            OrderLine.order_qty.label("order_qty"),
            Partner.name.label("partner_name"),
            Product.product_code.label("product_code"),
            OrderLine.source_erp_product_code,
            func.coalesce(OrderLine.source_product_name, Product.product_name).label("product_name"),
            Lot.lot_no.label("lot_no"),
        )
        .select_from(ShipmentLine)
        .join(OrderLine, OrderLine.order_line_id == ShipmentLine.order_line_id)
        .join(Partner, Partner.partner_id == OrderLine.partner_id)
        .join(Product, Product.product_id == ShipmentLine.product_id)
        .outerjoin(Lot, Lot.lot_id == ShipmentLine.lot_id)
        .where(ShipmentLine.status == status)
    )

    count_q = (
        select(func.count())
        .select_from(ShipmentLine)
        .join(OrderLine, OrderLine.order_line_id == ShipmentLine.order_line_id)
        .join(Partner, Partner.partner_id == OrderLine.partner_id)
        .join(Product, Product.product_id == ShipmentLine.product_id)
        .outerjoin(Lot, Lot.lot_id == ShipmentLine.lot_id)
        .where(ShipmentLine.status == status)
    )

    if q and q.strip():
        normalized_q = q.strip()
        keyword = f"%{normalized_q}%"
        search_cond = or_(
            OrderLine.order_no == normalized_q.upper(),
            Partner.name.ilike(keyword),
            Product.product_code.ilike(keyword),
            OrderLine.source_erp_product_code.ilike(keyword),
            (Product.product_name.ilike(keyword) | OrderLine.source_product_name.ilike(keyword)),
            Lot.lot_no.ilike(keyword),
            ShipmentLine.stock_lot_no.ilike(keyword),
        )
        base = base.where(search_cond)
        count_q = count_q.where(search_cond)

    if status == "DONE":
        if shipped_from is not None:
            shipped_from_dt, _ = korea_day_bounds_utc(shipped_from)
            base = base.where(ShipmentLine.shipped_at >= shipped_from_dt)
            count_q = count_q.where(ShipmentLine.shipped_at >= shipped_from_dt)

        if shipped_to is not None:
            _, shipped_to_exclusive = korea_day_bounds_utc(shipped_to)
            base = base.where(ShipmentLine.shipped_at < shipped_to_exclusive)
            count_q = count_q.where(ShipmentLine.shipped_at < shipped_to_exclusive)

    total = int(db.execute(count_q).scalar_one() or 0)

    rows = (
        db.execute(
            base.order_by(
                ShipmentLine.created_at.desc(),
                ShipmentLine.shipment_line_id.desc(),
            )
            .limit(size)
            .offset((page - 1) * size)
        )
        .all()
    )

    order_line_ids = sorted({int(row[0].order_line_id) for row in rows})
    product_ids = sorted({int(row[0].product_id) for row in rows})

    shipped_qty_map: dict[int, int] = {}
    if order_line_ids:
        shipped_rows = (
            db.execute(
                select(
                    ProductInventoryMovement.order_line_id,
                    func.coalesce(func.sum(-ProductInventoryMovement.qty), 0).label("already_shipped_qty"),
                )
                .where(
                    ProductInventoryMovement.order_line_id.in_(order_line_ids),
                    ProductInventoryMovement.movement_type == "SHIP_OUT",
                )
                .group_by(ProductInventoryMovement.order_line_id)
            )
            .all()
        )
        shipped_qty_map = {
            int(order_line_id): int(already_shipped_qty or 0)
            for order_line_id, already_shipped_qty in shipped_rows
            if order_line_id is not None
        }

    current_stock_qty_map: dict[int, int] = {}
    if product_ids:
        inventory_rows = (
            db.execute(
                select(ProductInventory.product_id, ProductInventory.current_qty).where(
                    ProductInventory.product_id.in_(product_ids)
                )
            )
            .all()
        )
        current_stock_qty_map = {
            int(product_id): int(current_qty or 0)
            for product_id, current_qty in inventory_rows
        }

    items: list[ShipmentLineOut] = []

    for shipment_line, order_no, order_qty, partner_name, product_code, source_code, product_name, lot_no in rows:
        display_lot_no = shipment_line.stock_lot_no if shipment_line.source_type == "STOCK" else lot_no

        ship_target_qty = int(calculate_ship_qty(partner_name or "", int(order_qty or 0)) or 0)
        already_shipped_qty = shipped_qty_map.get(int(shipment_line.order_line_id), 0)
        remaining_ship_qty = max(ship_target_qty - already_shipped_qty, 0)

        current_stock_qty = current_stock_qty_map.get(int(shipment_line.product_id), 0)

        if status == "WAITING":
            stock_after_ship_qty = max(current_stock_qty - int(shipment_line.ship_qty or 0), 0)
        else:
            stock_after_ship_qty = current_stock_qty

        items.append(
            ShipmentLineOut(
                shipment_line_id=shipment_line.shipment_line_id,
                order_line_id=shipment_line.order_line_id,
                order_no=order_no,
                partner_name=partner_name,
                product_id=shipment_line.product_id,
                product_code=source_code or product_code,
                mes_product_code=product_code,
                product_name=product_name,
                product_inventory_lot_id=shipment_line.product_inventory_lot_id,
                stock_lot_no=shipment_line.stock_lot_no,
                lot_id=shipment_line.lot_id,
                lot_no=display_lot_no,
                inspection_result_id=shipment_line.inspection_result_id,
                source_type=shipment_line.source_type,
                status=shipment_line.status,
                ship_qty=shipment_line.ship_qty,
                shipped_qty=shipment_line.shipped_qty,
                ship_target_qty=ship_target_qty,
                already_shipped_qty=already_shipped_qty,
                remaining_ship_qty=remaining_ship_qty,
                current_stock_qty=current_stock_qty,
                stock_after_ship_qty=stock_after_ship_qty,
                memo=shipment_line.memo,
                created_at=shipment_line.created_at,
                shipped_at=shipment_line.shipped_at,
            )
        )

    return items, total
