from __future__ import annotations

from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.shipment_line import ShipmentLine
from app.schemas.inspection_result import (
    InspectionAccumulatedSummaryOut,
    InspectionInventorySummaryOut,
    InspectionResultGetOut,
    InspectionResultListItemOut,
    InspectionResultListOut,
    InspectionRoundSummaryOut,
)
from app.services.inventory_fifo_service import get_available_inventory_lots_fifo
from app.services.order_line_plan_service import (
    get_latest_plan_history,
    get_reserved_stock_shipment_qty,
)
from app.services.ship_qty_policy import calculate_ship_qty


def ensure_inspection_schedule(db: Session, inspection_schedule_id: int) -> InspectionSchedule:
    obj = db.execute(
        select(InspectionSchedule).where(
            InspectionSchedule.inspection_schedule_id == inspection_schedule_id
        )
    ).scalar_one_or_none()

    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="InspectionSchedule not found",
        )

    return obj


def get_accumulated_inspection_summary(
    db: Session,
    *,
    inspection_schedule_id: int,
) -> InspectionAccumulatedSummaryOut:
    current_schedule = ensure_inspection_schedule(db, inspection_schedule_id)
    lot_id = current_schedule.lot_id

    row = db.execute(
        select(
            func.coalesce(func.sum(InspectionResult.good_qty), 0),
            func.coalesce(func.sum(InspectionResult.defect_qty), 0),
            func.coalesce(func.sum(InspectionResult.defect_ship_qty), 0),
            func.coalesce(func.sum(InspectionResult.inspected_qty), 0),
            func.coalesce(func.sum(InspectionResult.uninspected_qty), 0),
            func.coalesce(func.sum(InspectionResult.discard_qty), 0),
        )
        .select_from(InspectionResult)
        .join(
            InspectionSchedule,
            InspectionSchedule.inspection_schedule_id == InspectionResult.inspection_schedule_id,
        )
        .where(
            InspectionSchedule.lot_id == lot_id,
            InspectionSchedule.inspection_schedule_id != inspection_schedule_id,
            InspectionSchedule.status.in_(("PARTIAL_DONE", "DONE")),
        )
    ).one()

    return InspectionAccumulatedSummaryOut(
        good_qty=int(row[0] or 0),
        defect_qty=int(row[1] or 0),
        defect_ship_qty=int(row[2] or 0),
        inspected_qty=int(row[3] or 0),
        uninspected_qty=int(row[4] or 0),
        received_qty=int(row[3] or 0) + int(row[4] or 0),
        discard_qty=int(row[5] or 0),
    )


