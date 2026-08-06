from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_change_log import OutsourceWorkGroupChangeLog
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction_item import OutsourceWorkInstructionItem
from app.schemas.outsource_work_instruction import (
    OutsourceWorkGroupCancelIn,
    OutsourceWorkGroupUpdateIn,
)
from app.services.outsource_work_instruction_query import (
    OUTSOURCE_WORK_GROUP_STATUS_CANCELED,
    get_cancel_block_reason,
    get_update_block_reason,
)
from app.services.production_daily_query import refresh_order_line_snapshots_for_work_groups


def update_work_group(
    db: Session,
    outsource_work_group_id: int,
    payload: OutsourceWorkGroupUpdateIn,
    *,
    actor: str,
) -> OutsourceWorkGroup:
    normalized_actor = _normalize_actor(actor)
    work_group = _get_work_group_for_update(db, outsource_work_group_id)

    update_block_reason = get_update_block_reason(db, work_group)
    if update_block_reason is not None:
        raise HTTPException(status_code=409, detail=update_block_reason)

    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Update reason is required")

    required_qty = _q2(payload.length_m)

    before_data = _build_work_group_change_snapshot(db, work_group)

    work_group.sheet_qty = payload.sheet_qty
    work_group.length_m = required_qty
    work_group.sheet_cut_count = payload.sheet_cut_count
    work_group.fabric_lot_no = (
        payload.fabric_lot_no.strip()
        if payload.fabric_lot_no and payload.fabric_lot_no.strip()
        else None
    )
    work_group.remark = payload.remark.strip() if payload.remark and payload.remark.strip() else None

    group_items = (
        db.execute(
            select(OutsourceWorkGroupItem)
            .where(
                OutsourceWorkGroupItem.outsource_work_group_id
                == work_group.outsource_work_group_id
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )

    for group_item in group_items:
        group_item.cuts_per_sheet = payload.sheet_cut_count
        group_item.expected_output_qty = payload.sheet_qty * payload.sheet_cut_count

    after_data = _build_work_group_change_snapshot(db, work_group)
    db.add(
        OutsourceWorkGroupChangeLog(
            outsource_work_group_id=work_group.outsource_work_group_id,
            action_type="UPDATE",
            reason=reason,
            before_data=before_data,
            after_data=after_data,
            created_by=normalized_actor,
        )
    )

    refresh_order_line_snapshots_for_work_groups(db, [work_group.outsource_work_group_id])
    db.flush()
    return work_group


def cancel_work_group(
    db: Session,
    outsource_work_group_id: int,
    payload: OutsourceWorkGroupCancelIn,
    *,
    actor: str,
) -> OutsourceWorkGroup:
    normalized_actor = _normalize_actor(actor)
    work_group = _get_work_group_for_update(db, outsource_work_group_id)

    cancel_block_reason = get_cancel_block_reason(db, work_group)
    if cancel_block_reason is not None:
        raise HTTPException(status_code=409, detail=cancel_block_reason)

    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Cancel reason is required")

    before_data = _build_work_group_change_snapshot(db, work_group)
    _cancel_linked_inspection_schedules(db, work_group)

    work_group.status = OUTSOURCE_WORK_GROUP_STATUS_CANCELED
    work_group.canceled_at = utc_now()
    work_group.canceled_reason = reason

    group_lot_ids = [
        row[0]
        for row in db.execute(
            select(OutsourceWorkGroupItem.lot_id).where(
                OutsourceWorkGroupItem.outsource_work_group_id
                == work_group.outsource_work_group_id
            )
        ).all()
    ]

    if group_lot_ids:
        instruction_items = (
            db.execute(
                select(OutsourceWorkInstructionItem)
                .where(
                    OutsourceWorkInstructionItem.outsource_work_instruction_id
                    == work_group.outsource_work_instruction_id,
                    OutsourceWorkInstructionItem.lot_id.in_(group_lot_ids),
                    OutsourceWorkInstructionItem.process_type == work_group.process_type,
                    OutsourceWorkInstructionItem.is_active.is_(True),
                )
                .with_for_update()
            )
            .scalars()
            .all()
        )

        for instruction_item in instruction_items:
            instruction_item.is_active = False

        _reset_canceled_work_group_lots_to_waiting(
            db,
            group_lot_ids,
            canceled_work_group_id=work_group.outsource_work_group_id,
        )

    after_data = _build_work_group_change_snapshot(db, work_group)
    db.add(
        OutsourceWorkGroupChangeLog(
            outsource_work_group_id=work_group.outsource_work_group_id,
            action_type="CANCEL",
            reason=reason,
            before_data=before_data,
            after_data=after_data,
            created_by=normalized_actor,
        )
    )

    refresh_order_line_snapshots_for_work_groups(db, [work_group.outsource_work_group_id])
    db.flush()
    return work_group


def _cancel_linked_inspection_schedules(
    db: Session,
    work_group: OutsourceWorkGroup,
) -> None:
    schedules = (
        db.execute(
            select(InspectionSchedule)
            .where(
                InspectionSchedule.outsource_work_group_id
                == work_group.outsource_work_group_id,
                InspectionSchedule.status.in_(("WAITING", "RECEIVED")),
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )

    for schedule in schedules:
        schedule.status = "CANCELED"


def _reset_canceled_work_group_lots_to_waiting(
    db: Session,
    lot_ids: list[int],
    *,
    canceled_work_group_id: int,
) -> None:
    lots = (
        db.execute(
            select(Lot)
            .where(Lot.lot_id.in_(lot_ids))
            .with_for_update()
        )
        .scalars()
        .all()
    )

    for lot in lots:
        if lot.status not in {"WAITING", "RECEIVED"}:
            continue

        active_outsource_exists = (
            db.execute(
                select(OutsourceWorkGroupItem.outsource_work_group_item_id)
                .join(
                    OutsourceWorkGroup,
                    OutsourceWorkGroup.outsource_work_group_id
                    == OutsourceWorkGroupItem.outsource_work_group_id,
                )
                .where(
                    OutsourceWorkGroupItem.lot_id == lot.lot_id,
                    OutsourceWorkGroup.outsource_work_group_id
                    != canceled_work_group_id,
                    (
                        OutsourceWorkGroup.status.is_(None)
                        | (OutsourceWorkGroup.status != OUTSOURCE_WORK_GROUP_STATUS_CANCELED)
                    ),
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )
        if active_outsource_exists:
            continue

        active_inspection_exists = (
            db.execute(
                select(InspectionSchedule.inspection_schedule_id)
                .where(
                    InspectionSchedule.lot_id == lot.lot_id,
                    InspectionSchedule.status != "CANCELED",
                    or_(
                        InspectionSchedule.outsource_work_group_id.is_(None),
                        InspectionSchedule.outsource_work_group_id
                        != canceled_work_group_id,
                    ),
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )
        if not active_inspection_exists:
            lot.status = "WAITING"


def _get_work_group_for_update(
    db: Session,
    outsource_work_group_id: int,
) -> OutsourceWorkGroup:
    work_group = (
        db.execute(
            select(OutsourceWorkGroup)
            .where(OutsourceWorkGroup.outsource_work_group_id == outsource_work_group_id)
            .with_for_update()
        )
        .scalar_one_or_none()
    )

    if work_group is None:
        raise HTTPException(status_code=404, detail="Outsource work group not found")

    return work_group


def _build_work_group_change_snapshot(
    db: Session,
    work_group: OutsourceWorkGroup,
) -> dict:
    group_items = (
        db.execute(
            select(OutsourceWorkGroupItem)
            .where(
                OutsourceWorkGroupItem.outsource_work_group_id
                == work_group.outsource_work_group_id
            )
            .order_by(OutsourceWorkGroupItem.outsource_work_group_item_id.asc())
        )
        .scalars()
        .all()
    )
    return {
        "outsource_work_group_id": work_group.outsource_work_group_id,
        "status": work_group.status,
        "canceled_at": _json_value(work_group.canceled_at),
        "canceled_reason": work_group.canceled_reason,
        "sheet_qty": work_group.sheet_qty,
        "length_m": _json_value(work_group.length_m),
        "sheet_cut_count": work_group.sheet_cut_count,
        "fabric_lot_no": work_group.fabric_lot_no,
        "remark": work_group.remark,
        "items": [
            {
                "outsource_work_group_item_id": item.outsource_work_group_item_id,
                "lot_id": item.lot_id,
                "cuts_per_sheet": item.cuts_per_sheet,
                "expected_output_qty": item.expected_output_qty,
            }
            for item in group_items
        ],
    }


def _json_value(value):
    if isinstance(value, Decimal):
        return str(_q2(value))
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _normalize_actor(actor: str) -> str:
    normalized_actor = actor.strip()
    if not normalized_actor:
        raise ValueError("actor is required for outsource work-group history")
    return normalized_actor
