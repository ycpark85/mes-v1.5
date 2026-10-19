from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.time import korea_today, utc_now

from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.outsource_purchase_order_item import OutsourcePurchaseOrderItem
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.outsource_work_instruction_item import OutsourceWorkInstructionItem
from app.models.partner import Partner
from app.models.product import Product
from app.models.product_inventory import ProductInventory
from app.models.production_progress_snapshot import ProductionProgressSnapshot
from app.models.shipment_line import ShipmentLine


PROCESS_DISPLAY = {
    "LOT_CREATED": "LOT\uc0dd\uc131",
    "OUTSOURCE_ORDERED": "\uc678\uc8fc\ubc1c\uc8fc",
    "DIECUT_RECEIVED": "\ub3c4\ubb34\uc1a1\uc785\uace0",
    "OUTSOURCE_DONE": "\uc678\uc8fc\uc644\ub8cc",
    "INSPECTION_WAITING": "\uac80\uc218\ub300\uae30",
    "INSPECTION_IN_PROGRESS": "\uac80\uc218\uc911",
    "COMPLETED": "\uc644\ub8cc",
}

PROCESS_ORDER = {
    "LOT_CREATED": 1,
    "OUTSOURCE_ORDERED": 2,
    "DIECUT_RECEIVED": 3,
    "OUTSOURCE_DONE": 4,
    "INSPECTION_WAITING": 5,
    "INSPECTION_IN_PROGRESS": 6,
    "COMPLETED": 7,
}

PROCESS_PROGRESS = {
    "LOT_CREATED": 10,
    "OUTSOURCE_ORDERED": 25,
    "DIECUT_RECEIVED": 45,
    "OUTSOURCE_DONE": 60,
    "INSPECTION_WAITING": 75,
    "INSPECTION_IN_PROGRESS": 90,
    "COMPLETED": 100,
}

WORK_TYPE_DISPLAY = {
    "BASIC": "\uae30\ubcf8\uc791\uc5c5",
    "REWORK": "\uc7ac\uc791\uc5c5",
}


@dataclass(frozen=True)
class LotProgress:
    process_code: str
    process_order: int
    progress_rate: int


