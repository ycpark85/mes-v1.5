from __future__ import annotations

from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, File, Query, UploadFile, status as http_status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
import app.services.bohyun_outsource_service as bohyun_outsource_service
from app.services.outsource_purchase_order_excel import (
    build_purchase_order_excel_download,
)
from app.services.outsource_purchase_order_query import (
    build_purchase_order_out,
    get_purchase_order_detail,
    list_purchase_order_targets,
    list_purchase_orders,
)
from app.services.outsource_purchase_order_service import (
    create_purchase_order,
)
from app.services.outsource_work_group_service import (
    cancel_work_group as cancel_work_group_service,
    update_work_group as update_work_group_service,
)
from app.services.outsource_work_instruction_file_service import (
    get_work_group_plate_data_file,
    save_plate_data_stream,
)
from app.services.outsource_work_instruction_service import (
    create_work_instruction_batch as create_work_instruction_batch_service,
)
from app.services.outsource_work_instruction_query import (
    build_work_instruction_out,
    build_work_group_detail,
    get_work_group_detail,
    list_candidate_lots,
    list_work_groups,
)
from app.schemas.outsource_work_instruction import (
    BohyunOutsourceGroupListOut,
    BohyunOutsourceGroupShipBatch,
    BohyunOutsourceGroupWorkDone,
    OutsourcePurchaseOrderCreate,
    OutsourcePurchaseOrderListOut,
    OutsourcePurchaseOrderOut,
    OutsourcePurchaseOrderTargetListOut,
    OutsourceWorkInstructionBatchCreate,
    OutsourceWorkInstructionBatchOut,
    OutsourceWorkInstructionCandidateLotListOut,
    OutsourceWorkInstructionPlateUploadOut,
    OutsourceWorkGroupCancelIn,
    OutsourceWorkGroupDetailOut,
    OutsourceWorkGroupListOut,
    OutsourceWorkGroupUpdateIn,
)

router = APIRouter(prefix="/outsource-work-instructions", tags=["OutsourceWorkInstruction"])


def _commit_work_group_change(
    db: Session,
    work_group,
) -> OutsourceWorkGroupDetailOut:
    db.commit()
    db.refresh(work_group)

    return build_work_group_detail(db, work_group)


def _commit_work_instruction_batch_creation(
    db: Session,
    created_instructions,
) -> OutsourceWorkInstructionBatchOut:
    db.commit()

    for instruction in created_instructions:
        db.refresh(instruction)

    return OutsourceWorkInstructionBatchOut(
        items=[
            build_work_instruction_out(db, instruction)
            for instruction in created_instructions
        ]
    )


def _commit_purchase_order_creation(
    db: Session,
    purchase_order,
) -> OutsourcePurchaseOrderOut:
    db.commit()
    db.refresh(purchase_order)

    return build_purchase_order_out(db, purchase_order)


def _commit_success(db: Session) -> dict[str, bool]:
    db.commit()

    return {"success": True}


