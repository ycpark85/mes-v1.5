from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.observability import request_id_context
from app.core.time import korea_today, utc_now
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.outsource_purchase_order_item import OutsourcePurchaseOrderItem
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.product import Product
from app.models.routing_template import RoutingTemplate
from app.schemas.inspection_schedule import (
    InspectionScheduleCreate,
    InspectionScheduleReorderIn,
    InspectionScheduleUpdate,
)
from app.services.lot_status import derive_lot_status_from_inspection_statuses
from app.services.production_daily_query import refresh_order_line_snapshots_for_lots
from app.services.routing_policy import is_inspection_only_template_name
from app.services.order_fulfillment_policy import sync_order_fulfillment_status


inspection_logger = logging.getLogger("mes.inspection")
_KOREA_BUSINESS_DATE_SQL = text(
    "SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date"
)


def create_inspection_schedule(
    db: Session,
    payload: InspectionScheduleCreate,
) -> InspectionSchedule:
    lot = db.get(Lot, payload.lot_id)

    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")

    selected_schedule: InspectionSchedule | None = None
    created_schedules: list[InspectionSchedule] = []

    if payload.outsource_work_group_id:
        work_group = _get_outsource_work_group_for_update(
            db,
            payload.outsource_work_group_id,
        )

        if not work_group:
            raise HTTPException(
                status_code=404,
                detail="Outsource work group not found",
            )

        if work_group.status == "CANCELED":
            raise HTTPException(
                status_code=409,
                detail="Canceled outsource work group cannot be scheduled for inspection",
            )

        next_seq = _get_next_day_seq(db, payload.inspection_date)
        group_items = _get_outsource_work_group_items(
            db,
            payload.outsource_work_group_id,
        )

        if not group_items:
            raise HTTPException(
                status_code=409,
                detail="Outsource work group has no items",
            )

        selected_group_item = next(
            (
                group_item
                for group_item in group_items
                if group_item.lot_id == payload.lot_id
            ),
            None,
        )

        if selected_group_item is None:
            raise HTTPException(
                status_code=409,
                detail="Selected lot is not included in outsource work group",
            )

        for group_item in group_items:
            existing_schedule = _get_existing_active_schedule(
                db,
                lot_id=group_item.lot_id,
                inspection_date=payload.inspection_date,
            )

            if existing_schedule:
                if group_item.lot_id == payload.lot_id:
                    selected_schedule = existing_schedule

                continue

            schedule = _create_single_inspection_schedule(
                db=db,
                lot_id=group_item.lot_id,
                inspection_date=payload.inspection_date,
                memo=payload.memo,
                day_seq=next_seq,
                outsource_work_group_id=work_group.outsource_work_group_id,
                outsource_work_group_item_id=group_item.outsource_work_group_item_id,
            )

            if group_item.lot_id == payload.lot_id:
                selected_schedule = schedule

            created_schedules.append(schedule)
            next_seq += 1

        if selected_schedule is None and created_schedules:
            selected_schedule = created_schedules[0]

        if selected_schedule is None:
            raise HTTPException(
                status_code=409,
                detail="Inspection schedule already exists for this outsource work group",
            )

    else:
        next_seq = _get_next_day_seq(db, payload.inspection_date)
        existing_schedule = _get_existing_active_schedule(
            db,
            lot_id=payload.lot_id,
            inspection_date=payload.inspection_date,
        )

        if existing_schedule:
            raise HTTPException(
                status_code=409,
                detail="Inspection schedule already exists for this lot and date",
            )

        selected_schedule = _create_single_inspection_schedule(
            db=db,
            lot_id=payload.lot_id,
            inspection_date=payload.inspection_date,
            memo=payload.memo,
            day_seq=next_seq,
            outsource_work_group_id=payload.outsource_work_group_id,
            outsource_work_group_item_id=payload.outsource_work_group_item_id,
        )

    db.flush()
    return selected_schedule


