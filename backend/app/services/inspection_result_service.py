from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import KOREA_TIME_ZONE, UTC, utc_now
from app.models.defect_type import DefectType
from app.models.inspection_defect import InspectionDefect
from app.models.inspection_defect_attachment import InspectionDefectAttachment
from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.schemas.inspection_result import DefectLineIn
from app.models.product_inventory import ProductInventory
from app.models.product_inventory_lot import ProductInventoryLot
from app.models.product_inventory_movement import ProductInventoryMovement
from app.models.shipment_line import ShipmentLine
from app.services.inventory_fifo_service import allocate_inventory_lots_fifo
from app.services.inspection_schedule_service import (
    sync_lot_status_from_inspection_schedules,
)
from app.services.production_daily_query import (
    refresh_order_line_snapshots_for_lots,
    refresh_order_line_snapshots_for_product,
)
from app.services.inspection_quantity_policy import (
    InspectionQuantityError,
    build_inspection_quantity_plan,
)
from app.services.ship_qty_policy import build_shipment_progress, calculate_ship_qty


def _utcnow() -> datetime:
    return utc_now()


def _normalize_concurrency_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=KOREA_TIME_ZONE)
    return value.astimezone(UTC)


def _timestamps_match(current: datetime, expected: datetime) -> bool:
    return _normalize_concurrency_timestamp(current) == _normalize_concurrency_timestamp(
        expected
    )


