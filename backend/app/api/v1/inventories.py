from __future__ import annotations

from typing import Annotated, Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db, set_local_statement_timeout
from app.db.inspection_read import get_inspection_read_db as get_inventory_read_db
from app.schemas.inventory import (
    InitialInventoryBulkIn,
    InitialInventoryBulkResultOut,
    ProductInventoryAdjustmentIn,
    ProductInventoryConsistencyListOut,
    ProductInventoryListOut,
    ProductInventoryMovementListOut,
    ProductInventoryMovementOut,
    ProductInventoryLotListOut,
    ProductInventoryLotAdjustmentIn,
)
from app.services.product_inventory_adjustment_service import (
    adjust_product_inventory_in_session,
    build_product_inventory_movement_out,
)
from app.services.product_inventory_initial_bulk_service import upload_initial_inventory_bulk_in_session
from app.services.product_inventory_query import (
    list_product_inventories,
    list_product_inventory_consistency,
    list_product_inventory_movements,
    list_product_inventory_lots,
)

router = APIRouter(prefix="/inventories", tags=["Inventory"])


@router.get("", response_model=ProductInventoryListOut)
def list_inventories(
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=200),
    q: Optional[str] = Query(None),
    include_zero: bool = False,
    db: Session = Depends(get_db),
):
    return list_product_inventories(db, page=page, size=size, q=q, include_zero=include_zero)


@router.get("/movements", response_model=ProductInventoryMovementListOut)
def list_inventory_movements(
    product_id: Optional[int] = Query(None, ge=1),
    movement_type: Optional[str] = Query(None),
    product_inventory_lot_id: Optional[int] = Query(None, ge=1),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=200),
    stock_page: Optional[int] = Query(None, ge=1),
    stock_size: int = Query(50, ge=1, le=200),
    stock_q: Optional[str] = None,
    stock_include_zero: bool = False,
    db: Session = Depends(get_inventory_read_db),
):
    return list_product_inventory_movements(
        db,
        product_id=product_id,
        movement_type=movement_type,
        product_inventory_lot_id=product_inventory_lot_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
        stock_page=stock_page,
        stock_size=stock_size,
        stock_q=stock_q,
        stock_include_zero=stock_include_zero,
    )


@router.get("/consistency", response_model=ProductInventoryConsistencyListOut)
def list_inventory_consistency(db: Session = Depends(get_db)):
    return list_product_inventory_consistency(db)


@router.get("/{product_id}/lots", response_model=ProductInventoryLotListOut)
def list_inventory_lots(
    product_id: Annotated[int, Path(ge=1)], q: Optional[str] = None, include_zero: bool = False,
    page: int = Query(1, ge=1), size: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_inventory_read_db),
):
    return list_product_inventory_lots(db, product_id=product_id, q=q,
        include_zero=include_zero, page=page, size=size)


@router.post("/{product_id}/lots/{product_inventory_lot_id}/adjust",
             response_model=ProductInventoryMovementOut, status_code=status.HTTP_201_CREATED)
def adjust_inventory_lot(
    product_id: Annotated[int, Path(ge=1)], product_inventory_lot_id: Annotated[int, Path(ge=1)],
    payload: ProductInventoryLotAdjustmentIn, direction: str = Query(...),
    db: Session = Depends(get_db),
):
    # A distinct route prevents an older server from ignoring the selected LOT and using FIFO.
    return adjust_inventory(product_id, ProductInventoryAdjustmentIn(qty=payload.qty,
        memo=payload.memo, product_inventory_lot_id=product_inventory_lot_id), direction, db)


@router.post(
    "/{product_id}/adjust",
    response_model=ProductInventoryMovementOut,
    status_code=status.HTTP_201_CREATED,
)
def adjust_inventory(
    product_id: int,
    payload: ProductInventoryAdjustmentIn,
    direction: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        result = adjust_product_inventory_in_session(
            db,
            product_id=product_id,
            payload=payload,
            direction=direction,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    db.refresh(result.movement)
    return build_product_inventory_movement_out(movement=result.movement, product=result.product)


@router.post("/initial-bulk", response_model=InitialInventoryBulkResultOut)
def upload_initial_inventory_bulk(
    payload: InitialInventoryBulkIn,
    db: Session = Depends(get_db),
):
    try:
        set_local_statement_timeout(db)
        result = upload_initial_inventory_bulk_in_session(db, payload)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