def get_inspection_inventory_summary(
    db: Session,
    *,
    inspection_schedule_id: int,
    current_result_id: int | None,
) -> InspectionInventorySummaryOut:
    current_schedule = ensure_inspection_schedule(db, inspection_schedule_id)

    lot = db.execute(select(Lot).where(Lot.lot_id == current_schedule.lot_id)).scalar_one_or_none()
    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lot not found",
        )

    order_line = db.execute(
        select(OrderLine).where(OrderLine.order_line_id == lot.order_line_id)
    ).scalar_one_or_none()
    if order_line is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OrderLine not found",
        )

    partner = db.get(Partner, order_line.partner_id)
    partner_name = partner.name if partner else ""

    current_result_stock_ship_qty = 0
    current_result_result_ship_qty = 0
    current_result_stock_in_qty = 0
    current_result_discard_qty = 0

    inventory_total_qty = int(
        db.execute(
            select(func.coalesce(ProductInventory.current_qty, 0)).where(
                ProductInventory.product_id == lot.product_id
            )
        ).scalar_one_or_none()
        or 0
    )

    available_stock_lots = get_available_inventory_lots_fifo(
        db,
        product_id=lot.product_id,
        exclude_lot_no=lot.lot_no,
        exclude_inspection_result_id=current_result_id,
    )
    lot_available_qty = sum(available_qty for _, available_qty in available_stock_lots)
    reserved_for_order_line_qty = get_reserved_stock_shipment_qty(
        db,
        product_id=lot.product_id,
        order_line_id=order_line.order_line_id,
    )
    current_stock_qty = min(
        max(inventory_total_qty, 0),
        lot_available_qty + reserved_for_order_line_qty,
    )

    if current_result_id is not None:
        result = db.get(InspectionResult, current_result_id)
        if result is not None:
            current_result_discard_qty = int(result.discard_qty or 0)

        current_result_stock_ship_qty = int(
            db.execute(
                select(func.coalesce(func.sum(ShipmentLine.ship_qty), 0)).where(
                    ShipmentLine.inspection_result_id == current_result_id,
                    ShipmentLine.source_type == "STOCK",
                    ShipmentLine.status != "CANCELED",
                )
            ).scalar_one()
            or 0
        )
        current_stock_qty += current_result_stock_ship_qty

        current_result_result_ship_qty = int(
            db.execute(
                select(func.coalesce(func.sum(ShipmentLine.ship_qty), 0)).where(
                    ShipmentLine.inspection_result_id == current_result_id,
                    ShipmentLine.source_type == "INSPECTION_RESULT",
                    ShipmentLine.status != "CANCELED",
                )
            ).scalar_one()
            or 0
        )

        sellable_qty = 0
        if result is not None:
            if result.is_partial:
                sellable_qty = 0
            else:
                accumulated = get_accumulated_inspection_summary(
                    db,
                    inspection_schedule_id=inspection_schedule_id,
                )
                sellable_qty = (
                    int(accumulated.good_qty or 0)
                    + int(accumulated.defect_ship_qty or 0)
                    + int(result.good_qty or 0)
                    + int(result.defect_ship_qty or 0)
                )

        current_result_stock_in_qty = max(
            sellable_qty - current_result_result_ship_qty - current_result_discard_qty,
            0,
        )

    else:
        latest_plan = get_latest_plan_history(db, order_line.order_line_id)
        if latest_plan is not None:
            current_result_stock_ship_qty = min(
                reserved_for_order_line_qty or int(latest_plan.stock_ship_qty or 0),
                current_stock_qty,
            )

    ship_target_qty = calculate_ship_qty(partner_name, int(order_line.order_qty))

    shipped_query = select(func.coalesce(func.sum(-ProductInventoryMovement.qty), 0)).where(
        ProductInventoryMovement.order_line_id == order_line.order_line_id,
        ProductInventoryMovement.movement_type == "SHIP_OUT",
    )

    already_shipped_qty = db.execute(shipped_query).scalar_one()
    already_shipped_qty = int(already_shipped_qty or 0)

    remaining_ship_target_qty = max(ship_target_qty - already_shipped_qty, 0)

    return InspectionInventorySummaryOut(
        product_id=int(lot.product_id),
        order_line_id=int(order_line.order_line_id),
        current_stock_qty=current_stock_qty,
        order_qty=int(order_line.order_qty),
        ship_target_qty=ship_target_qty,
        already_shipped_qty=already_shipped_qty,
        remaining_ship_target_qty=remaining_ship_target_qty,
        current_result_stock_ship_qty=current_result_stock_ship_qty,
        current_result_result_ship_qty=current_result_result_ship_qty,
        current_result_stock_in_qty=current_result_stock_in_qty,
        current_result_discard_qty=current_result_discard_qty,
    )


