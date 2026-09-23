from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.services.lot_query import get_lot_detail, list_lots as list_lots_query
from app.services.lot_rework_service import create_rework_lot
from app.services.lot_trace_query import get_lot_trace_detail_for_lot

from app.schemas.lot import (
    LotCreate,
    LotDetailOut,
    LotListOut,
    LotTraceDetailOut,
)

router = APIRouter(prefix="/lots", tags=["Lot"])


@router.post("", response_model=LotDetailOut, status_code=http_status.HTTP_201_CREATED)
def create_lot(payload: LotCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        result = create_rework_lot(db, payload, actor=current_user.login_id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="LOT creation integrity error")

    return result


@router.get("", response_model=LotListOut)
def list_lots(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    q: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    order_line_id: Optional[int] = Query(None),
    product_id: Optional[int] = Query(None),
    partner_id: Optional[int] = Query(None),
    due_date_from: Optional[date] = Query(None),
    due_date_to: Optional[date] = Query(None),
    created_date_from: Optional[date] = Query(None),
    created_date_to: Optional[date] = Query(None),
    inspection_schedule_registered: Optional[bool] = Query(None),
    sort: Optional[str] = Query(None),
):
    return list_lots_query(
        db,
        page=page,
        size=size,
        status=status,
        q=q,
        order_line_id=order_line_id,
        product_id=product_id,
        partner_id=partner_id,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
        created_date_from=created_date_from,
        created_date_to=created_date_to,
        inspection_schedule_registered=inspection_schedule_registered,
        sort=sort,
    )

@router.get("/{lot_id}/detail", response_model=LotTraceDetailOut)
def get_lot_trace_detail(
    lot_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return get_lot_trace_detail_for_lot(
        db,
        lot_id,
        attachment_content_url_builder=lambda attachment_id: str(
            request.url_for(
                "get_result_attachment_content",
                attachment_id=attachment_id,
            )
        ),
    )

@router.get("/{lot_id}", response_model=LotDetailOut)
def get_lot(lot_id: int, db: Session = Depends(get_db)):
    return get_lot_detail(db, lot_id)

