from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.product_inventory_movement import ProductInventoryMovement
from app.services.inspection_schedule_service import resequence_inspection_date


@dataclass(frozen=True)
class CanceledScheduleCleanupRow:
    inspection_schedule_id: int
    lot_id: int
    lot_no: str
    inspection_date: date
    outsource_work_group_id: int
    outsource_work_group_item_id: int | None
    status: str
    day_seq: int | None
    received_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    memo: str | None
    created_at: datetime
    updated_at: datetime
    blocked_reasons: tuple[str, ...]


def cleanup_legacy_canceled_outsource_schedules(
    db: Session,
    *,
    apply: bool = False,
    expected_count: int | None = None,
) -> dict:
    rows = _load_cleanup_rows(db, lock=apply)
    safe_rows = [row for row in rows if not row.blocked_reasons]
    blocked_rows = [row for row in rows if row.blocked_reasons]

    report = {
        "candidate_count": len(rows),
        "safe_count": len(safe_rows),
        "blocked_count": len(blocked_rows),
        "applied": False,
        "deleted_count": 0,
        "rows": [asdict(row) for row in rows],
    }

    if not apply:
        return report

    if expected_count is None:
        raise ValueError("expected_count is required when apply=True")
    if len(safe_rows) != expected_count:
        raise RuntimeError(
            "Cleanup target count changed: "
            f"expected={expected_count}, actual={len(safe_rows)}"
        )
    if blocked_rows:
        raise RuntimeError(
            "Cleanup is blocked because referenced schedules exist: "
            f"blocked_count={len(blocked_rows)}"
        )

    affected_dates = sorted({row.inspection_date for row in safe_rows})
    schedule_ids = [row.inspection_schedule_id for row in safe_rows]
    schedules_by_id = {
        schedule.inspection_schedule_id: schedule
        for schedule in db.execute(
            select(InspectionSchedule).where(
                InspectionSchedule.inspection_schedule_id.in_(schedule_ids)
            )
        )
        .scalars()
        .all()
    }

    for schedule_id in schedule_ids:
        schedule = schedules_by_id.get(schedule_id)
        if schedule is None:
            raise RuntimeError(
                f"Cleanup target disappeared: inspection_schedule_id={schedule_id}"
            )
        db.delete(schedule)

    db.flush()

    for inspection_date in affected_dates:
        resequence_inspection_date(db, inspection_date)

    remaining_count = len(
        db.execute(
            select(InspectionSchedule.inspection_schedule_id).where(
                InspectionSchedule.inspection_schedule_id.in_(schedule_ids)
            )
        )
        .scalars()
        .all()
    )
    if remaining_count:
        raise RuntimeError(f"Cleanup verification failed: remaining={remaining_count}")

    report["applied"] = True
    report["deleted_count"] = len(schedule_ids)
    return report


