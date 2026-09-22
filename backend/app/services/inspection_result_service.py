from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import KOREA_TIME_ZONE, UTC, utc_now
from app.models.defect_type import DefectType
from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.schemas.inspection_result import DefectLineIn
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
from app.services.inspection_settlement_service import get_settlement_sources, settlement_carry_qty
from app.services.inventory_lock_service import lock_product_inventory
from app.models.inspection_result_revision import InspectionResultRevision
from app.services.inspection_inventory_service import apply_inventory_for_result
from app.services.inspection_result_history_service import (
    result_snapshot, replace_defects_and_attachments, ensure_no_issued_documents,
)



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


def _validate_lot_received_quantity(
    db: Session,
    *,
    schedule: InspectionSchedule,
    current_received_qty: int,
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
    if current_received_qty <= 0:
        raise HTTPException(status_code=422, detail="이번 검수 처리수량은 0보다 커야 합니다.")

    # The LOT plan is neither a minimum nor a maximum for actual processed quantity.


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
    shortage_reason: Optional[str] = None,
) -> tuple[InspectionResult, str, Optional[int]]:
    """
    - 신규 저장은 IN_PROGRESS, 기존 최종 실적 수정은 DONE에서 허용
    - inspected_qty = good_qty + defect_ship_qty + defect_qty (서버 계산)
    - sellable_qty = good_qty + defect_ship_qty
    - split and final rounds both settle inspected sellable quantity immediately
    - allocation includes explicitly owned carry; updates post only audited deltas
    - defects/attachments: 변경된 경우에만 교체하고 수정 이력 보존
    - is_partial=true: schedule=PARTIAL_DONE + next schedule 자동 생성(RECEIVED)
    - is_partial=false: schedule=DONE + 재고/출하 반영
    """
    sch, result, order_line_id = _lock_inspection_result(
        db, inspection_schedule_id, expected_updated_at=expected_updated_at, is_partial=is_partial)

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

    shortage_reason = (shortage_reason or "").strip() or None
    if is_partial:
        shortage_reason = None
    prior_unsettled_results, settlement_error = get_settlement_sources(db, schedule=sch, result=result)
    if settlement_error:
        raise HTTPException(status_code=409, detail=settlement_error)
    prior_unsettled_sellable_qty = settlement_carry_qty(prior_unsettled_results, existing=result is not None)
    before_values = result_snapshot(db, result) if result is not None else None
    if result is not None and any(getattr(result, name) != value for name, value in (
        ("good_qty", good_qty), ("defect_ship_qty", defect_ship_qty), ("defect_qty", defect_qty),
        ("uninspected_qty", uninspected_qty), ("discard_qty", discard_qty),
    )):
        ensure_no_issued_documents(db, result.inspection_result_id, order_line_id)
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
        current_received_qty=inspected_qty + uninspected_qty,
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

    values = dict(good_qty=good_qty, defect_ship_qty=defect_ship_qty, defect_qty=defect_qty,
        inspected_qty=inspected_qty, uninspected_qty=uninspected_qty, discard_qty=discard_qty,
        is_partial=is_partial, next_inspection_date=next_inspection_date, partial_reason=partial_reason,
        shortage_reason=shortage_reason, memo=memo)
    if result is None:
        result = InspectionResult(inspection_schedule_id=inspection_schedule_id, created_by=actor, **values)
        db.add(result)
    else:
        for field, value in values.items():
            setattr(result, field, value)
    db.flush()

    replace_defects_and_attachments(
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
        if sch.finished_at is None:
            sch.finished_at = now

    db.flush()
    apply_inventory_for_result(
        db=db,
        result=result,
        schedule=sch,
        stock_ship_qty=stock_ship_qty,
        result_ship_qty=result_ship_qty,
        stock_in_qty=stock_in_qty,
    )
    if result.settled_at is None:
        result.settled_at = now
        result.settled_by = actor
    result.settlement_owner_id = result.inspection_result_id
    result.settled_sellable_qty = good_qty + defect_ship_qty
    for prior_result in prior_unsettled_results:
        if prior_result.settlement_owner_id is None:
            prior_result.settled_at = now
            prior_result.settled_by = actor
            prior_result.settlement_owner_id = result.inspection_result_id
            prior_result.settled_sellable_qty = prior_result.good_qty + prior_result.defect_ship_qty

    db.flush()
    after_values = result_snapshot(db, result)
    if before_values != after_values:
        result.updated_at = now
        db.add(InspectionResultRevision(inspection_result_id=result.inspection_result_id,
            before_values=before_values or {}, after_values=after_values, actor=actor))
    sync_lot_status_from_inspection_schedules(db, lot_id=sch.lot_id)

    refresh_order_line_snapshots_for_lots(db, {sch.lot_id})
    lot = db.get(Lot, sch.lot_id)
    if lot is not None:
        refresh_order_line_snapshots_for_product(db, lot.product_id)

    return result, sch.status, created_next_id






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


def _lock_inspection_result(
    db: Session, inspection_schedule_id: int, *,
    expected_updated_at: datetime | None, is_partial: bool,
) -> tuple[InspectionSchedule, InspectionResult | None, int]:
    """Lock order → product inventory → LOT → schedule, then validate the edit version."""
    context = db.execute(select(InspectionSchedule.lot_id, Lot.order_line_id, Lot.product_id)
        .join(Lot, Lot.lot_id == InspectionSchedule.lot_id)
        .where(InspectionSchedule.inspection_schedule_id == inspection_schedule_id)).one_or_none()
    if context is None:
        raise HTTPException(status_code=404, detail="inspection_schedule not found")
    order = db.execute(select(OrderLine).where(OrderLine.order_line_id == context.order_line_id)
        .with_for_update().execution_options(populate_existing=True)).scalar_one()
    if order.status == "CANCELED" or not order.is_active:
        raise HTTPException(status_code=409, detail="취소된 발주의 검수는 저장할 수 없습니다.")
    lock_product_inventory(db, context.product_id)
    db.execute(select(Lot).where(Lot.lot_id == context.lot_id).with_for_update()
               .execution_options(populate_existing=True)).scalar_one()
    sch = db.execute(
        select(InspectionSchedule)
        .where(InspectionSchedule.inspection_schedule_id == inspection_schedule_id)
        .with_for_update().execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if not sch:
        raise HTTPException(status_code=404, detail="inspection_schedule not found")

    result = db.execute(
        select(InspectionResult).where(InspectionResult.inspection_schedule_id == inspection_schedule_id)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()

    if sch.status not in ("IN_PROGRESS", "DONE"):
        raise HTTPException(status_code=409, detail="Only IN_PROGRESS or DONE schedule can be saved as result")

    if sch.status == "DONE" and result is None:
        raise HTTPException(status_code=409, detail="DONE schedule result not found")

    if result is not None and expected_updated_at is None:
        raise HTTPException(status_code=409, detail="수정 버전이 없습니다. 최신 프로그램에서 실적을 다시 조회하세요.")

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

    return sch, result, context.order_line_id