def _get_prior_unsettled_results(
    db: Session,
    *,
    lot_id: int,
    current_schedule_id: int,
) -> list[InspectionResult]:
    return (
        db.execute(
            select(InspectionResult)
            .join(
                InspectionSchedule,
                InspectionSchedule.inspection_schedule_id
                == InspectionResult.inspection_schedule_id,
            )
            .where(
                InspectionSchedule.lot_id == lot_id,
                InspectionSchedule.inspection_schedule_id != current_schedule_id,
                InspectionSchedule.status == "PARTIAL_DONE",
                InspectionResult.settled_at.is_(None),
            )
            .order_by(
                InspectionSchedule.inspection_date.asc(),
                InspectionSchedule.inspection_schedule_id.asc(),
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )


def _validate_lot_received_quantity(
    db: Session,
    *,
    schedule: InspectionSchedule,
    current_result_id: int | None,
    current_received_qty: int,
    is_partial: bool,
) -> None:
    lot = (
        db.execute(
            select(Lot)
            .where(Lot.lot_id == schedule.lot_id)
            .with_for_update()
        )
        .scalar_one_or_none()
    )
    if lot is None:
        raise HTTPException(status_code=404, detail="lot not found")

    # LOT quantity is a production plan, not a cap on actual inspected quantity.
    # Additional production may still await inspection after a split meets the plan.
    if is_partial:
        return

    prior_query = (
        select(
            func.coalesce(
                func.sum(
                    InspectionResult.inspected_qty
                    + InspectionResult.uninspected_qty
                ),
                0,
            )
        )
        .join(
            InspectionSchedule,
            InspectionSchedule.inspection_schedule_id
            == InspectionResult.inspection_schedule_id,
        )
        .where(
            InspectionSchedule.lot_id == schedule.lot_id,
            InspectionSchedule.status.in_(("PARTIAL_DONE", "DONE")),
        )
    )
    if current_result_id is not None:
        prior_query = prior_query.where(
            InspectionResult.inspection_result_id != current_result_id
        )

    prior_received_qty = int(db.execute(prior_query).scalar_one() or 0)
    accumulated_received_qty = prior_received_qty + current_received_qty
    lot_qty = int(lot.lot_qty or 0)

    if accumulated_received_qty < lot_qty:
        raise HTTPException(
            status_code=422,
            detail=(
                "최종검수의 누적 처리수량(미검수 포함)은 LOT 계획수량 이상이어야 합니다. "
                f"LOT 계획수량: {lot_qty}, 누적 처리수량: {accumulated_received_qty}"
            ),
        )





def upsert_inspection_result(
    db: Session,
    inspection_schedule_id: int,
    *,
    good_qty: int,
    defect_ship_qty: int,
    defect_qty: int,
    uninspected_qty: int,
    stock_ship_qty: int,
    result_ship_qty: int,
    stock_in_qty: int,
    discard_qty: int,
    is_partial: bool,
    next_inspection_date: Optional[date],
    partial_reason: Optional[str],
    memo: Optional[str],
    defects: Sequence[DefectLineIn],
    actor: str,
    expected_updated_at: Optional[datetime] = None,
) -> tuple[InspectionResult, str, Optional[int]]:
    """
    - 신규 저장은 IN_PROGRESS, 기존 최종 실적 수정은 DONE에서 허용
    - inspected_qty = good_qty + defect_ship_qty + defect_qty (서버 계산)
    - sellable_qty = good_qty + defect_ship_qty
    - split and final rounds both settle inspected sellable quantity immediately
    - production shipment + stock-in + disposal equals current sellable qty plus legacy carry-in
    - defects/attachments: 전체 삭제 후 재삽입
    - is_partial=true: schedule=PARTIAL_DONE + next schedule 자동 생성(RECEIVED)
    - is_partial=false: schedule=DONE + 재고/출하 반영
    """
    sch = db.execute(
        select(InspectionSchedule)
        .where(InspectionSchedule.inspection_schedule_id == inspection_schedule_id)
        .with_for_update()
    ).scalar_one_or_none()
    if not sch:
        raise HTTPException(status_code=404, detail="inspection_schedule not found")

    result = db.execute(
        select(InspectionResult).where(InspectionResult.inspection_schedule_id == inspection_schedule_id)
    ).scalar_one_or_none()

    if sch.status not in ("IN_PROGRESS", "DONE"):
        raise HTTPException(status_code=409, detail="Only IN_PROGRESS or DONE schedule can be saved as result")

    if sch.status == "DONE" and result is None:
        raise HTTPException(status_code=409, detail="DONE schedule result not found")

    if (
        result is not None
        and expected_updated_at is not None
        and not _timestamps_match(result.updated_at, expected_updated_at)
    ):
        raise HTTPException(
            status_code=409,
            detail="Inspection result was modified by another user. Reload and try again.",
        )

    if sch.status == "DONE" and is_partial:
        raise HTTPException(status_code=409, detail="DONE schedule cannot be changed to partial inspection")

    if is_partial:
        if not next_inspection_date:
            raise HTTPException(status_code=422, detail="next_inspection_date is required when is_partial=true")
        partial_reason = (partial_reason or "").strip()
        if not partial_reason:
            raise HTTPException(
                status_code=422,
                detail="partial_reason is required when is_partial=true",
            )
    else:
        next_inspection_date = None
        partial_reason = None

    prior_unsettled_results = _get_prior_unsettled_results(
        db,
        lot_id=sch.lot_id,
        current_schedule_id=inspection_schedule_id,
    )
    prior_unsettled_sellable_qty = sum(
        int(row.good_qty or 0) + int(row.defect_ship_qty or 0)
        for row in prior_unsettled_results
    )
    try:
        quantity_plan = build_inspection_quantity_plan(
            is_partial=is_partial,
            good_qty=good_qty,
            defect_ship_qty=defect_ship_qty,
            defect_qty=defect_qty,
            stock_ship_qty=stock_ship_qty,
            result_ship_qty=result_ship_qty,
            stock_in_qty=stock_in_qty,
            discard_qty=discard_qty,
            uninspected_qty=uninspected_qty,
            prior_unsettled_sellable_qty=prior_unsettled_sellable_qty,
        )
    except InspectionQuantityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    inspected_qty = quantity_plan.inspected_qty
    stock_ship_qty = quantity_plan.stock_ship_qty
    result_ship_qty = quantity_plan.result_ship_qty
    stock_in_qty = quantity_plan.stock_in_qty
    discard_qty = quantity_plan.discard_qty
    uninspected_qty = quantity_plan.uninspected_qty

    _validate_lot_received_quantity(
        db,
        schedule=sch,
        current_result_id=result.inspection_result_id if result is not None else None,
        current_received_qty=inspected_qty + uninspected_qty,
        is_partial=is_partial,
    )

    if defects:
        defect_type_ids = sorted({d.defect_type_id for d in defects})
        rows = db.execute(
            select(DefectType.defect_type_id).where(
                DefectType.defect_type_id.in_(defect_type_ids),
                DefectType.is_active.is_(True),
            )
        ).scalars().all()

        if set(rows) != set(defect_type_ids):
            raise HTTPException(status_code=422, detail="Invalid or inactive defect_type_id exists")

    now = _utcnow()

    if result is None:
        result = InspectionResult(
            inspection_schedule_id=inspection_schedule_id,
            good_qty=good_qty,
            defect_ship_qty=defect_ship_qty,
            defect_qty=defect_qty,
            inspected_qty=inspected_qty,
            uninspected_qty=uninspected_qty,
            discard_qty=discard_qty,
            is_partial=is_partial,
            next_inspection_date=next_inspection_date,
            partial_reason=partial_reason,
            memo=memo,
            created_by=actor,
        )
        db.add(result)
        db.flush()
    else:
        result.good_qty = good_qty
        result.defect_ship_qty = defect_ship_qty
        result.defect_qty = defect_qty
        result.inspected_qty = inspected_qty
        result.uninspected_qty = uninspected_qty
        result.discard_qty = discard_qty
        result.is_partial = is_partial
        result.next_inspection_date = next_inspection_date
        result.partial_reason = partial_reason
        result.memo = memo
        db.flush()

    _replace_defects_and_attachments(
        db,
        inspection_result_id=result.inspection_result_id,
        defects=defects,
    )

    created_next_id: Optional[int] = None

    if is_partial:
        sch.status = "PARTIAL_DONE"
        sch.finished_at = now

        base_received_at = sch.received_at or now
        created_next_id = _create_next_schedule(
            db=db,
            lot_id=sch.lot_id,
            inspection_date=next_inspection_date,  # type: ignore[arg-type]
            received_at=base_received_at,
        )
    else:
        sch.status = "DONE"
        sch.finished_at = now

    db.flush()
    _apply_inventory_for_result(
        db=db,
        result=result,
        schedule=sch,
        stock_ship_qty=stock_ship_qty,
        result_ship_qty=result_ship_qty,
        stock_in_qty=stock_in_qty,
        settlement_sellable_qty=quantity_plan.settlement_sellable_qty,
    )
    result.settled_at = now
    result.settled_by = actor
    for prior_result in prior_unsettled_results:
        prior_result.settled_at = now
        prior_result.settled_by = actor

    db.flush()
    sync_lot_status_from_inspection_schedules(db, lot_id=sch.lot_id)

    refresh_order_line_snapshots_for_lots(db, {sch.lot_id})
    lot = db.get(Lot, sch.lot_id)
    if lot is not None:
        refresh_order_line_snapshots_for_product(db, lot.product_id)

    return result, sch.status, created_next_id

   


def _replace_defects_and_attachments(
    db: Session,
    *,
    inspection_result_id: int,
    defects: Sequence[DefectLineIn],
):
    defect_ids = db.execute(
        select(InspectionDefect.inspection_defect_id).where(
            InspectionDefect.inspection_result_id == inspection_result_id
        )
    ).scalars().all()

    if defect_ids:
        db.execute(
            delete(InspectionDefectAttachment).where(
                InspectionDefectAttachment.inspection_defect_id.in_(defect_ids)
            )
        )
        db.execute(
            delete(InspectionDefect).where(
                InspectionDefect.inspection_defect_id.in_(defect_ids)
            )
        )
        db.flush()

    for line in defects:
        defect = InspectionDefect(
            inspection_result_id=inspection_result_id,
            defect_type_id=line.defect_type_id,
            defect_qty=line.defect_qty,
            disposition=line.disposition,
            memo=line.memo,
        )
        db.add(defect)
        db.flush()

        for att in line.attachments:
            db.add(
                InspectionDefectAttachment(
                    inspection_defect_id=defect.inspection_defect_id,
                    file_uri=att.file_uri,
                    file_name=att.file_name,
                    mime_type=att.mime_type,
                    memo=att.memo,
                )
            )

    db.flush()


def _create_next_schedule(
    db: Session,
    *,
    lot_id: int,
    inspection_date: date,
    received_at: datetime,
) -> int:
    """
    - status=RECEIVED
    - day_seq: 동일 날짜(status!=CANCELED) row들을 FOR UPDATE로 잠금 후 파이썬 max+1
    """
    locked_seqs = db.execute(
        select(InspectionSchedule.day_seq)
        .where(
            InspectionSchedule.inspection_date == inspection_date,
            InspectionSchedule.status != "CANCELED",
        )
        .with_for_update()
    ).scalars().all()

    max_seq = 0
    for s in locked_seqs:
        if s is not None and int(s) > max_seq:
            max_seq = int(s)

    next_seq = max_seq + 1

    new_sch = InspectionSchedule(
        lot_id=lot_id,
        inspection_date=inspection_date,
        status="RECEIVED",
        received_at=received_at,
        day_seq=next_seq,
    )
    db.add(new_sch)

    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Duplicate (lot_id, inspection_date) is not allowed")

    return new_sch.inspection_schedule_id


def _get_fifo_stock_lot_allocations(
    db: Session,
    *,
    product_id: int,
    current_lot_no: str | None,
    inspection_result_id: int,
    stock_ship_qty: int,
) -> list[tuple[ProductInventoryLot, int]]:
    allocations, remaining_qty = allocate_inventory_lots_fifo(
        db,
        product_id=product_id,
        ship_qty=stock_ship_qty,
        exclude_lot_no=current_lot_no,
        exclude_inspection_result_id=inspection_result_id,
        for_update=True,
    )

    if remaining_qty > 0:
        raise HTTPException(
            status_code=422,
            detail="기존재고 출하대기 수량을 FIFO LOT 재고로 배정할 수 없습니다.",
        )

    return allocations


def _get_or_create_inventory_lot(
    db: Session,
    *,
    product_id: int,
    lot_no: str,
) -> ProductInventoryLot:
    inventory_lot = (
        db.execute(
            select(ProductInventoryLot)
            .where(
                ProductInventoryLot.product_id == product_id,
                ProductInventoryLot.lot_no == lot_no,
            )
            .with_for_update()
        )
        .scalar_one_or_none()
    )

    if inventory_lot is None:
        inventory_lot = ProductInventoryLot(
            product_id=product_id,
            lot_no=lot_no,
            current_qty=0,
        )
        db.add(inventory_lot)
        db.flush()

    return inventory_lot


def _add_ship_out_movement(
    db: Session,
    *,
    order_line: OrderLine,
    schedule: InspectionSchedule,
    inventory: ProductInventory,
    shipment_line: ShipmentLine,
    ship_qty: int,
    memo: str,
) -> None:
    db.add(
        ProductInventoryMovement(
            product_id=shipment_line.product_id,
            product_inventory_lot_id=shipment_line.product_inventory_lot_id,
            stock_lot_no=shipment_line.stock_lot_no,
            movement_type="SHIP_OUT",
            qty=-ship_qty,
            balance_after=inventory.current_qty,
            source_type="SHIPMENT_LINE",
            source_id=shipment_line.shipment_line_id,
            order_line_id=order_line.order_line_id,
            inspection_schedule_id=schedule.inspection_schedule_id,
            inspection_result_id=shipment_line.inspection_result_id,
            memo=memo,
        )
    )


def _create_completed_stock_shipment_lines_by_fifo(
    db: Session,
    *,
    order_line: OrderLine,
    schedule: InspectionSchedule,
    inventory: ProductInventory,
    product_id: int,
    current_lot_no: str | None,
    inspection_result_id: int,
    stock_ship_qty: int,
) -> None:
    shipped_at = _utcnow()
    allocations = _get_fifo_stock_lot_allocations(
        db,
        product_id=product_id,
        current_lot_no=current_lot_no,
        inspection_result_id=inspection_result_id,
        stock_ship_qty=stock_ship_qty,
    )

    for inventory_lot, ship_qty in allocations:
        stock_lot = (
            db.execute(
                select(Lot)
                .where(
                    Lot.product_id == product_id,
                    Lot.lot_no == inventory_lot.lot_no,
                )
                .limit(1)
            )
            .scalar_one_or_none()
        )

        inventory_lot.current_qty -= ship_qty
        inventory.current_qty -= ship_qty

        shipment_line = ShipmentLine(
            order_line_id=order_line.order_line_id,
            product_id=product_id,
            product_inventory_lot_id=inventory_lot.product_inventory_lot_id,
            stock_lot_no=inventory_lot.lot_no,
            lot_id=stock_lot.lot_id if stock_lot else None,
            inspection_result_id=inspection_result_id,
            source_type="STOCK",
            status="DONE",
            ship_qty=ship_qty,
            shipped_qty=ship_qty,
            shipped_at=shipped_at,
            memo="검수실적 저장 시 기존재고 출고 처리",
        )
        db.add(shipment_line)
        db.flush()

        _add_ship_out_movement(
            db,
            order_line=order_line,
            schedule=schedule,
            inventory=inventory,
            shipment_line=shipment_line,
            ship_qty=ship_qty,
            memo=f"검수실적 저장 기존재고 출고 / shipment_line_id={shipment_line.shipment_line_id}",
        )


def _cancel_waiting_stock_reservations_for_order_line(
    db: Session,
    *,
    order_line_id: int,
) -> None:
    waiting_lines = (
        db.execute(
            select(ShipmentLine)
            .where(
                ShipmentLine.order_line_id == order_line_id,
                ShipmentLine.source_type == "STOCK",
                ShipmentLine.status == "WAITING",
                ShipmentLine.inspection_result_id.is_(None),
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )

    for line in waiting_lines:
        line.status = "CANCELED"
        line.shipped_qty = 0
        line.memo = f"{line.memo or ''} / 검수 완료 후 미사용 예약 해제".strip()


def _consume_waiting_stock_reservations(
    db: Session,
    *,
    order_line: OrderLine,
    schedule: InspectionSchedule,
    inventory: ProductInventory,
    product_id: int,
    inspection_result_id: int,
    stock_ship_qty: int,
    release_unused_reservations: bool,
) -> int:
    if stock_ship_qty <= 0:
        if release_unused_reservations:
            _cancel_waiting_stock_reservations_for_order_line(
                db,
                order_line_id=order_line.order_line_id,
            )
        return 0

    remaining_qty = stock_ship_qty
    shipped_at = _utcnow()

    waiting_lines = (
        db.execute(
            select(ShipmentLine)
            .where(
                ShipmentLine.order_line_id == order_line.order_line_id,
                ShipmentLine.product_id == product_id,
                ShipmentLine.source_type == "STOCK",
                ShipmentLine.status == "WAITING",
                ShipmentLine.inspection_result_id.is_(None),
            )
            .order_by(ShipmentLine.shipment_line_id.asc())
            .with_for_update()
        )
        .scalars()
        .all()
    )

    for line in waiting_lines:
        if remaining_qty <= 0:
            if release_unused_reservations:
                line.status = "CANCELED"
                line.shipped_qty = 0
                line.memo = f"{line.memo or ''} / 검수 완료 후 미사용 예약 해제".strip()
            continue

        reserved_qty = int(line.ship_qty or 0)
        ship_qty = min(reserved_qty, remaining_qty)
        if ship_qty <= 0:
            line.status = "CANCELED"
            line.shipped_qty = 0
            continue

        inventory_lot = None
        if line.product_inventory_lot_id:
            inventory_lot = (
                db.execute(
                    select(ProductInventoryLot)
                    .where(ProductInventoryLot.product_inventory_lot_id == line.product_inventory_lot_id)
                    .with_for_update()
                )
                .scalar_one_or_none()
            )

        if inventory_lot is None and line.stock_lot_no:
            inventory_lot = (
                db.execute(
                    select(ProductInventoryLot)
                    .where(
                        ProductInventoryLot.product_id == product_id,
                        ProductInventoryLot.lot_no == line.stock_lot_no,
                    )
                    .with_for_update()
                )
                .scalar_one_or_none()
            )

        if inventory_lot is None:
            raise HTTPException(
                status_code=409,
                detail="예약 재고 LOT를 확인할 수 없어 출고 처리할 수 없습니다.",
            )

        if int(inventory_lot.current_qty or 0) < ship_qty:
            raise HTTPException(status_code=409, detail="예약 LOT 재고가 부족합니다.")
        if int(inventory.current_qty or 0) < ship_qty:
            raise HTTPException(status_code=409, detail="제품 재고가 부족합니다.")

        stock_lot = (
            db.execute(
                select(Lot)
                .where(
                    Lot.product_id == product_id,
                    Lot.lot_no == inventory_lot.lot_no,
                )
                .limit(1)
            )
            .scalar_one_or_none()
        )

        inventory_lot.current_qty -= ship_qty
        inventory.current_qty -= ship_qty

        line.product_inventory_lot_id = inventory_lot.product_inventory_lot_id
        line.stock_lot_no = inventory_lot.lot_no
        line.lot_id = stock_lot.lot_id if stock_lot else line.lot_id
        line.inspection_result_id = inspection_result_id
        line.status = "DONE"
        line.ship_qty = ship_qty
        line.shipped_qty = ship_qty
        line.shipped_at = shipped_at
        line.memo = f"{line.memo or ''} / 검수 완료 시 예약 재고 출고".strip()

        if not release_unused_reservations and reserved_qty > ship_qty:
            db.add(
                ShipmentLine(
                    order_line_id=line.order_line_id,
                    product_id=line.product_id,
                    product_inventory_lot_id=inventory_lot.product_inventory_lot_id,
                    stock_lot_no=inventory_lot.lot_no,
                    lot_id=stock_lot.lot_id if stock_lot else None,
                    inspection_result_id=None,
                    source_type="STOCK",
                    status="WAITING",
                    ship_qty=reserved_qty - ship_qty,
                    shipped_qty=0,
                    memo="분할검수 후 잔여 예약재고 유지",
                )
            )

        _add_ship_out_movement(
            db,
            order_line=order_line,
            schedule=schedule,
            inventory=inventory,
            shipment_line=line,
            ship_qty=ship_qty,
            memo=f"검수실적 저장: 예약 재고 출고 / shipment_line_id={line.shipment_line_id}",
        )

        remaining_qty -= ship_qty

    return remaining_qty


def _create_completed_result_shipment_line(
    db: Session,
    *,
    order_line: OrderLine,
    schedule: InspectionSchedule,
    inventory: ProductInventory,
    inventory_lot: ProductInventoryLot,
    lot: Lot,
    inspection_result_id: int,
    result_ship_qty: int,
) -> None:
    inventory_lot.current_qty -= result_ship_qty
    inventory.current_qty -= result_ship_qty

    shipment_line = ShipmentLine(
        order_line_id=order_line.order_line_id,
        product_id=lot.product_id,
        product_inventory_lot_id=inventory_lot.product_inventory_lot_id,
        stock_lot_no=inventory_lot.lot_no,
        lot_id=lot.lot_id,
        inspection_result_id=inspection_result_id,
        source_type="INSPECTION_RESULT",
        status="DONE",
        ship_qty=result_ship_qty,
        shipped_qty=result_ship_qty,
        shipped_at=_utcnow(),
        memo="검수실적 저장 시 생산분 출고 처리",
    )
    db.add(shipment_line)
    db.flush()

    _add_ship_out_movement(
        db,
        order_line=order_line,
        schedule=schedule,
        inventory=inventory,
        shipment_line=shipment_line,
        ship_qty=result_ship_qty,
        memo=f"검수실적 저장 생산분 출고 / shipment_line_id={shipment_line.shipment_line_id}",
    )


def _apply_inventory_for_result(
    db: Session,
    *,
    result: InspectionResult,
    schedule: InspectionSchedule,
    stock_ship_qty: int,
    result_ship_qty: int,
    stock_in_qty: int,
    settlement_sellable_qty: int,
) -> None:
    lot = db.execute(
        select(Lot)
        .where(Lot.lot_id == schedule.lot_id)
        .with_for_update()
    ).scalar_one_or_none()
    if lot is None:
        raise HTTPException(status_code=404, detail="lot not found")

    order_line = db.execute(
        select(OrderLine)
        .where(OrderLine.order_line_id == lot.order_line_id)
        .with_for_update()
    ).scalar_one_or_none()
    if order_line is None:
        raise HTTPException(status_code=404, detail="order_line not found")

    inventory = db.execute(
        select(ProductInventory)
        .where(ProductInventory.product_id == lot.product_id)
        .with_for_update()
    ).scalar_one_or_none()

    if inventory is None:
        inventory = ProductInventory(
            product_id=lot.product_id,
            current_qty=0,
        )
        db.add(inventory)
        db.flush()

    existing_movements = db.execute(
        select(ProductInventoryMovement)
        .where(
            ProductInventoryMovement.inspection_result_id == result.inspection_result_id,
            ProductInventoryMovement.source_type.in_(
                ("INSPECTION_RESULT", "INSPECTION_RESULT_IN", "SHIPMENT_LINE")
            ),
        )
        .with_for_update()
    ).scalars().all()

    for mv in existing_movements:
        inventory_lot = None
        if mv.product_inventory_lot_id:
            inventory_lot = (
                db.execute(
                    select(ProductInventoryLot)
                    .where(ProductInventoryLot.product_inventory_lot_id == mv.product_inventory_lot_id)
                    .with_for_update()
                )
                .scalar_one_or_none()
            )

        if mv.movement_type == "INSPECTION_IN":
            inventory.current_qty -= int(mv.qty or 0)
            if inventory_lot is not None:
                inventory_lot.current_qty -= int(mv.qty or 0)
        elif mv.movement_type == "SHIP_OUT":
            inventory.current_qty -= int(mv.qty or 0)
            if inventory_lot is not None:
                inventory_lot.current_qty -= int(mv.qty or 0)

        db.delete(mv)

    existing_shipment_lines = db.execute(
        select(ShipmentLine)
        .where(
            ShipmentLine.inspection_result_id == result.inspection_result_id,
            ShipmentLine.status != "CANCELED",
        )
        .with_for_update()
    ).scalars().all()

    for line in existing_shipment_lines:
        db.delete(line)

    db.flush()

    discard_qty = int(result.discard_qty or 0)
    if result_ship_qty + stock_in_qty + discard_qty != settlement_sellable_qty:
        raise HTTPException(
            status_code=422,
            detail="생산 출고수량 + 재고편입수량 + 폐기수량은 판매가능수량과 같아야 합니다.",
        )

    current_stock_qty_before_result_in = int(inventory.current_qty or 0)
    if stock_ship_qty > current_stock_qty_before_result_in:
        raise HTTPException(
            status_code=422,
            detail=(
                "재고 출고수량이 현재 사용 가능한 재고보다 큽니다. "
                f"현재 가능재고: {current_stock_qty_before_result_in}"
            ),
        )

    partner = db.get(Partner, order_line.partner_id)
    ship_target_qty = int(
        calculate_ship_qty(partner.name if partner else "", int(order_line.order_qty or 0))
        or 0
    )
    already_shipped_qty = int(
        db.execute(
            select(func.coalesce(func.sum(-ProductInventoryMovement.qty), 0)).where(
                ProductInventoryMovement.order_line_id == order_line.order_line_id,
                ProductInventoryMovement.movement_type == "SHIP_OUT",
            )
        ).scalar_one()
        or 0
    )
    requested_ship_qty = stock_ship_qty + result_ship_qty
    shipment_progress = build_shipment_progress(
        ship_target_qty=ship_target_qty,
        total_shipped_qty=already_shipped_qty + requested_ship_qty,
        current_result_shipped_qty=requested_ship_qty,
    )
    if requested_ship_qty > shipment_progress.remaining_before_current_result_qty:
        raise HTTPException(
            status_code=422,
            detail=(
                "이번 회차 출고수량이 발주의 남은 출고수량을 초과할 수 없습니다. "
                "남은 출고수량: "
                f"{shipment_progress.remaining_before_current_result_qty}"
            ),
        )

    remaining_stock_ship_qty = _consume_waiting_stock_reservations(
        db,
        order_line=order_line,
        schedule=schedule,
        inventory=inventory,
        product_id=lot.product_id,
        inspection_result_id=result.inspection_result_id,
        stock_ship_qty=stock_ship_qty,
        release_unused_reservations=not result.is_partial,
    )

    if remaining_stock_ship_qty > 0:
        _create_completed_stock_shipment_lines_by_fifo(
            db,
            order_line=order_line,
            schedule=schedule,
            inventory=inventory,
            product_id=lot.product_id,
            current_lot_no=None,
            inspection_result_id=result.inspection_result_id,
            stock_ship_qty=remaining_stock_ship_qty,
        )

    inventory_in_qty = max(settlement_sellable_qty - discard_qty, 0)
    if inventory_in_qty > 0:
        inventory_lot = _get_or_create_inventory_lot(
            db,
            product_id=lot.product_id,
            lot_no=lot.lot_no,
        )
        inventory.current_qty += inventory_in_qty
        inventory_lot.current_qty += inventory_in_qty
        db.add(
            ProductInventoryMovement(
                product_id=lot.product_id,
                product_inventory_lot_id=inventory_lot.product_inventory_lot_id,
                stock_lot_no=inventory_lot.lot_no,
                movement_type="INSPECTION_IN",
                qty=inventory_in_qty,
                balance_after=inventory.current_qty,
                source_type="INSPECTION_RESULT_IN",
                source_id=result.inspection_result_id,
                order_line_id=order_line.order_line_id,
                inspection_schedule_id=schedule.inspection_schedule_id,
                inspection_result_id=result.inspection_result_id,
                memo="검수 회차 판매가능수량 재고 입고",
            )
        )

    if result_ship_qty > 0:
        result_inventory_lot = _get_or_create_inventory_lot(
            db,
            product_id=lot.product_id,
            lot_no=lot.lot_no,
        )
        _create_completed_result_shipment_line(
            db,
            order_line=order_line,
            schedule=schedule,
            inventory=inventory,
            inventory_lot=result_inventory_lot,
            lot=lot,
            inspection_result_id=result.inspection_result_id,
            result_ship_qty=result_ship_qty,
        )

    db.flush()
