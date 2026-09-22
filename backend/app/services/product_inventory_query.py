from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session
from app.core.time import korea_day_bounds_utc

from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.schemas.inventory import (
    ProductInventoryConsistencyListOut,
    ProductInventoryConsistencyOut,
    ProductInventoryListOut,
    ProductInventoryMovementListOut,
    ProductInventoryMovementOut,
    ProductInventoryOut,
    ProductInventoryLotOut,
    ProductInventoryLotListOut,
)


def list_product_inventories(
    db: Session,
    *,
    page: int = 1,
    size: int = 100,
    q: str | None = None,
    include_zero: bool = False,
) -> ProductInventoryListOut:
    base = (
        select(
            Product.product_id,
            Product.product_code,
            Product.product_name,
            Product.uom,
            func.coalesce(ProductInventory.current_qty, 0).label("current_qty"),
            ProductInventory.updated_at,
        )
        .select_from(Product)
        .join(ProductInventory, ProductInventory.product_id == Product.product_id)
        .where(Product.is_active.is_(True))
    )

    count_q = (
        select(func.count())
        .select_from(Product)
        .join(ProductInventory, ProductInventory.product_id == Product.product_id)
        .where(Product.is_active.is_(True))
    )

    if not include_zero:
        base = base.where(ProductInventory.current_qty > 0)
        count_q = count_q.where(ProductInventory.current_qty > 0)

    if q:
        keyword = f"%{q.strip()}%"
        search_condition = or_(
            Product.product_code.ilike(keyword),
            Product.product_name.ilike(keyword),
        )
        base = base.where(search_condition)
        count_q = count_q.where(search_condition)

    total = int(db.execute(count_q).scalar_one() or 0)

    rows = (
        db.execute(
            base.order_by(Product.product_code.asc())
            .limit(size)
            .offset((page - 1) * size)
        )
        .mappings()
        .all()
    )

    return ProductInventoryListOut(
        items=[ProductInventoryOut(**dict(row)) for row in rows],
        total=total,
        page=page,
        size=size,
    )


def list_product_inventory_lots(
    db: Session, *, product_id: int, q: str | None = None,
    include_zero: bool = False, page: int = 1, size: int = 100,
) -> ProductInventoryLotListOut:
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found")
    base = select(ProductInventoryLot).where(ProductInventoryLot.product_id == product_id)
    if not include_zero:
        base = base.where(ProductInventoryLot.current_qty > 0)
    if q and q.strip():
        base = base.where(ProductInventoryLot.lot_no.ilike(f"%{q.strip()}%"))
    filtered = base.subquery()
    total, total_qty = db.execute(select(func.count(), func.coalesce(func.sum(filtered.c.current_qty), 0))).one()
    inventory = db.execute(select(ProductInventory.current_qty, ProductInventory.updated_at).where(
        ProductInventory.product_id == product_id)).one_or_none()
    current_qty = int(inventory.current_qty or 0) if inventory else 0
    lot_qty = int(db.execute(select(func.coalesce(func.sum(ProductInventoryLot.current_qty), 0)).where(
        ProductInventoryLot.product_id == product_id)).scalar_one())
    rows = db.execute(base.order_by(ProductInventoryLot.created_at, ProductInventoryLot.product_inventory_lot_id)
        .limit(size).offset((page - 1) * size)).scalars().all()
    return ProductInventoryLotListOut(items=[ProductInventoryLotOut.model_validate(row) for row in rows],
        product_id=product_id, product_current_qty=current_qty, total_qty=int(total_qty), total=int(total),
        product_updated_at=inventory.updated_at if inventory else None,
        page=page, size=size, stock_warning=("품목 총재고와 LOT별 합계가 다릅니다. 정합성점검이 필요합니다."
                                            if current_qty != lot_qty else None))