def _load_cleanup_rows(
    db: Session,
    *,
    lock: bool,
) -> list[CanceledScheduleCleanupRow]:
    statement = (
        select(InspectionSchedule, Lot.lot_no)
        .join(Lot, Lot.lot_id == InspectionSchedule.lot_id)
        .join(
            OutsourceWorkGroup,
            OutsourceWorkGroup.outsource_work_group_id
            == InspectionSchedule.outsource_work_group_id,
        )
        .where(
            InspectionSchedule.status == "CANCELED",
            OutsourceWorkGroup.status == "CANCELED",
        )
        .order_by(InspectionSchedule.inspection_schedule_id.asc())
    )
    if lock:
        statement = statement.with_for_update(of=InspectionSchedule)

    schedule_rows = db.execute(statement).all()
    schedule_ids = [row.InspectionSchedule.inspection_schedule_id for row in schedule_rows]
    if not schedule_ids:
        return []

    result_schedule_ids = set(
        db.execute(
            select(InspectionResult.inspection_schedule_id).where(
                InspectionResult.inspection_schedule_id.in_(schedule_ids)
            )
        )
        .scalars()
        .all()
    )
    movement_schedule_ids = set(
        db.execute(
            select(ProductInventoryMovement.inspection_schedule_id).where(
                ProductInventoryMovement.inspection_schedule_id.in_(schedule_ids)
            )
        )
        .scalars()
        .all()
    )

    cleanup_rows: list[CanceledScheduleCleanupRow] = []
    for schedule_row in schedule_rows:
        schedule = schedule_row.InspectionSchedule
        blocked_reasons: list[str] = []
        if schedule.inspection_schedule_id in result_schedule_ids:
            blocked_reasons.append("INSPECTION_RESULT")
        if schedule.inspection_schedule_id in movement_schedule_ids:
            blocked_reasons.append("PRODUCT_INVENTORY_MOVEMENT")

        cleanup_rows.append(
            CanceledScheduleCleanupRow(
                inspection_schedule_id=schedule.inspection_schedule_id,
                lot_id=schedule.lot_id,
                lot_no=schedule_row.lot_no,
                inspection_date=schedule.inspection_date,
                outsource_work_group_id=schedule.outsource_work_group_id,
                outsource_work_group_item_id=schedule.outsource_work_group_item_id,
                status=schedule.status,
                day_seq=schedule.day_seq,
                received_at=schedule.received_at,
                started_at=schedule.started_at,
                finished_at=schedule.finished_at,
                memo=schedule.memo,
                created_at=schedule.created_at,
                updated_at=schedule.updated_at,
                blocked_reasons=tuple(blocked_reasons),
            )
        )

    return cleanup_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Safely remove legacy CANCELED inspection schedules linked to "
            "CANCELED outsource work groups. The default mode is read-only."
        )
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--expected-app-env")
    parser.add_argument("--expected-database")
    parser.add_argument("--backup-root")
    parser.add_argument("--preview-limit", type=int, default=30)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    database_name = str(engine.url.database or "")
    app_env = settings.app_env.strip()

    if args.apply:
        if args.expected_count is None or args.expected_count < 0:
            raise ValueError("--expected-count with a non-negative value is required")
        if not args.expected_app_env or args.expected_app_env.strip() != app_env:
            raise ValueError(
                f"--expected-app-env must exactly match current APP_ENV={app_env}"
            )
        if not args.expected_database or args.expected_database.strip() != database_name:
            raise ValueError(
                "--expected-database must exactly match the current database name"
            )
        if not args.backup_root:
            raise ValueError("--backup-root is required when --apply is used")

    db = SessionLocal()
    try:
        report = cleanup_legacy_canceled_outsource_schedules(
            db,
            apply=args.apply,
            expected_count=args.expected_count,
        )
        if args.apply:
            report["backup_path"] = _write_backup(
                backup_root=Path(args.backup_root),
                app_env=app_env,
                database_name=database_name,
                report=report,
            )
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    rows = report.pop("rows")
    report["app_env"] = app_env
    report["database"] = database_name
    report["rows"] = rows[: args.preview_limit]
    report["preview_truncated"] = len(rows) > args.preview_limit
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    if report["blocked_count"]:
        return 2
    return 0


def _write_backup(
    *,
    backup_root: Path,
    app_env: str,
    database_name: str,
    report: dict,
) -> str:
    backup_root = backup_root.resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_root / f"inspection-schedule-cleanup-{timestamp}.json"
    payload = {
        "created_at_utc": timestamp,
        "app_env": app_env,
        "database": database_name,
        "candidate_count": report["candidate_count"],
        "rows": report["rows"],
    }

    with backup_path.open("x", encoding="utf-8") as backup_file:
        json.dump(payload, backup_file, ensure_ascii=False, indent=2, default=str)
        backup_file.flush()
        os.fsync(backup_file.fileno())

    return str(backup_path)


if __name__ == "__main__":
    raise SystemExit(main())