def list_production_daily_rows(
    db: Session,
    *,
    page: int,
    size: int,
    status: str = "IN_PROGRESS",
    partner_q: str | None = None,
    product_q: str | None = None,
) -> tuple[list[dict], int]:
    normalized_status = _normalize_status(status)

    stmt = select(ProductionProgressSnapshot, OrderLine.source_erp_product_code).join(
        OrderLine, OrderLine.order_line_id == ProductionProgressSnapshot.order_line_id
    ).where(
        ProductionProgressSnapshot.status == normalized_status
    )

    if partner_q and partner_q.strip():
        stmt = stmt.where(
            ProductionProgressSnapshot.partner_name.ilike(f"%{partner_q.strip()}%")
        )

    if product_q and product_q.strip():
        keyword = f"%{product_q.strip()}%"
        stmt = stmt.where(
            or_(
                ProductionProgressSnapshot.product_code.ilike(keyword),
                OrderLine.source_erp_product_code.ilike(keyword),
                ProductionProgressSnapshot.product_name.ilike(keyword),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(db.execute(count_stmt).scalar_one() or 0)

    rows = (
        db.execute(
            stmt.order_by(
                ProductionProgressSnapshot.due_date.asc(),
                ProductionProgressSnapshot.current_process_order.asc(),
                ProductionProgressSnapshot.partner_name.asc(),
                ProductionProgressSnapshot.order_no.asc(),
                ProductionProgressSnapshot.line_no.asc(),
            )
            .offset((page - 1) * size)
            .limit(size)
        )
        .all()
    )

    today = korea_today()
    return [
        dict(
            _snapshot_to_row(snapshot, today=today),
            product_code=source_code or snapshot.product_code,
            mes_product_code=snapshot.product_code,
        )
        for snapshot, source_code in rows
    ], total


def refresh_order_line_snapshot(db: Session, order_line_id: int) -> bool:
    data = _build_order_line_snapshot_data(db, order_line_id)

    snapshot = (
        db.execute(
            select(ProductionProgressSnapshot).where(
                ProductionProgressSnapshot.order_line_id == order_line_id
            )
        )
        .scalar_one_or_none()
    )

    if data is None:
        if snapshot is not None:
            db.delete(snapshot)
        db.flush()
        return False

    if snapshot is None:
        snapshot = ProductionProgressSnapshot(**data)
        db.add(snapshot)
    else:
        for key, value in data.items():
            setattr(snapshot, key, value)
        snapshot.updated_at = utc_now()

    db.flush()
    return True


def refresh_order_line_snapshots_for_lots(db: Session, lot_ids: list[int] | set[int]) -> int:
    if not lot_ids:
        return 0

    order_line_ids = (
        db.execute(
            select(Lot.order_line_id)
            .where(Lot.lot_id.in_(list(lot_ids)))
            .distinct()
        )
        .scalars()
        .all()
    )

    return _refresh_order_line_ids(db, order_line_ids)


def refresh_order_line_snapshots_for_work_groups(
    db: Session,
    work_group_ids: list[int] | set[int],
) -> int:
    if not work_group_ids:
        return 0

    order_line_ids = (
        db.execute(
            select(Lot.order_line_id)
            .join(OutsourceWorkGroupItem, OutsourceWorkGroupItem.lot_id == Lot.lot_id)
            .where(OutsourceWorkGroupItem.outsource_work_group_id.in_(list(work_group_ids)))
            .distinct()
        )
        .scalars()
        .all()
    )

    return _refresh_order_line_ids(db, order_line_ids)


def refresh_order_line_snapshots_for_product(db: Session, product_id: int) -> int:
    order_line_ids = (
        db.execute(
            select(ProductionProgressSnapshot.order_line_id).where(
                ProductionProgressSnapshot.product_id == product_id,
                ProductionProgressSnapshot.status == "IN_PROGRESS",
            )
        )
        .scalars()
        .all()
    )

    return _refresh_order_line_ids(db, order_line_ids)


def rebuild_all_production_progress_snapshots(db: Session) -> int:
    order_line_ids = (
        db.execute(
            select(OrderLine.order_line_id)
            .join(Lot, Lot.order_line_id == OrderLine.order_line_id)
            .where(
                OrderLine.is_active.is_(True),
                OrderLine.status != "CANCELED",
            )
            .distinct()
        )
        .scalars()
        .all()
    )

    target_ids = {int(order_line_id) for order_line_id in order_line_ids}

    if target_ids:
        db.execute(
            delete(ProductionProgressSnapshot).where(
                ProductionProgressSnapshot.order_line_id.notin_(target_ids)
            )
        )
    else:
        db.execute(delete(ProductionProgressSnapshot))

    refreshed = _refresh_order_line_ids(db, target_ids)
    db.flush()
    return refreshed


def _refresh_order_line_ids(db: Session, order_line_ids) -> int:
    refreshed = 0
    for order_line_id in {int(value) for value in order_line_ids if value is not None}:
        if refresh_order_line_snapshot(db, order_line_id):
            refreshed += 1
    return refreshed


def _build_order_line_snapshot_data(db: Session, order_line_id: int) -> dict | None:
    row = (
        db.execute(
            select(
                OrderLine,
                Partner.name.label("partner_name"),
                Product.product_code.label("product_code"),
                func.coalesce(OrderLine.source_product_name, Product.product_name).label("product_name"),
            )
            .join(Partner, Partner.partner_id == OrderLine.partner_id)
            .join(Product, Product.product_id == OrderLine.product_id)
            .where(OrderLine.order_line_id == order_line_id)
        )
        .one_or_none()
    )

    if row is None:
        return None

    order_line, partner_name, product_code, product_name = row
    if not order_line.is_active or order_line.status == "CANCELED":
        return None

    lots = (
        db.execute(
            select(Lot)
            .where(Lot.order_line_id == order_line_id)
            .order_by(Lot.lot_id.asc())
        )
        .scalars()
        .all()
    )
    active_lots = [lot for lot in lots if lot.status != "CANCELED"]
    if not active_lots:
        return None

    lot_ids = [lot.lot_id for lot in active_lots]
    work_statuses_by_lot = _load_work_statuses_by_lot(db, lot_ids)
    schedule_statuses_by_lot = _load_schedule_statuses_by_lot(db, lot_ids)
    completed_lot_ids = _load_completed_lot_ids(db, lot_ids)

    all_completed = all(lot.lot_id in completed_lot_ids for lot in active_lots)
    row_status = "COMPLETED" if all_completed else "IN_PROGRESS"

    target_lots = _select_target_lots(active_lots, completed_lot_ids, row_status)
    if not target_lots:
        return None

    lot_progresses = [
        _get_lot_progress(
            lot.lot_id,
            work_statuses_by_lot=work_statuses_by_lot,
            schedule_statuses_by_lot=schedule_statuses_by_lot,
            completed_lot_ids=completed_lot_ids,
        )
        for lot in target_lots
    ]
    current_progress = min(lot_progresses, key=lambda item: item.process_order)
    work_type = "REWORK" if any(lot.parent_lot_id is not None for lot in target_lots) else "BASIC"

    return {
        "order_line_id": int(order_line.order_line_id),
        "order_no": str(order_line.order_no or ""),
        "line_no": int(order_line.line_no or 0),
        "due_date": order_line.due_date,
        "partner_id": int(order_line.partner_id),
        "partner_name": str(partner_name or ""),
        "product_id": int(order_line.product_id),
        "product_code": str(product_code or ""),
        "product_name": str(product_name or ""),
        "order_qty": int(order_line.order_qty or 0),
        "available_inventory_qty": _get_available_inventory_qty(db, int(order_line.product_id)),
        "production_qty": sum(int(lot.lot_qty or 0) for lot in target_lots),
        "work_type": work_type,
        "current_process": current_progress.process_code,
        "current_process_order": current_progress.process_order,
        "progress_rate": min(progress.progress_rate for progress in lot_progresses),
        "status": row_status,
        "lot_count": len(active_lots),
        "target_lot_count": len(target_lots),
        "completed_lot_count": sum(1 for lot in target_lots if lot.lot_id in completed_lot_ids),
        "lot_nos_text": "\n".join(str(lot.lot_no or "") for lot in target_lots),
    }


def _get_available_inventory_qty(db: Session, product_id: int) -> int:
    current_qty = (
        db.execute(
            select(func.coalesce(ProductInventory.current_qty, 0)).where(
                ProductInventory.product_id == product_id
            )
        )
        .scalar_one_or_none()
    )
    reserved_qty = (
        db.execute(
            select(func.coalesce(func.sum(ShipmentLine.ship_qty), 0)).where(
                ShipmentLine.product_id == product_id,
                ShipmentLine.source_type == "STOCK",
                ShipmentLine.status == "WAITING",
            )
        )
        .scalar_one()
    )

    return max(int(current_qty or 0) - int(reserved_qty or 0), 0)


def _snapshot_to_row(snapshot: ProductionProgressSnapshot, *, today: date) -> dict:
    due_days = (snapshot.due_date - today).days
    lot_nos = [
        lot_no
        for lot_no in (snapshot.lot_nos_text or "").splitlines()
        if lot_no.strip()
    ]

    return {
        "order_line_id": int(snapshot.order_line_id),
        "order_no": snapshot.order_no,
        "line_no": int(snapshot.line_no),
        "due_date": snapshot.due_date,
        "due_days": due_days,
        "due_slack_text": _format_due_slack(due_days),
        "due_slack_level": _get_due_slack_level(due_days),
        "partner_id": int(snapshot.partner_id),
        "partner_name": snapshot.partner_name,
        "product_id": int(snapshot.product_id),
        "product_code": snapshot.product_code,
        "product_name": snapshot.product_name,
        "order_qty": int(snapshot.order_qty or 0),
        "available_inventory_qty": int(snapshot.available_inventory_qty or 0),
        "production_qty": int(snapshot.production_qty or 0),
        "work_type": snapshot.work_type,
        "work_type_display": WORK_TYPE_DISPLAY.get(snapshot.work_type, snapshot.work_type),
        "current_process": snapshot.current_process,
        "current_process_display": PROCESS_DISPLAY.get(snapshot.current_process, snapshot.current_process),
        "progress_rate": int(snapshot.progress_rate or 0),
        "lot_count": int(snapshot.lot_count or 0),
        "target_lot_count": int(snapshot.target_lot_count or 0),
        "completed_lot_count": int(snapshot.completed_lot_count or 0),
        "lot_nos": lot_nos,
    }


def _normalize_status(status: str | None) -> str:
    normalized_status = status.strip().upper() if status else "IN_PROGRESS"
    if normalized_status not in {"IN_PROGRESS", "COMPLETED"}:
        return "IN_PROGRESS"
    return normalized_status


def _load_work_statuses_by_lot(db: Session, lot_ids: list[int]) -> dict[int, list[str | None]]:
    if not lot_ids:
        return {}

    group_statuses_by_lot: dict[int, list[str | None]] = defaultdict(list)

    group_rows = (
        db.execute(
            select(
                OutsourceWorkGroupItem.lot_id,
                OutsourceWorkGroup.status,
            )
            .join(
                OutsourceWorkGroup,
                OutsourceWorkGroup.outsource_work_group_id
                == OutsourceWorkGroupItem.outsource_work_group_id,
            )
            .where(OutsourceWorkGroupItem.lot_id.in_(lot_ids))
        )
        .all()
    )
    for lot_id, status in group_rows:
        group_statuses_by_lot[int(lot_id)].append(status)

    instruction_lot_ids = (
        db.execute(
            select(OutsourceWorkInstructionItem.lot_id).where(
                OutsourceWorkInstructionItem.lot_id.in_(lot_ids)
            )
        )
        .scalars()
        .all()
    )
    purchase_order_rows = (
        db.execute(
            select(
                OutsourcePurchaseOrderItem.lot_id,
                OutsourcePurchaseOrderItem.status,
            ).where(OutsourcePurchaseOrderItem.lot_id.in_(lot_ids))
        )
        .all()
    )
    purchase_order_statuses_by_lot: dict[int, list[str | None]] = defaultdict(list)
    for lot_id, status in purchase_order_rows:
        purchase_order_statuses_by_lot[int(lot_id)].append(status)

    statuses_by_lot: dict[int, list[str | None]] = {}
    instruction_lot_id_set = {int(lot_id) for lot_id in instruction_lot_ids}

    for lot_id in lot_ids:
        normalized_lot_id = int(lot_id)
        if group_statuses_by_lot.get(normalized_lot_id):
            statuses_by_lot[normalized_lot_id] = group_statuses_by_lot[normalized_lot_id]
        elif purchase_order_statuses_by_lot.get(normalized_lot_id):
            statuses_by_lot[normalized_lot_id] = purchase_order_statuses_by_lot[
                normalized_lot_id
            ]
        elif normalized_lot_id in instruction_lot_id_set:
            statuses_by_lot[normalized_lot_id] = [None]

    return statuses_by_lot


def _load_schedule_statuses_by_lot(db: Session, lot_ids: list[int]) -> dict[int, list[str]]:
    if not lot_ids:
        return {}

    rows = (
        db.execute(
            select(InspectionSchedule.lot_id, InspectionSchedule.status).where(
                InspectionSchedule.lot_id.in_(lot_ids),
                InspectionSchedule.status != "CANCELED",
            )
        )
        .all()
    )

    statuses_by_lot: dict[int, list[str]] = defaultdict(list)
    for lot_id, status in rows:
        statuses_by_lot[int(lot_id)].append(str(status or ""))

    return statuses_by_lot


def _load_completed_lot_ids(db: Session, lot_ids: list[int]) -> set[int]:
    if not lot_ids:
        return set()

    rows = (
        db.execute(
            select(InspectionSchedule.lot_id)
            .join(
                InspectionResult,
                InspectionResult.inspection_schedule_id == InspectionSchedule.inspection_schedule_id,
            )
            .where(
                InspectionSchedule.lot_id.in_(lot_ids),
                InspectionSchedule.status == "DONE",
                InspectionResult.is_partial.is_(False),
            )
            .distinct()
        )
        .scalars()
        .all()
    )

    return {int(lot_id) for lot_id in rows}


def _select_target_lots(
    lots: list[Lot],
    completed_lot_ids: set[int],
    row_status: str,
) -> list[Lot]:
    rework_lots = [lot for lot in lots if lot.parent_lot_id is not None]
    basic_lots = [lot for lot in lots if lot.parent_lot_id is None]

    if row_status == "COMPLETED":
        return rework_lots if rework_lots else basic_lots

    active_rework_lots = [lot for lot in rework_lots if lot.lot_id not in completed_lot_ids]
    if active_rework_lots:
        return active_rework_lots

    return [lot for lot in basic_lots if lot.lot_id not in completed_lot_ids] or basic_lots


def _get_lot_progress(
    lot_id: int,
    *,
    work_statuses_by_lot: dict[int, list[str | None]],
    schedule_statuses_by_lot: dict[int, list[str]],
    completed_lot_ids: set[int],
) -> LotProgress:
    if lot_id in completed_lot_ids:
        return _make_progress("COMPLETED")

    schedule_statuses = schedule_statuses_by_lot.get(lot_id, [])
    if "IN_PROGRESS" in schedule_statuses or "PARTIAL_DONE" in schedule_statuses:
        return _make_progress("INSPECTION_IN_PROGRESS")
    if "RECEIVED" in schedule_statuses:
        return _make_progress("INSPECTION_WAITING")

    work_statuses = work_statuses_by_lot.get(lot_id, [])
    if not work_statuses:
        return _make_progress("LOT_CREATED")

    if any(status is None for status in work_statuses):
        return _make_progress("OUTSOURCE_ORDERED")
    if any(status == "VENDOR_RECEIVED" for status in work_statuses):
        return _make_progress("DIECUT_RECEIVED")
    if any(status in {"WORK_DONE", "SHIPPED"} for status in work_statuses):
        return _make_progress("OUTSOURCE_DONE")

    return _make_progress("OUTSOURCE_ORDERED")


def _make_progress(process_code: str) -> LotProgress:
    return LotProgress(
        process_code=process_code,
        process_order=PROCESS_ORDER[process_code],
        progress_rate=PROCESS_PROGRESS[process_code],
    )


def _format_due_slack(due_days: int) -> str:
    if due_days > 0:
        return f"D-{due_days}"
    if due_days == 0:
        return "D-DAY"
    return f"D+{abs(due_days)}"


def _get_due_slack_level(due_days: int) -> str:
    if due_days >= 4:
        return "RELAXED"
    if due_days >= 1:
        return "IMMINENT"
    return "URGENT"