def list_product_inventory_movements(
    db: Session,
    *,
    product_id: int | None = None,
    movement_type: str | None = None,
    product_inventory_lot_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    size: int = 100,
    stock_page: int | None = None,
    stock_size: int = 50,
    stock_q: str | None = None,
    stock_include_zero: bool = False,
) -> ProductInventoryMovementListOut:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="조회 시작일은 종료일보다 늦을 수 없습니다.")
    if stock_page is not None and product_inventory_lot_id is None:
        raise HTTPException(status_code=422, detail="재고와 이력을 함께 조회하려면 LOT를 선택해야 합니다.")
    selected_lot = None
    warning = None
    if product_inventory_lot_id is not None:
        selected_lot = db.get(ProductInventoryLot, product_inventory_lot_id)
        if selected_lot is None or (product_id is not None and selected_lot.product_id != product_id):
            raise HTTPException(status_code=404, detail="선택한 품목의 재고 LOT를 찾을 수 없습니다.")
        product_id = selected_lot.product_id
        ledger_total = db.execute(select(func.coalesce(func.sum(ProductInventoryMovement.qty), 0)).where(
            ProductInventoryMovement.product_id == product_id,
            ProductInventoryMovement.product_inventory_lot_id == product_inventory_lot_id)).scalar_one()
        if int(ledger_total) != int(selected_lot.current_qty):
            warning = "LOT 수불 합계와 현재 재고가 다릅니다. 반영 후 LOT 재고는 확인 불가입니다."

    # Calculate the complete ledger BEFORE date/type/page filtering. Per-product locks
    # serialize movement IDs; timestamp ties or backdated transactions cannot change balances.
    movement = ProductInventoryMovement
    ledger = select(movement,
        func.sum(movement.qty).over(partition_by=movement.product_inventory_lot_id,
            order_by=movement.inventory_movement_id, rows=(None, 0)).label("lot_balance"),
        func.sum(movement.qty).over(partition_by=movement.product_inventory_lot_id).label("lot_total"))
    if product_id is not None:
        ledger = ledger.where(movement.product_id == product_id)
    if product_inventory_lot_id is not None:
        ledger = ledger.where(movement.product_inventory_lot_id == product_inventory_lot_id)
    history = ledger.subquery()
    base = (
        select(
            *[history.c[column.name] for column in movement.__table__.columns],
            Product.product_code,
            Product.product_name,
            case(((history.c.lot_total == ProductInventoryLot.current_qty)
                  & (history.c.lot_balance >= 0), history.c.lot_balance), else_=None).label("lot_balance_after"),
        )
        .select_from(history)
        .join(Product, Product.product_id == history.c.product_id)
        .outerjoin(ProductInventoryLot, ProductInventoryLot.product_inventory_lot_id == history.c.product_inventory_lot_id)
    )
    if movement_type:
        base = base.where(history.c.movement_type == movement_type)
    if date_from:
        base = base.where(history.c.created_at >= korea_day_bounds_utc(date_from)[0])
    if date_to:
        base = base.where(history.c.created_at < korea_day_bounds_utc(date_to)[1])
    total = int(db.execute(select(func.count()).select_from(base.subquery())).scalar_one())

    rows = (
        db.execute(
            base.order_by(
                history.c.inventory_movement_id.desc(),
            )
            .limit(size)
            .offset((page - 1) * size)
        )
        .mappings()
        .all()
    )

    stock_snapshot = None
    if stock_page is not None:
        # The endpoint's read-only repeatable-read transaction keeps these totals
        # and LOT rows at the same point in time as the movement ledger above.
        stock_snapshot = list_product_inventory_lots(db, product_id=product_id,
            q=stock_q, include_zero=stock_include_zero, page=stock_page, size=stock_size)
        last_page = max(1, (stock_snapshot.total + stock_size - 1) // stock_size)
        if stock_page > last_page:
            stock_snapshot = list_product_inventory_lots(db, product_id=product_id,
                q=stock_q, include_zero=stock_include_zero, page=last_page, size=stock_size)

    return ProductInventoryMovementListOut(
        items=[ProductInventoryMovementOut(**dict(row)) for row in rows],
        total=total,
        page=page,
        size=size,
        product_inventory_lot_id=product_inventory_lot_id,
        stock_lot_no=selected_lot.lot_no if selected_lot else None,
        current_qty=int(selected_lot.current_qty) if selected_lot else None,
        lot_updated_at=selected_lot.updated_at if selected_lot else None,
        history_warning=warning,
        stock_snapshot=stock_snapshot,
    )


def list_product_inventory_consistency(db: Session) -> ProductInventoryConsistencyListOut:
    lot_qty_sq = (
        select(
            ProductInventoryLot.product_id.label("product_id"),
            func.coalesce(func.sum(ProductInventoryLot.current_qty), 0).label("lot_qty"),
        )
        .group_by(ProductInventoryLot.product_id)
        .subquery()
    )

    movement_qty_sq = (
        select(
            ProductInventoryMovement.product_id.label("product_id"),
            func.coalesce(func.sum(ProductInventoryMovement.qty), 0).label("movement_qty"),
        )
        .group_by(ProductInventoryMovement.product_id)
        .subquery()
    )

    current_qty = func.coalesce(ProductInventory.current_qty, 0)
    lot_qty = func.coalesce(lot_qty_sq.c.lot_qty, 0)
    movement_qty = func.coalesce(movement_qty_sq.c.movement_qty, 0)

    rows = (
        db.execute(
            select(
                Product.product_id,
                Product.product_code,
                Product.product_name,
                current_qty.label("current_qty"),
                lot_qty.label("lot_qty"),
                movement_qty.label("movement_qty"),
                (current_qty - lot_qty).label("diff_qty"),
            )
            .select_from(Product)
            .join(ProductInventory, ProductInventory.product_id == Product.product_id)
            .outerjoin(lot_qty_sq, lot_qty_sq.c.product_id == Product.product_id)
            .outerjoin(movement_qty_sq, movement_qty_sq.c.product_id == Product.product_id)
            .where(Product.is_active.is_(True))
            .where((current_qty != lot_qty) | (current_qty != movement_qty))
            .order_by(Product.product_code.asc())
        )
        .mappings()
        .all()
    )

    return ProductInventoryConsistencyListOut(
        items=[ProductInventoryConsistencyOut(**dict(row)) for row in rows],
        total=len(rows),
    )