def update_inspection_schedule(
    db: Session,
    inspection_schedule_id: int,
    payload: InspectionScheduleUpdate,
    *,
    today: date | None = None,
) -> InspectionSchedule:
    schedule = db.get(InspectionSchedule, inspection_schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Inspection schedule not found")

    if schedule.status not in ("WAITING", "RECEIVED"):
        raise HTTPException(
            status_code=409,
            detail="Schedule can be updated only in WAITING/RECEIVED status",
        )

    if payload.inspection_date is not None and payload.inspection_date != schedule.inspection_date:
        today_kst = today or korea_today()
        if payload.inspection_date < today_kst:
            raise HTTPException(
                status_code=409,
                detail="Inspection schedule date cannot be changed to a past date",
            )

        old_date = schedule.inspection_date

        schedule.inspection_date = payload.inspection_date
        schedule.day_seq = _get_next_day_seq(db, payload.inspection_date)

        db.flush()
        resequence_inspection_date(db, old_date)
        resequence_inspection_date(db, payload.inspection_date)
        return schedule

    db.flush()
    return schedule


def receive_inspection_schedule(
    db: Session,
    inspection_schedule_id: int,
) -> InspectionSchedule:
    schedule_link = db.execute(
        select(
            InspectionSchedule.outsource_work_group_id,
            InspectionSchedule.inspection_date,
        ).where(
            InspectionSchedule.inspection_schedule_id == inspection_schedule_id
        )
    ).one_or_none()

    if schedule_link is None:
        raise HTTPException(status_code=404, detail="Inspection schedule not found")

    work_group: OutsourceWorkGroup | None = None
    locked_group_schedules: list[InspectionSchedule] = []

    if schedule_link.outsource_work_group_id:
        work_group = _get_outsource_work_group_for_update(
            db,
            schedule_link.outsource_work_group_id,
        )
        locked_group_schedules = (
            db.execute(
                select(InspectionSchedule)
                .where(
                    InspectionSchedule.outsource_work_group_id
                    == schedule_link.outsource_work_group_id,
                    InspectionSchedule.inspection_date == schedule_link.inspection_date,
                )
                .order_by(InspectionSchedule.inspection_schedule_id.asc())
                .with_for_update()
            )
            .scalars()
            .all()
        )
        schedule = next(
            (
                row
                for row in locked_group_schedules
                if row.inspection_schedule_id == inspection_schedule_id
            ),
            None,
        )
    else:
        schedule = _get_inspection_schedule_for_update(db, inspection_schedule_id)

    if schedule is None:
        raise HTTPException(status_code=404, detail="Inspection schedule not found")

    if schedule.status != "WAITING":
        raise HTTPException(status_code=409, detail="Only WAITING schedule can be received")

    if _is_inspection_only_lot(db, schedule.lot_id):
        _mark_schedules_received(db, [schedule])
        return schedule

    if schedule.outsource_work_group_id:
        if not work_group:
            raise HTTPException(
                status_code=404,
                detail="Outsource work group not found",
            )

        if work_group.status != "SHIPPED":
            raise HTTPException(
                status_code=409,
                detail="Only SHIPPED outsource work group can be received",
            )

        group_schedules = [
            row for row in locked_group_schedules if row.status == "WAITING"
        ]
        group_schedules.sort(
            key=lambda row: (
                row.day_seq if row.day_seq is not None else 2**31,
                row.inspection_schedule_id,
            )
        )

        if not group_schedules:
            raise HTTPException(
                status_code=409,
                detail="No WAITING inspection schedules for outsource work group",
            )

        _mark_schedules_received(db, group_schedules)
        return schedule

    shipped_count = db.execute(
        select(func.count())
        .select_from(OutsourcePurchaseOrderItem)
        .where(
            OutsourcePurchaseOrderItem.lot_id == schedule.lot_id,
            OutsourcePurchaseOrderItem.status == "SHIPPED",
        )
    ).scalar_one()

    if int(shipped_count) == 0:
        raise HTTPException(
            status_code=409,
            detail="Only SHIPPED outsource purchase order item can be received",
        )

    _mark_schedules_received(db, [schedule])
    return schedule


def start_inspection_schedule(
    db: Session,
    inspection_schedule_id: int,
    *,
    today: date | None = None,
) -> InspectionSchedule:
    schedule = _get_inspection_schedule_for_update(db, inspection_schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Inspection schedule not found")

    if schedule.status != "RECEIVED":
        raise HTTPException(status_code=409, detail="Only RECEIVED schedule can be started")

    business_date = _resolve_inspection_start_business_date(db, today=today)
    if schedule.inspection_date != business_date:
        inspection_logger.warning(
            "inspection_start_date_rejected request_id=%s schedule_id=%s "
            "lot_id=%s inspection_date=%s business_date=%s",
            request_id_context.get(),
            schedule.inspection_schedule_id,
            schedule.lot_id,
            schedule.inspection_date,
            business_date,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "오늘 스케줄만 검수를 시작할 수 있습니다. "
                f"선택 검수일: {schedule.inspection_date.isoformat()}, "
                f"서버 기준일: {business_date.isoformat()}"
            ),
        )

    schedule.status = "IN_PROGRESS"
    schedule.started_at = _utcnow()

    db.flush()
    sync_lot_status_from_inspection_schedules(db, lot_id=schedule.lot_id)
    refresh_order_line_snapshots_for_lots(db, {schedule.lot_id})

    return schedule


def _resolve_inspection_start_business_date(
    db: Session,
    *,
    today: date | None,
) -> date:
    if today is not None:
        return today

    application_date = korea_today()
    if db.get_bind().dialect.name != "postgresql":
        return application_date

    business_date = db.execute(_KOREA_BUSINESS_DATE_SQL).scalar_one()
    if business_date != application_date:
        inspection_logger.error(
            "inspection_business_date_source_mismatch request_id=%s "
            "database_date=%s application_date=%s selected_source=database",
            request_id_context.get(),
            business_date,
            application_date,
        )

    return business_date


def cancel_inspection_schedule(
    db: Session,
    inspection_schedule_id: int,
) -> InspectionSchedule:
    schedule = db.get(InspectionSchedule, inspection_schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Inspection schedule not found")

    if schedule.status not in ("WAITING", "RECEIVED"):
        raise HTTPException(
            status_code=409,
            detail="Only WAITING/RECEIVED schedule can be canceled",
        )

    lot_id = schedule.lot_id
    schedule.status = "CANCELED"

    db.flush()
    sync_lot_status_from_inspection_schedules(db, lot_id=lot_id)
    refresh_order_line_snapshots_for_lots(db, {lot_id})

    return schedule


def reorder_inspection_schedules(
    db: Session,
    payload: InspectionScheduleReorderIn,
) -> list[InspectionSchedule]:
    rows = (
        db.execute(
            select(InspectionSchedule)
            .where(
                InspectionSchedule.inspection_date == payload.inspection_date,
                InspectionSchedule.status.in_(("WAITING", "RECEIVED")),
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail="No reorder targets for this date")

    target_ids = {row.inspection_schedule_id for row in rows}
    req_ids = payload.ordered_ids

    if set(req_ids) != target_ids:
        raise HTTPException(
            status_code=409,
            detail="ordered_ids must match ALL schedules of that date (WAITING/RECEIVED)",
        )

    return resequence_inspection_date(
        db,
        payload.inspection_date,
        ordered_active_ids=req_ids,
    )


def resequence_inspection_date(
    db: Session,
    target_date: date,
    *,
    ordered_active_ids: list[int] | None = None,
) -> list[InspectionSchedule]:
    rows = (
        db.execute(
            select(InspectionSchedule)
            .where(
                InspectionSchedule.inspection_date == target_date,
                InspectionSchedule.status != "CANCELED",
            )
            .order_by(
                InspectionSchedule.day_seq.asc().nulls_last(),
                InspectionSchedule.inspection_schedule_id.asc(),
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )

    active_rows = [row for row in rows if row.status in ("WAITING", "RECEIVED")]

    if ordered_active_ids is not None:
        if len(ordered_active_ids) != len(set(ordered_active_ids)):
            raise HTTPException(status_code=409, detail="Duplicated ids in ordered_ids")

        active_ids = {row.inspection_schedule_id for row in active_rows}
        if set(ordered_active_ids) != active_ids:
            raise HTTPException(
                status_code=409,
                detail="ordered_ids must match ALL schedules of that date (WAITING/RECEIVED)",
            )

        active_map = {row.inspection_schedule_id: row for row in active_rows}
        ordered_active_rows = iter(active_map[sid] for sid in ordered_active_ids)
        ordered_rows: list[InspectionSchedule] = []

        for row in rows:
            if row.status in ("WAITING", "RECEIVED"):
                ordered_rows.append(next(ordered_active_rows))
            else:
                ordered_rows.append(row)
    else:
        ordered_rows = rows

    for idx, row in enumerate(ordered_rows, start=1):
        row.day_seq = idx

    db.flush()
    return ordered_rows


def sync_lot_status_from_inspection_schedules(
    db: Session,
    *,
    lot_id: int,
) -> None:
    lot = db.get(Lot, lot_id)
    if not lot:
        return

    statuses = (
        db.execute(
            select(InspectionSchedule.status).where(
                InspectionSchedule.lot_id == lot_id,
                InspectionSchedule.status != "CANCELED",
            )
        )
        .scalars()
        .all()
    )

    if not statuses:
        return

    next_status = derive_lot_status_from_inspection_statuses(statuses)

    if next_status is None:
        return

    lot.status = next_status
    db.flush()

    if next_status == "DONE":
        _sync_order_line_status_from_lot(db, lot=lot)


def _mark_schedules_received(
    db: Session,
    schedules: list[InspectionSchedule],
) -> None:
    now = _utcnow()

    for schedule in schedules:
        schedule.status = "RECEIVED"
        schedule.received_at = now

    db.flush()

    lot_ids = {schedule.lot_id for schedule in schedules}
    for lot_id in lot_ids:
        sync_lot_status_from_inspection_schedules(db, lot_id=lot_id)

    refresh_order_line_snapshots_for_lots(db, lot_ids)


def _is_inspection_only_lot(db: Session, lot_id: int) -> bool:
    template_name = (
        db.execute(
            select(RoutingTemplate.template_name)
            .select_from(Lot)
            .join(Product, Product.product_id == Lot.product_id)
            .join(
                RoutingTemplate,
                RoutingTemplate.routing_template_id == Product.routing_template_id,
            )
            .where(Lot.lot_id == lot_id)
        )
        .scalar_one_or_none()
    )

    return is_inspection_only_template_name(template_name)


def _get_next_day_seq(db: Session, inspection_date: date) -> int:
    max_seq = db.execute(
        select(func.coalesce(func.max(InspectionSchedule.day_seq), 0)).where(
            InspectionSchedule.inspection_date == inspection_date,
            InspectionSchedule.status != "CANCELED",
        )
    ).scalar_one()

    return int(max_seq) + 1


def _get_inspection_schedule_for_update(
    db: Session,
    inspection_schedule_id: int,
) -> InspectionSchedule | None:
    return (
        db.execute(
            select(InspectionSchedule)
            .where(
                InspectionSchedule.inspection_schedule_id == inspection_schedule_id
            )
            .with_for_update()
        )
        .scalar_one_or_none()
    )


def _get_outsource_work_group_for_update(
    db: Session,
    outsource_work_group_id: int,
) -> OutsourceWorkGroup | None:
    return (
        db.execute(
            select(OutsourceWorkGroup)
            .where(
                OutsourceWorkGroup.outsource_work_group_id
                == outsource_work_group_id
            )
            .with_for_update()
        )
        .scalar_one_or_none()
    )


def _get_existing_active_schedule(
    db: Session,
    *,
    lot_id: int,
    inspection_date: date,
) -> InspectionSchedule | None:
    return (
        db.execute(
            select(InspectionSchedule)
            .where(
                InspectionSchedule.lot_id == lot_id,
                InspectionSchedule.inspection_date == inspection_date,
                InspectionSchedule.status != "CANCELED",
            )
            .limit(1)
        )
        .scalar_one_or_none()
    )


def _get_outsource_work_group_items(
    db: Session,
    outsource_work_group_id: int,
) -> list[OutsourceWorkGroupItem]:
    return (
        db.execute(
            select(OutsourceWorkGroupItem)
            .where(
                OutsourceWorkGroupItem.outsource_work_group_id
                == outsource_work_group_id
            )
            .order_by(OutsourceWorkGroupItem.outsource_work_group_item_id.asc())
        )
        .scalars()
        .all()
    )


def _create_single_inspection_schedule(
    db: Session,
    lot_id: int,
    inspection_date: date,
    memo: str | None,
    day_seq: int,
    outsource_work_group_id: int | None = None,
    outsource_work_group_item_id: int | None = None,
) -> InspectionSchedule:
    schedule = InspectionSchedule(
        lot_id=lot_id,
        inspection_date=inspection_date,
        status="WAITING",
        day_seq=day_seq,
        memo=memo,
        outsource_work_group_id=outsource_work_group_id,
        outsource_work_group_item_id=outsource_work_group_item_id,
    )

    db.add(schedule)
    return schedule


def _sync_order_line_status_from_lot(db: Session, *, lot: Lot) -> None:
    order_line = db.get(OrderLine, lot.order_line_id)
    if order_line is not None:
        sync_order_fulfillment_status(db, order_line)


def _utcnow() -> datetime:
    return utc_now()
