"""Read-only LOT balances at a saved inspection's inventory posting boundary.

This projection is never an availability source for editing or shipment validation.
"""
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.inspection_result import InspectionResult
from app.models.lot import Lot
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.schemas.inspection_result import InspectionInventorySummaryOut
from app.schemas.inspection_schedule import InspectionStockLotOut
from app.services.ship_qty_policy import build_shipment_progress


def project_saved_inventory(
    db: Session, *, result: InspectionResult, summary: InspectionInventorySummaryOut,
) -> InspectionInventorySummaryOut:
    movement = ProductInventoryMovement
    saved = summary.model_copy(update={
        "view_mode": "saved", "stock_lots": [], "current_stock_qty": 0,
        "physical_stock_qty": 0, "stock_error": None,
        "already_shipped_qty": 0, "prior_shipped_qty": 0,
        "remaining_ship_target_qty": 0, "remaining_before_current_result_qty": 0,
    })
    anchor = db.execute(select(movement.inventory_movement_id, movement.created_at).where(
        movement.product_id == summary.product_id,
        movement.inspection_result_id == result.inspection_result_id,
    ).order_by(movement.inventory_movement_id.desc()).limit(1)).first()
    if anchor is not None:
        # Per-product inventory locks serialize postings. IDs also distinguish transactions
        # with equal timestamps; metadata-only edits must not advance this boundary.
        cutoff = movement.inventory_movement_id <= anchor.inventory_movement_id
        saved.stock_as_of = anchor.created_at
    else:
        # A zero-quantity/legacy unposted round has no movement anchor. Its original
        # creation time is usable only when no inventory posting ties that timestamp.
        saved.stock_as_of = result.created_at
        tied = db.execute(select(movement.inventory_movement_id).where(
            movement.product_id == summary.product_id, movement.created_at == result.created_at,
        ).limit(1)).first()
        if tied is not None:
            saved.stock_error = "저장 시점의 재고 처리 순서를 확인할 수 없습니다. 당시 재고 조회가 불가합니다."
            return saved
        cutoff = movement.created_at < result.created_at

    balances = db.execute(select(
        movement.product_inventory_lot_id,
        func.sum(movement.qty).label("current_qty"),
        func.sum(case((cutoff, movement.qty), else_=0)).label("saved_qty"),
    ).where(movement.product_id == summary.product_id)
        .group_by(movement.product_inventory_lot_id)).all()
    lot_rows = db.execute(select(ProductInventoryLot, Lot.lot_id).outerjoin(Lot, and_(
        Lot.product_id == ProductInventoryLot.product_id, Lot.lot_no == ProductInventoryLot.lot_no,
    )).where(ProductInventoryLot.product_id == summary.product_id)
        .order_by(ProductInventoryLot.created_at, ProductInventoryLot.product_inventory_lot_id)).all()
    lots = {row.product_inventory_lot_id: (row, production_id) for row, production_id in lot_rows}
    totals = {row.product_inventory_lot_id: row for row in balances}
    # Never substitute current stock or a product-wide balance for a missing LOT history.
    if (any(key not in lots for key in totals)
        or sum(int(row.current_qty) for row, _ in lot_rows) != summary.physical_stock_qty
        or any(int(row.current_qty) != int(totals[key].current_qty if key in totals else 0)
               for key, (row, _) in lots.items())
        or any(int(row.saved_qty) < 0 for row in balances)):
        saved.stock_error = "LOT별 수불 이력과 재고가 일치하지 않아 저장 당시 재고를 확인할 수 없습니다."
        return saved

    shipped_by_lot = {row.product_inventory_lot_id: row.allocated_ship_qty
                      for row in summary.stock_lots if row.allocated_ship_qty}
    for key, (lot, production_id) in lots.items():
        qty = int(totals[key].saved_qty) if key in totals else 0
        shipped = shipped_by_lot.get(key, 0)
        if qty or shipped:
            saved.stock_lots.append(InspectionStockLotOut(
                lot_id=production_id or key, product_inventory_lot_id=key,
                production_lot_id=production_id, lot_no=lot.lot_no,
                stock_qty=qty, physical_qty=qty, allocated_ship_qty=shipped,
                created_date=lot.created_at,
            ))
    saved.current_stock_qty = sum(row.physical_qty for row in saved.stock_lots)
    saved.physical_stock_qty = saved.current_stock_qty
    total_ship, own_ship = db.execute(select(
        func.coalesce(func.sum(-movement.qty), 0),
        func.coalesce(func.sum(case((
            movement.inspection_result_id == result.inspection_result_id, -movement.qty,
        ), else_=0)), 0),
    ).where(movement.product_id == summary.product_id,
        movement.order_line_id == summary.order_line_id,
        movement.movement_type == "SHIP_OUT", cutoff)).one()
    progress = build_shipment_progress(ship_target_qty=summary.ship_target_qty,
        total_shipped_qty=int(total_ship), current_result_shipped_qty=int(own_ship))
    saved.already_shipped_qty = progress.total_shipped_qty
    saved.prior_shipped_qty = progress.prior_shipped_qty
    saved.current_result_shipped_qty = progress.current_result_shipped_qty
    saved.remaining_before_current_result_qty = progress.remaining_before_current_result_qty
    saved.remaining_ship_target_qty = progress.remaining_after_current_result_qty
    return saved
