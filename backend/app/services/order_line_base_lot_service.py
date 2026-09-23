from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.schemas.order_line import OrderLineBaseLotCreateResult, OrderLineStatus
from app.services.order_line_creation_service import (
    create_primary_lot_for_order_line,
    ensure_product_active,
)
from app.services.order_line_plan_service import (
    get_latest_plan_history,
    get_planned_production_qty,
)


def create_base_lot_from_plan(db: Session, order_line_id: int) -> OrderLineBaseLotCreateResult:
    order_line = db.execute(select(OrderLine).where(OrderLine.order_line_id == order_line_id)
        .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if not order_line or not order_line.is_active:
        raise HTTPException(status_code=404, detail="OrderLine not found")

    if order_line.status != OrderLineStatus.OPEN.value:
        raise HTTPException(status_code=409, detail="기본 LOT는 OPEN 상태 수주에서만 생성할 수 있습니다.")

    lots = _load_order_line_lots(db, order_line_id)
    if any(l.parent_lot_id is None for l in lots):
        raise HTTPException(status_code=409, detail="이미 기본 LOT가 존재합니다.")

    if not order_line.decision_made:
        raise HTTPException(status_code=409, detail="처리계획이 먼저 저장되어야 합니다.")

    partner = db.get(Partner, order_line.partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    product = ensure_product_active(db, order_line.product_id)
    planned_production_qty = _get_planned_production_qty(db, order_line, partner.name)
    if planned_production_qty <= 0:
        raise HTTPException(
            status_code=409,
            detail="계획 생산수량이 0이어서 기본 LOT를 생성할 수 없습니다.",
        )

    lot = create_primary_lot_for_order_line(
        db,
        order_line,
        product,
        lot_qty=planned_production_qty,
    )

    return OrderLineBaseLotCreateResult(
        order_line_id=order_line.order_line_id,
        planned_production_qty=planned_production_qty,
        created_lot_id=lot.lot_id,
        created_lot_no=lot.lot_no,
        created_lot_qty=lot.lot_qty,
        order_status=order_line.status,
    )


def _load_order_line_lots(db: Session, order_line_id: int) -> list[Lot]:
    return (
        db.execute(
            select(Lot)
            .where(Lot.order_line_id == order_line_id)
            .order_by(Lot.created_date.asc(), Lot.lot_id.asc())
        )
        .scalars()
        .all()
    )


def _get_planned_production_qty(db: Session, order_line, partner_name: str) -> int:
    latest_plan_history = get_latest_plan_history(db, order_line.order_line_id)
    if latest_plan_history is not None:
        return int(latest_plan_history.production_qty or 0)

    return get_planned_production_qty(db, order_line, partner_name)
