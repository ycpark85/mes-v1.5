from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_change_log import OutsourceWorkGroupChangeLog
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction import OutsourceWorkInstruction


@dataclass(frozen=True, slots=True)
class OutsourceWorkTimelineEvent:
    lot_id: int
    event_type: str
    event_at: datetime
    title: str
    instruction_no: str
    process_type: str
    group_seq: str
    details: str
    reason: str | None
    actor: str | None
    status: str
    ref_type: str
    ref_id: int


def get_outsource_work_timeline_events(
    db: Session,
    *,
    lot_ids: list[int],
) -> list[OutsourceWorkTimelineEvent]:
    if not lot_ids:
        return []

    rows = db.execute(
        select(
            OutsourceWorkGroupItem.lot_id,
            OutsourceWorkGroup,
            OutsourceWorkInstruction,
        )
        .select_from(OutsourceWorkGroupItem)
        .join(
            OutsourceWorkGroup,
            OutsourceWorkGroup.outsource_work_group_id
            == OutsourceWorkGroupItem.outsource_work_group_id,
        )
        .join(
            OutsourceWorkInstruction,
            OutsourceWorkInstruction.outsource_work_instruction_id
            == OutsourceWorkGroup.outsource_work_instruction_id,
        )
        .where(OutsourceWorkGroupItem.lot_id.in_(lot_ids))
        .order_by(
            OutsourceWorkGroup.outsource_work_group_id.asc(),
            OutsourceWorkGroupItem.lot_id.asc(),
        )
    ).all()
    if not rows:
        return []

    work_group_ids = sorted(
        {work_group.outsource_work_group_id for _, work_group, _ in rows}
    )
    change_logs = (
        db.execute(
            select(OutsourceWorkGroupChangeLog)
            .where(
                OutsourceWorkGroupChangeLog.outsource_work_group_id.in_(
                    work_group_ids
                ),
                OutsourceWorkGroupChangeLog.action_type.in_(("UPDATE", "CANCEL")),
            )
            .order_by(
                OutsourceWorkGroupChangeLog.created_at.asc(),
                (
                    OutsourceWorkGroupChangeLog
                    .outsource_work_group_change_log_id
                ).asc(),
            )
        )
        .scalars()
        .all()
    )
    logs_by_group_id: dict[int, list[OutsourceWorkGroupChangeLog]] = {}
    for change_log in change_logs:
        logs_by_group_id.setdefault(
            change_log.outsource_work_group_id,
            [],
        ).append(change_log)

    events: list[OutsourceWorkTimelineEvent] = []
    seen_group_lots: set[tuple[int, int]] = set()
    for lot_id, work_group, instruction in rows:
        group_lot_key = (work_group.outsource_work_group_id, lot_id)
        if group_lot_key in seen_group_lots:
            continue
        seen_group_lots.add(group_lot_key)

        group_change_logs = logs_by_group_id.get(
            work_group.outsource_work_group_id,
            [],
        )
        for change_log in group_change_logs:
            if change_log.action_type == "UPDATE":
                events.append(
                    OutsourceWorkTimelineEvent(
                        lot_id=lot_id,
                        event_type="OUTSOURCE_INSTRUCTION_UPDATED",
                        event_at=change_log.created_at,
                        title="외주 작업지시 수정",
                        instruction_no=instruction.instruction_no,
                        process_type=work_group.process_type,
                        group_seq=work_group.group_seq,
                        details=_build_update_details(change_log, lot_id=lot_id),
                        reason=change_log.reason,
                        actor=change_log.created_by,
                        status="DONE",
                        ref_type="OUTSOURCE_WORK_GROUP_CHANGE_LOG",
                        ref_id=change_log.outsource_work_group_change_log_id,
                    )
                )
                continue

            events.append(
                OutsourceWorkTimelineEvent(
                    lot_id=lot_id,
                    event_type="OUTSOURCE_INSTRUCTION_CANCELED",
                    event_at=change_log.created_at,
                    title="외주 작업지시 취소",
                    instruction_no=instruction.instruction_no,
                    process_type=work_group.process_type,
                    group_seq=work_group.group_seq,
                    details="",
                    reason=change_log.reason,
                    actor=change_log.created_by,
                    status="CANCELED",
                    ref_type="OUTSOURCE_WORK_GROUP_CHANGE_LOG",
                    ref_id=change_log.outsource_work_group_change_log_id,
                )
            )

        has_cancel_log = any(
            change_log.action_type == "CANCEL"
            for change_log in group_change_logs
        )
        if (
            not has_cancel_log
            and work_group.status == "CANCELED"
            and work_group.canceled_at is not None
        ):
            events.append(
                OutsourceWorkTimelineEvent(
                    lot_id=lot_id,
                    event_type="OUTSOURCE_INSTRUCTION_CANCELED",
                    event_at=work_group.canceled_at,
                    title="외주 작업지시 취소",
                    instruction_no=instruction.instruction_no,
                    process_type=work_group.process_type,
                    group_seq=work_group.group_seq,
                    details="",
                    reason=work_group.canceled_reason,
                    actor=None,
                    status="CANCELED",
                    ref_type="OUTSOURCE_WORK_GROUP",
                    ref_id=work_group.outsource_work_group_id,
                )
            )

    return events


def _build_update_details(
    change_log: OutsourceWorkGroupChangeLog,
    *,
    lot_id: int,
) -> str:
    before_data = change_log.before_data or {}
    after_data = change_log.after_data or {}
    changes: list[str] = []

    fields = (
        ("sheet_qty", "작업수량(장)"),
        ("length_m", "길이(m)"),
        ("sheet_cut_count", "장당 작업수"),
        ("fabric_lot_no", "원단 LOT"),
        ("remark", "비고"),
    )
    for field_name, label in fields:
        before_value = before_data.get(field_name)
        after_value = after_data.get(field_name)
        if before_value != after_value:
            changes.append(
                f"{label} {_format_value(before_value)} → "
                f"{_format_value(after_value)}"
            )

    before_item = _find_lot_item(before_data, lot_id=lot_id)
    after_item = _find_lot_item(after_data, lot_id=lot_id)
    before_output_qty = before_item.get("expected_output_qty")
    after_output_qty = after_item.get("expected_output_qty")
    if before_output_qty != after_output_qty:
        changes.append(
            f"예상수량 {_format_value(before_output_qty)} → "
            f"{_format_value(after_output_qty)}"
        )

    return " / ".join(changes) if changes else "작업지시 정보 변경"


def _find_lot_item(snapshot: dict[str, Any], *, lot_id: int) -> dict[str, Any]:
    items = snapshot.get("items")
    if not isinstance(items, list):
        return {}

    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            item_lot_id = int(item.get("lot_id"))
        except (TypeError, ValueError):
            continue
        if item_lot_id == lot_id:
            return item
    return {}


def _format_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)
