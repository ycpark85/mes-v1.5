# app/api/v1/order_lines.py
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.crud.order_line import order_line_crud
from app.db.session import get_db, set_local_statement_timeout
from app.models.user import User
from app.schemas.lot_create_context import LotCreateContextDto
from app.schemas.order_line import (
    OrderLineBaseLotCreateResult,
    OrderLineBulkCommitRequest,
    OrderLineBulkCommitResult,
    OrderLineBulkValidateRequest,
    OrderLineBulkValidateResult,
    OrderLineCreate,
    OrderLineListOut,
    OrderLineOut,
    OrderLinePlanConfirmRequest,
    OrderLineShortCloseRequest,
    OrderLineUpdate,
    PageMeta,
)
from app.schemas.order_line_detail import OrderLineDetailDto, OrderLineDetailUpdate
from app.services.bulk.order_line_bulk_service import order_line_bulk_service
from app.services.order_line_creation_service import (
    create_primary_lot_for_order_line,
    create_order_line_with_policy as _create_order_line_with_policy,
)
from app.services.order_line_base_lot_service import create_base_lot_from_plan
from app.services.order_line_cancel_service import cancel_order_line_status
from app.services.order_line_detail_query import get_order_line_detail_dto
from app.services.order_line_detail_update_service import update_order_line_detail_fields
from app.services.order_line_delete_service import delete_order_line_group
from app.services.order_line_lot_context_query import get_lot_create_context_dto
from app.services.order_line_list_query import list_order_lines_for_grid
from app.services.order_line_plan_service import (
    confirm_order_line_plan_decision,
    get_latest_plan_history as _get_latest_plan_history,
)
from app.services.order_line_response_builder import (
    build_order_line_out,
    get_order_line_out_by_id,
)
from app.services.order_line_manual_close_service import manual_close_order_line, reopen_manual_order_line
from app.services.order_line_update_service import update_order_line_fields

router = APIRouter(prefix="/order-lines", tags=["OrderLine"])


@router.post("/bulk/commit", response_model=OrderLineBulkCommitResult)
def commit_order_lines_bulk(
    payload: OrderLineBulkCommitRequest,
    db: Session = Depends(get_db),
):
    try:
        set_local_statement_timeout(db)
        result = order_line_bulk_service.commit_bulk(db, payload)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="벌크 수주 등록 중 무결성 오류가 발생했습니다.")

    return result


@router.post("/bulk/validate", response_model=OrderLineBulkValidateResult)
def validate_order_lines_bulk(
    payload: OrderLineBulkValidateRequest,
    db: Session = Depends(get_db),
):
    set_local_statement_timeout(db)
    return order_line_bulk_service.validate_bulk(db, payload)


@router.post("", response_model=OrderLineOut, status_code=http_status.HTTP_201_CREATED)
def create_order_line(payload: OrderLineCreate, db: Session = Depends(get_db)):
    try:
        obj = _create_order_line_with_policy(db, payload)

        db.commit()
        db.refresh(obj)

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Duplicate order_no+line_no or integrity error",
        )

    latest_plan_history = _get_latest_plan_history(db, obj.order_line_id)

    return build_order_line_out(db, obj, plan_history=latest_plan_history)

@router.post("/{order_line_id}/plan/confirm", response_model=OrderLineOut)
def confirm_order_line_plan(
    order_line_id: int,
    payload: OrderLinePlanConfirmRequest,
    db: Session = Depends(get_db),
):
    try:
        order_line, history, partner, product = confirm_order_line_plan_decision(
            db,
            order_line_id=order_line_id,
            payload=payload,
        )
        if history.plan_type == "STOCK_REPLENISHMENT":
            create_primary_lot_for_order_line(
                db,
                order_line,
                product,
                lot_qty=int(order_line.order_qty or 0),
            )
        db.commit()
        db.refresh(order_line)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="처리계획 확정 중 무결성 오류가 발생했습니다.",
        )

    return build_order_line_out(
        db,
        order_line,
        plan_history=history,
        partner=partner,
        product=product,
    )


