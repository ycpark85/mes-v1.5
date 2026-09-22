from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.product_inventory_lot import ProductInventoryLot
from app.schemas.inspection_schedule import (
    InspectionScheduleOut,
    InspectionStockLotListOut,
    InspectionStockLotOut,
)
from app.services.inspection_stock_service import InspectionStockContext, get_inspection_stock_context


def get_inspection_schedule_detail(
    db: Session,
    inspection_schedule_id: int,
) -> InspectionScheduleOut:
    schedule = db.get(InspectionSchedule, inspection_schedule_id)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inspection schedule not found",
        )

    return InspectionScheduleOut.model_validate(schedule, from_attributes=True)


def list_inspection_stock_lots(
    db: Session,
    inspection_schedule_id: int,
) -> InspectionStockLotListOut:
    schedule = db.get(InspectionSchedule, inspection_schedule_id)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inspection schedule not found",
        )

    current_lot = db.get(Lot, schedule.lot_id)
    if current_lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lot not found",
        )

    current_result_id = db.execute(
        select(InspectionResult.inspection_result_id)
        .where(InspectionResult.inspection_schedule_id == inspection_schedule_id)
        .limit(1)
    ).scalar_one_or_none()

    stock = get_inspection_stock_context(db, product_id=current_lot.product_id,
        order_line_id=current_lot.order_line_id, result_id=current_result_id)
    return build_inspection_stock_lot_list(db, product_id=current_lot.product_id, stock=stock)


def build_inspection_stock_lot_list(
    db: Session, *, product_id: int, stock: InspectionStockContext,
) -> InspectionStockLotListOut:
    """Project one captured stock context for both the detail and compatibility endpoint."""
    production_ids = dict(db.execute(select(Lot.lot_no, Lot.lot_id).join(
        ProductInventoryLot,
        (ProductInventoryLot.product_id == Lot.product_id) & (ProductInventoryLot.lot_no == Lot.lot_no),
    ).where(Lot.product_id == product_id)).all()) if stock.lots else {}
    items = [InspectionStockLotOut(
            lot_id=production_ids.get(row.lot.lot_no) or row.lot.product_inventory_lot_id,
            production_lot_id=production_ids.get(row.lot.lot_no),
            product_inventory_lot_id=row.lot.product_inventory_lot_id,
            lot_no=row.lot.lot_no, stock_qty=row.stock_qty,
            physical_qty=int(row.lot.current_qty), reserved_qty=row.reserved_qty,
            other_reserved_qty=row.other_reserved_qty,
            allocated_ship_qty=row.current_shipped_qty, created_date=row.lot.created_at,
        ) for row in stock.lots]
    return InspectionStockLotListOut(items=items, total_stock_qty=stock.available_qty,
        physical_stock_qty=stock.physical_qty, stock_error=stock.error)