def list_inspection_results_for_grid(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    partner_q: str | None = None,
    product_q: str | None = None,
    lot_q: str | None = None,
    page: int = 1,
    size: int = 100,
) -> InspectionResultListOut:
    inspection_round_sq = (
        select(
            InspectionSchedule.inspection_schedule_id.label("inspection_schedule_id"),
            func.row_number()
            .over(
                partition_by=InspectionSchedule.lot_id,
                order_by=(
                    InspectionSchedule.inspection_date.asc(),
                    InspectionSchedule.inspection_schedule_id.asc(),
                ),
            )
            .label("inspection_round"),
            func.count()
            .over(partition_by=InspectionSchedule.lot_id)
            .label("inspection_round_count"),
        )
        .select_from(InspectionSchedule)
        .join(
            InspectionResult,
            InspectionResult.inspection_schedule_id
            == InspectionSchedule.inspection_schedule_id,
        )
        .where(InspectionSchedule.status.in_(("PARTIAL_DONE", "DONE")))
        .subquery()
    )

    result_ship_sq = (
        select(
            ShipmentLine.inspection_result_id.label("inspection_result_id"),
            func.coalesce(func.sum(ShipmentLine.ship_qty), 0).label("result_ship_qty"),
        )
        .where(
            ShipmentLine.source_type == "INSPECTION_RESULT",
            ShipmentLine.status != "CANCELED",
        )
        .group_by(ShipmentLine.inspection_result_id)
        .subquery()
    )

    inventory_in_sq = (
        select(
            ProductInventoryMovement.inspection_result_id.label("inspection_result_id"),
            func.coalesce(func.sum(ProductInventoryMovement.qty), 0).label("inventory_in_qty"),
        )
        .where(
            ProductInventoryMovement.movement_type == "INSPECTION_IN",
            ProductInventoryMovement.source_type == "INSPECTION_RESULT_IN",
        )
        .group_by(ProductInventoryMovement.inspection_result_id)
        .subquery()
    )

    stmt = (
        select(
            InspectionResult.inspection_result_id,
            InspectionSchedule.inspection_schedule_id,
            Lot.lot_id,
            Lot.lot_no,
            InspectionSchedule.inspection_date,
            InspectionSchedule.status.label("schedule_status"),
            inspection_round_sq.c.inspection_round,
            inspection_round_sq.c.inspection_round_count,
            InspectionResult.is_partial,
            InspectionResult.next_inspection_date,
            InspectionResult.partial_reason,
            OrderLine.due_date,
            Partner.name.label("partner_name"),
            Product.product_code,
            Product.product_name,
            Lot.lot_qty,
            OrderLine.order_qty,
            InspectionResult.good_qty,
            InspectionResult.uninspected_qty,
            (InspectionResult.inspected_qty + InspectionResult.uninspected_qty).label("received_qty"),
            func.coalesce(result_ship_sq.c.result_ship_qty, 0).label("result_ship_qty"),
            InspectionResult.discard_qty,
            (
                func.coalesce(inventory_in_sq.c.inventory_in_qty, 0)
                - func.coalesce(result_ship_sq.c.result_ship_qty, 0)
            ).label("stock_in_qty"),
            InspectionResult.defect_qty,
            InspectionResult.created_by,
            InspectionResult.created_at,
            InspectionResult.updated_at,
            InspectionResult.memo,
        )
        .select_from(InspectionResult)
        .join(
            InspectionSchedule,
            InspectionSchedule.inspection_schedule_id == InspectionResult.inspection_schedule_id,
        )
        .join(Lot, Lot.lot_id == InspectionSchedule.lot_id)
        .join(
            inspection_round_sq,
            inspection_round_sq.c.inspection_schedule_id
            == InspectionSchedule.inspection_schedule_id,
        )
        .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
        .join(Partner, Partner.partner_id == OrderLine.partner_id)
        .join(Product, Product.product_id == Lot.product_id)
        .outerjoin(
            result_ship_sq,
            result_ship_sq.c.inspection_result_id == InspectionResult.inspection_result_id,
        )
        .outerjoin(
            inventory_in_sq,
            inventory_in_sq.c.inspection_result_id == InspectionResult.inspection_result_id,
        )
        .where(InspectionSchedule.status.in_(("PARTIAL_DONE", "DONE")))
    )

    if date_from is not None:
        stmt = stmt.where(InspectionSchedule.inspection_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(InspectionSchedule.inspection_date <= date_to)
    if q and q.strip():
        keyword = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Partner.name.ilike(keyword),
                Product.product_name.ilike(keyword),
                Product.product_code.ilike(keyword),
                Lot.lot_no.ilike(keyword),
            )
        )
    if partner_q and partner_q.strip():
        stmt = stmt.where(Partner.name.ilike(f"%{partner_q.strip()}%"))
    if product_q and product_q.strip():
        product_keyword = f"%{product_q.strip()}%"
        stmt = stmt.where(
            or_(
                Product.product_name.ilike(product_keyword),
                Product.product_code.ilike(product_keyword),
            )
        )
    if lot_q and lot_q.strip():
        stmt = stmt.where(Lot.lot_no.ilike(f"%{lot_q.strip()}%"))

    filtered_results = stmt.subquery()
    nonnegative_stock_in_qty = case(
        (filtered_results.c.stock_in_qty < 0, 0),
        else_=filtered_results.c.stock_in_qty,
    )
    summary = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(filtered_results.c.good_qty), 0),
            func.coalesce(func.sum(filtered_results.c.uninspected_qty), 0),
            func.coalesce(func.sum(filtered_results.c.received_qty), 0),
            func.coalesce(func.sum(filtered_results.c.result_ship_qty), 0),
            func.coalesce(func.sum(filtered_results.c.discard_qty), 0),
            func.coalesce(func.sum(nonnegative_stock_in_qty), 0),
            func.coalesce(func.sum(filtered_results.c.defect_qty), 0),
        ).select_from(filtered_results)
    ).one()

    stmt = stmt.order_by(
        InspectionSchedule.inspection_date.desc(),
        InspectionResult.updated_at.desc(),
        InspectionResult.inspection_result_id.desc(),
    ).offset((page - 1) * size).limit(size)

    rows = db.execute(stmt).mappings().all()
    return InspectionResultListOut(
        items=[
            InspectionResultListItemOut(
                inspection_result_id=int(row["inspection_result_id"]),
                inspection_schedule_id=int(row["inspection_schedule_id"]),
                lot_id=int(row["lot_id"]),
                lot_no=str(row["lot_no"] or ""),
                inspection_date=row["inspection_date"],
                schedule_status=str(row["schedule_status"]),
                inspection_round=int(row["inspection_round"] or 0),
                inspection_round_count=int(row["inspection_round_count"] or 0),
                is_partial=bool(row["is_partial"]),
                next_inspection_date=row["next_inspection_date"],
                partial_reason=row["partial_reason"],
                due_date=row["due_date"],
                partner_name=str(row["partner_name"] or ""),
                product_code=str(row["product_code"] or ""),
                product_name=str(row["product_name"] or ""),
                lot_qty=int(row["lot_qty"] or 0),
                order_qty=int(row["order_qty"] or 0),
                good_qty=int(row["good_qty"] or 0),
                uninspected_qty=int(row["uninspected_qty"] or 0),
                received_qty=int(row["received_qty"] or 0),
                result_ship_qty=int(row["result_ship_qty"] or 0),
                discard_qty=int(row["discard_qty"] or 0),
                stock_in_qty=max(int(row["stock_in_qty"] or 0), 0),
                defect_qty=int(row["defect_qty"] or 0),
                created_by=row["created_by"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                memo=row["memo"],
            )
            for row in rows
        ],
        total_count=int(summary[0] or 0),
        page=page,
        size=size,
        total_good_qty=int(summary[1] or 0),
        total_uninspected_qty=int(summary[2] or 0),
        total_received_qty=int(summary[3] or 0),
        total_result_ship_qty=int(summary[4] or 0),
        total_discard_qty=int(summary[5] or 0),
        total_stock_in_qty=int(summary[6] or 0),
        total_defect_qty=int(summary[7] or 0),
    )


def get_inspection_result_detail(
    db: Session,
    inspection_schedule_id: int,
) -> InspectionResultGetOut:
    schedule = ensure_inspection_schedule(db, inspection_schedule_id)

    result = db.execute(
        select(InspectionResult).where(
            InspectionResult.inspection_schedule_id == inspection_schedule_id
        )
    ).scalar_one_or_none()

    accumulated = get_accumulated_inspection_summary(
        db,
        inspection_schedule_id=inspection_schedule_id,
    )

    inventory = get_inspection_inventory_summary(
        db,
        inspection_schedule_id=inspection_schedule_id,
        current_result_id=result.inspection_result_id if result else None,
    )

    rounds = _get_inspection_rounds(db, lot_id=schedule.lot_id)
    inspection_round = next(
        (
            row.inspection_round
            for row in rounds
            if row.inspection_schedule_id == inspection_schedule_id
        ),
        0,
    )

    return InspectionResultGetOut(
        result=result,
        schedule_status=schedule.status,
        inspection_round=inspection_round,
        inspection_round_count=len(rounds),
        rounds=rounds,
        accumulated=accumulated,
        inventory=inventory,
    )


def _get_inspection_rounds(
    db: Session,
    *,
    lot_id: int,
) -> list[InspectionRoundSummaryOut]:
    rows = (
        db.execute(
            select(InspectionSchedule, InspectionResult)
            .join(
                InspectionResult,
                InspectionResult.inspection_schedule_id
                == InspectionSchedule.inspection_schedule_id,
            )
            .where(
                InspectionSchedule.lot_id == lot_id,
                InspectionSchedule.status.in_(("PARTIAL_DONE", "DONE")),
            )
            .order_by(
                InspectionSchedule.inspection_date.asc(),
                InspectionSchedule.inspection_schedule_id.asc(),
            )
        )
        .all()
    )

    return [
        InspectionRoundSummaryOut(
            inspection_result_id=result.inspection_result_id,
            inspection_schedule_id=schedule.inspection_schedule_id,
            inspection_date=schedule.inspection_date,
            schedule_status=schedule.status,
            inspection_round=index,
            is_partial=result.is_partial,
            next_inspection_date=result.next_inspection_date,
            partial_reason=result.partial_reason,
            good_qty=int(result.good_qty or 0),
            defect_ship_qty=int(result.defect_ship_qty or 0),
            defect_qty=int(result.defect_qty or 0),
            inspected_qty=int(result.inspected_qty or 0),
            uninspected_qty=int(result.uninspected_qty or 0),
            received_qty=int(result.received_qty or 0),
            memo=result.memo,
            created_by=result.created_by,
            created_at=result.created_at,
        )
        for index, (schedule, result) in enumerate(rows, start=1)
    ]