@router.get("", response_model=OrderLineListOut)
def list_order_lines(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    q: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    status_group: Optional[str] = Query(None),
    work_queue: Optional[Literal["LOT_CREATION", "CLOSE_DECISION"]] = Query(None),
    is_active: Optional[bool] = Query(True),
    partner_id: Optional[int] = Query(None),
    product_id: Optional[int] = Query(None),
    order_date_from: Optional[date] = Query(None),
    order_date_to: Optional[date] = Query(None),
    due_date_from: Optional[date] = Query(None),
    due_date_to: Optional[date] = Query(None),
):
    items, total, queue_counts = list_order_lines_for_grid(
        db,
        page=page,
        size=size,
        q=q,
        status=status,
        status_group=status_group,
        work_queue=work_queue,
        is_active=is_active,
        partner_id=partner_id,
        product_id=product_id,
        order_date_from=order_date_from,
        order_date_to=order_date_to,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
    )

    return OrderLineListOut(
        items=[OrderLineOut(**x) for x in items],
        meta=PageMeta(page=page, size=size, total=total),
        queue_counts=queue_counts,
    )


@router.patch("/{order_line_id}", response_model=OrderLineOut)
def update_order_line(
    order_line_id: int,
    payload: OrderLineUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        obj = update_order_line_fields(
            db,
            order_line_id,
            payload,
            actor=current_user.login_id,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate order_no+line_no or integrity error")

    return build_order_line_out(db, obj)


@router.delete("/{order_line_id}")
def delete_order_line(order_line_id: int, db: Session = Depends(get_db)):
    order_no_for_message: str | None = None
    current_order_line = order_line_crud.get(db, order_line_id)
    if current_order_line is not None:
        order_no_for_message = current_order_line.order_no

    try:
        result = delete_order_line_group(db, order_line_id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        target_label = (
            f"수주번호 {order_no_for_message}"
            if order_no_for_message
            else f"수주 ID {order_line_id}"
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"{target_label} 삭제 중 연결 데이터 제약이 발생했습니다. "
                "출하, 외주, 검수, 재고 관련 데이터를 확인하세요."
            ),
        )

    return result


@router.get("/{order_line_id}/detail", response_model=OrderLineDetailDto)
def get_order_line_detail(order_line_id: int, db: Session = Depends(get_db)):
    return get_order_line_detail_dto(db, order_line_id)


@router.post("/{order_line_id}/base-lot", response_model=OrderLineBaseLotCreateResult)
def create_base_lot_from_fulfillment_plan(
    order_line_id: int,
    db: Session = Depends(get_db),
):
    try:
        result = create_base_lot_from_plan(db, order_line_id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="기본 LOT 생성 중 무결성 오류가 발생했습니다.")

    return result


@router.get("/{order_line_id}/lot-create-context", response_model=LotCreateContextDto)
def get_lot_create_context(order_line_id: int, db: Session = Depends(get_db)):
    return get_lot_create_context_dto(db, order_line_id)


@router.get("/{order_line_id}", response_model=OrderLineOut)
def get_order_line(order_line_id: int, db: Session = Depends(get_db)):
    return get_order_line_out_by_id(db, order_line_id)


@router.patch("/{order_line_id}/detail", response_model=OrderLineDetailDto)
def update_order_line_detail(
    order_line_id: int,
    payload: OrderLineDetailUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        order_line = update_order_line_detail_fields(
            db,
            order_line_id,
            payload,
            actor=current_user.login_id,
        )
        db.commit()
        db.refresh(order_line)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="수주 상세 수정 중 무결성 오류가 발생했습니다.")

    return get_order_line_detail_dto(db, order_line_id, include_plan_history=False)


@router.patch("/{order_line_id}/short-close", response_model=OrderLineOut)
@router.patch("/{order_line_id}/manual-close", response_model=OrderLineOut)
def short_close_order_line(
    order_line_id: int,
    payload: OrderLineShortCloseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        obj = manual_close_order_line(db, order_line_id, payload, actor=current_user.login_id)
        db.commit()
        db.refresh(obj)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="부족종료 처리 중 무결성 오류가 발생했습니다.")

    return build_order_line_out(db, obj)


@router.patch("/{order_line_id}/manual-reopen", response_model=OrderLineOut)
def reopen_order_line(
    order_line_id: int,
    payload: OrderLineShortCloseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        obj = reopen_manual_order_line(db, order_line_id, payload, actor=current_user.login_id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="완료 취소 중 무결성 오류가 발생했습니다.")
    return build_order_line_out(db, obj)


@router.post("/{order_line_id}/cancel", response_model=OrderLineDetailDto)
def cancel_order_line(
    order_line_id: int,
    db: Session = Depends(get_db),
):
    try:
        cancel_order_line_status(db, order_line_id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="수주 취소 중 무결성 오류가 발생했습니다.")

    return get_order_line_detail_dto(db, order_line_id, include_plan_history=False)
