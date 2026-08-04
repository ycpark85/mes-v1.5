from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db
from app.schemas.inspection_result import (
    DefectAttachmentUploadOut,
    InspectionResultGetOut,
    InspectionResultListOut,
    InspectionResultUpsertIn,
    InspectionResultUpsertOut,
)
from app.services.inspection_result_query import (
    get_inspection_result_detail,
    list_inspection_results_for_grid,
)
from app.services.inspection_result_attachment_service import (
    get_defect_attachment_download,
    save_defect_photo_upload,
)
from app.services.inspection_result_service import upsert_inspection_result

router = APIRouter(prefix="/inspection-schedules", tags=["InspectionResult"])


@router.get("/results/list", response_model=InspectionResultListOut)
def list_inspection_results(
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    partner_q: str | None = None,
    product_q: str | None = None,
    lot_q: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ = user
    return list_inspection_results_for_grid(
        db,
        date_from=date_from,
        date_to=date_to,
        q=q,
        partner_q=partner_q,
        product_q=product_q,
        lot_q=lot_q,
        page=page,
        size=size,
    )


@router.get("/{inspection_schedule_id}/result", response_model=InspectionResultGetOut)
def get_result(
    inspection_schedule_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ = user
    return get_inspection_result_detail(db, inspection_schedule_id)


@router.post(
    "/{inspection_schedule_id}/result/photos",
    response_model=DefectAttachmentUploadOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_result_photo(
    inspection_schedule_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ = user
    result = save_defect_photo_upload(
        db,
        inspection_schedule_id,
        file_name=file.filename or "",
        content_type=file.content_type,
        file_stream=file.file,
    )

    return {
        "file_uri": result.file_uri,
        "file_name": result.file_name,
        "mime_type": result.mime_type,
        "file_size": result.file_size,
    }

@router.get("/result/attachments/{attachment_id}/content")
def get_result_attachment_content(
    attachment_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ = user
    result = get_defect_attachment_download(db, attachment_id)
    db.close()

    return FileResponse(
        path=str(result.file_path),
        media_type=result.media_type,
        filename=result.file_name,
        content_disposition_type="inline",
        headers={"Cache-Control": "no-store"},
    )

@router.put("/{inspection_schedule_id}/result", response_model=InspectionResultUpsertOut)
def put_result(
    inspection_schedule_id: int,
    body: InspectionResultUpsertIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        actor = getattr(user, "username", None) or getattr(user, "login_id", None) or "system"

        result, sch_status, created_next_id = upsert_inspection_result(
            db,
            inspection_schedule_id,
            good_qty=body.good_qty,
            defect_ship_qty=body.defect_ship_qty,
            defect_qty=body.defect_qty,
            uninspected_qty=body.uninspected_qty,
            stock_ship_qty=body.stock_ship_qty,
            result_ship_qty=body.result_ship_qty,
            stock_in_qty=body.stock_in_qty,
            discard_qty=body.discard_qty,
            is_partial=body.is_partial,
            next_inspection_date=body.next_inspection_date,
            partial_reason=body.partial_reason,
            memo=body.memo,
            defects=body.defects,
            actor=actor,
            expected_updated_at=body.expected_updated_at,
        )
        db.commit()
        db.refresh(result)

        return {
            "result": result,
            "schedule_status": sch_status,
            "created_next_schedule_id": created_next_id,
        }
    except Exception:
        db.rollback()
        raise