@router.get("/groups", response_model=OutsourceWorkGroupListOut)
def get_outsource_work_groups(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    process_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return list_work_groups(
        db,
        date_from=date_from,
        date_to=date_to,
        process_type=process_type,
        status=status,
        q=q,
        page=page,
        size=size,
    )


@router.get("/groups/{outsource_work_group_id}", response_model=OutsourceWorkGroupDetailOut)
def get_outsource_work_group_detail(
    outsource_work_group_id: int,
    db: Session = Depends(get_db),
):
    return get_work_group_detail(db, outsource_work_group_id)


@router.put("/groups/{outsource_work_group_id}", response_model=OutsourceWorkGroupDetailOut)
def update_outsource_work_group(
    outsource_work_group_id: int,
    payload: OutsourceWorkGroupUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    work_group = update_work_group_service(
        db,
        outsource_work_group_id,
        payload,
        actor=current_user.login_id,
    )
    return _commit_work_group_change(db, work_group)


@router.post("/groups/{outsource_work_group_id}/cancel", response_model=OutsourceWorkGroupDetailOut)
def cancel_outsource_work_group(
    outsource_work_group_id: int,
    payload: OutsourceWorkGroupCancelIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    work_group = cancel_work_group_service(
        db,
        outsource_work_group_id,
        payload,
        actor=current_user.login_id,
    )
    return _commit_work_group_change(db, work_group)


@router.get("/bohyun-groups", response_model=BohyunOutsourceGroupListOut)
def get_bohyun_outsource_groups(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    process_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return bohyun_outsource_service.list_bohyun_outsource_groups(
        db,
        date_from=date_from,
        date_to=date_to,
        process_type=process_type,
        status=status,
        q=q,
        page=page,
        size=size,
        include_processing_fee=True,
    )


@router.post("/bohyun-groups/ship-batch")
def ship_bohyun_outsource_groups(
    payload: BohyunOutsourceGroupShipBatch,
    db: Session = Depends(get_db),
):
    bohyun_outsource_service.ship_bohyun_outsource_groups(db, payload.group_ids)
    return _commit_success(db)


@router.post("/bohyun-groups/{group_id}/inbound")
def inbound_bohyun_outsource_group(
    group_id: int,
    db: Session = Depends(get_db),
):
    bohyun_outsource_service.inbound_bohyun_outsource_group(db, group_id)
    return _commit_success(db)


@router.post("/bohyun-groups/{group_id}/work-done")
def complete_bohyun_outsource_group_work(
    group_id: int,
    payload: BohyunOutsourceGroupWorkDone,
    db: Session = Depends(get_db),
):
    bohyun_outsource_service.complete_bohyun_outsource_group_work(
        db,
        group_id,
        work_done_sheet_qty=payload.work_done_sheet_qty,
        outsource_processing_fee=payload.outsource_processing_fee,
        remark=payload.remark,
    )
    return _commit_success(db)


@router.get("/purchase-orders/{outsource_purchase_order_id}/excel")
def download_outsource_purchase_order_excel(
    outsource_purchase_order_id: int,
    db: Session = Depends(get_db),
):
    result = build_purchase_order_excel_download(db, outsource_purchase_order_id)
    db.close()

    return StreamingResponse(
        BytesIO(result.file_bytes),
        media_type=result.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
        },
    )


@router.post(
    "/upload-plate-data",
    response_model=OutsourceWorkInstructionPlateUploadOut,
    status_code=http_status.HTTP_201_CREATED,
)
def upload_plate_data(
    file: UploadFile = File(...),
):
    result = save_plate_data_stream(
        file_name=file.filename or "",
        content_type=file.content_type,
        file_stream=file.file,
    )

    return OutsourceWorkInstructionPlateUploadOut(
        file_name=result.file_name,
        file_path=result.file_path,
        content_type=result.content_type,
        file_size=result.file_size,
        uploaded_at=result.uploaded_at,
    )


@router.get("/work-groups/{group_id}/plate-data")
def download_work_group_plate_data(
    group_id: int,
    db: Session = Depends(get_db),
):
    result = get_work_group_plate_data_file(db, group_id)
    db.close()

    return FileResponse(
        path=result.file_path,
        media_type=result.media_type,
        filename=result.file_name,
    )


@router.get("/candidates", response_model=OutsourceWorkInstructionCandidateLotListOut)
def get_candidate_lots(
    process_type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return list_candidate_lots(
        db,
        process_type=process_type,
        q=q,
    )


@router.post(
    "/batch",
    response_model=OutsourceWorkInstructionBatchOut,
    status_code=http_status.HTTP_201_CREATED,
)
def create_outsource_work_instruction_batch(
    payload: OutsourceWorkInstructionBatchCreate,
    db: Session = Depends(get_db),
):
    created_instructions = create_work_instruction_batch_service(db, payload)
    return _commit_work_instruction_batch_creation(db, created_instructions)


@router.get(
    "/purchase-order-targets",
    response_model=OutsourcePurchaseOrderTargetListOut,
)
def get_purchase_order_targets(
    process_type: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return list_purchase_order_targets(
        db,
        process_type=process_type,
        page=page,
        size=size,
    )


@router.post(
    "/purchase-orders",
    response_model=OutsourcePurchaseOrderOut,
    status_code=http_status.HTTP_201_CREATED,
)
def create_outsource_purchase_order(
    payload: OutsourcePurchaseOrderCreate,
    db: Session = Depends(get_db),
):
    purchase_order = create_purchase_order(db, payload)
    return _commit_purchase_order_creation(db, purchase_order)


@router.get(
    "/purchase-orders/{outsource_purchase_order_id}",
    response_model=OutsourcePurchaseOrderOut,
)
# Deprecated candidate: current WPF does not call the purchase-order detail API.
# Keep until compatibility with old clients/direct API usage is confirmed.
def get_outsource_purchase_order(
    outsource_purchase_order_id: int,
    db: Session = Depends(get_db),
):
    return get_purchase_order_detail(db, outsource_purchase_order_id)


@router.get(
    "/purchase-orders",
    response_model=OutsourcePurchaseOrderListOut,
)
def get_outsource_purchase_orders(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    process_type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return list_purchase_orders(
        db,
        date_from=date_from,
        date_to=date_to,
        process_type=process_type,
        q=q,
        page=page,
        size=size,
    )
