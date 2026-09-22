# app/api/v1/inspection_schedules.py
from __future__ import annotations

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.inspection_read import get_inspection_read_db
from app.services.inspection_schedule_service import (
    cancel_inspection_schedule as cancel_inspection_schedule_service,
    create_inspection_schedule as create_inspection_schedule_service,
    receive_inspection_schedule as receive_inspection_schedule_service,
    reorder_inspection_schedules as reorder_inspection_schedules_service,
    start_inspection_schedule as start_inspection_schedule_service,
    update_inspection_schedule as update_inspection_schedule_service,
)
from app.services.inspection_schedule_query import (
    get_inspection_schedule_detail,
    list_inspection_stock_lots,
)
from app.services.inspection_work_instruction_query import (
    list_inspection_schedule_items,
    list_inspection_work_instruction_targets,
)
from app.services.outsource_work_instruction_file_service import (
    get_inspection_schedule_plate_data_file,
)
from app.schemas.inspection_schedule import (
    InspectionScheduleCreate,
    InspectionScheduleListItemOut,
    InspectionScheduleOut,
    InspectionScheduleReorderIn,
    InspectionScheduleUpdate,
    InspectionWorkInstructionTargetListOut,
    InspectionStockLotListOut,
)



router = APIRouter(prefix="/inspection-schedules", tags=["InspectionSchedule"])


@router.post("", response_model=InspectionScheduleOut, status_code=status.HTTP_201_CREATED)
def create_inspection_schedule(
    payload: InspectionScheduleCreate,
    db: Session = Depends(get_db),
):
    try:
        selected_schedule = create_inspection_schedule_service(db, payload)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Inspection schedule already exists for this lot and date",
        )

    db.refresh(selected_schedule)

    return selected_schedule


@router.patch("/{inspection_schedule_id}", response_model=InspectionScheduleOut)
def update_inspection_schedule(
    inspection_schedule_id: int,
    payload: InspectionScheduleUpdate,
    db: Session = Depends(get_db),
):
    try:
        obj = update_inspection_schedule_service(db, inspection_schedule_id, payload)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate (lot_id, inspection_date) is not allowed")

    db.refresh(obj)
    return obj


@router.post("/{inspection_schedule_id}/receive", response_model=InspectionScheduleOut)
def receive_inspection_schedule(
    inspection_schedule_id: int,
    db: Session = Depends(get_db),
):
    obj = receive_inspection_schedule_service(db, inspection_schedule_id)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/{inspection_schedule_id}/start", response_model=InspectionScheduleOut)
def start_inspection_schedule(
    inspection_schedule_id: int,
    db: Session = Depends(get_db),
):
    obj = start_inspection_schedule_service(db, inspection_schedule_id)
    db.commit()
    db.refresh(obj)
    return obj

@router.post("/{inspection_schedule_id}/cancel", response_model=InspectionScheduleOut)
def cancel_inspection_schedule(
    inspection_schedule_id: int,
    db: Session = Depends(get_db),
):
    obj = cancel_inspection_schedule_service(db, inspection_schedule_id)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/reorder", response_model=list[InspectionScheduleOut])
def reorder_inspection_schedules(
    payload: InspectionScheduleReorderIn,
    db: Session = Depends(get_db),
):
    try:
        ordered_rows = reorder_inspection_schedules_service(db, payload)
        db.commit()

        return ordered_rows

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Reorder failed due to constraint violation")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Reorder failed: {type(e).__name__}")

@router.get(
    "/work-instruction-targets",
    response_model=InspectionWorkInstructionTargetListOut,
)
def get_inspection_work_instruction_targets(
    partner_q: Optional[str] = None,
    product_q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_inspection_work_instruction_targets(
        db,
        partner_q=partner_q,
        product_q=product_q,
        limit=limit,
        offset=offset,
    )


@router.get("", response_model=list[InspectionScheduleListItemOut])
def list_inspection_schedules(
    inspection_date_from: Optional[date] = None,
    inspection_date_to: Optional[date] = None,
    status: Optional[str] = None,
    partner_q: Optional[str] = None,
    product_q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_inspection_schedule_items(
        db,
        inspection_date_from=inspection_date_from,
        inspection_date_to=inspection_date_to,
        status=status,
        partner_q=partner_q,
        product_q=product_q,
        limit=limit,
        offset=offset,
    )


@router.get("/{inspection_schedule_id}/plate-data")
def download_inspection_schedule_plate_data(
    inspection_schedule_id: int,
    db: Session = Depends(get_db),
):
    plate_data = get_inspection_schedule_plate_data_file(db, inspection_schedule_id)
    db.close()

    return FileResponse(
        path=plate_data.file_path,
        media_type=plate_data.media_type,
        filename=plate_data.file_name,
    )


@router.get("/{inspection_schedule_id}/stock-lots", response_model=InspectionStockLotListOut)
def get_inspection_stock_lots(
    inspection_schedule_id: int,
    db: Session = Depends(get_inspection_read_db),
):
    return list_inspection_stock_lots(db, inspection_schedule_id)

@router.get("/{inspection_schedule_id}", response_model=InspectionScheduleOut)
def get_inspection_schedule(
    inspection_schedule_id: int,
    db: Session = Depends(get_db),
):
    return get_inspection_schedule_detail(db, inspection_schedule_id)
