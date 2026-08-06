# app/crud/lot.py
from __future__ import annotations

from datetime import date
from typing import Optional, Tuple, List, Dict

from sqlalchemy import select, func, or_, exists, and_
from sqlalchemy.orm import Session

from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.lot_step import LotStep
from app.models.order_line import OrderLine
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.partner import Partner
from app.models.product import Product



def _build_lot_list_status(
    lot_status: str,
    inspection_status: Optional[str],
    *,
    has_active_outsource_work: bool = False,
) -> tuple[str, str]:
    if lot_status == "CANCELED":
        return "CANCELED", "취소"

    if lot_status == "DONE" or inspection_status == "DONE":
        return "INSPECTION_DONE", "검수완료"

    if inspection_status in ("RECEIVED", "IN_PROGRESS", "PARTIAL_DONE"):
        return "INSPECTION_WAITING", "검수대기"

    if lot_status == "IN_PROGRESS" or has_active_outsource_work:
        return "IN_PROGRESS", "진행중"

    if lot_status == "WAITING":
        return "CREATED", "생성"

    return lot_status, lot_status

class LotCRUD:
    def get(self, db: Session, lot_id: int) -> Optional[Lot]:
        return db.get(Lot, lot_id)

    def create(self, db: Session, obj: Lot) -> Lot:
        db.add(obj)
        db.flush()
        db.refresh(obj)
        return obj

    def list_with_joins(
        self,
        db: Session,
        *,
        page: int,
        size: int,
        q: Optional[str] = None,
        status: Optional[str] = None,
        order_line_id: Optional[int] = None,
        product_id: Optional[int] = None,
        partner_id: Optional[int] = None,
        due_date_from: Optional[date] = None,
        due_date_to: Optional[date] = None,
        created_date_from: Optional[date] = None,
        created_date_to: Optional[date] = None,
        inspection_schedule_registered: Optional[bool] = None,
        sort: Optional[str] = None,
    ) -> Tuple[List[Dict], int]:
        latest_inspection_subq = (
            select(
                InspectionSchedule.inspection_schedule_id.label("inspection_schedule_id"),
                InspectionSchedule.lot_id.label("lot_id"),
                InspectionSchedule.status.label("inspection_status"),
                func.row_number()
                .over(
                    partition_by=InspectionSchedule.lot_id,
                    order_by=(
                        InspectionSchedule.inspection_date.desc(),
                        InspectionSchedule.inspection_schedule_id.desc(),
                    ),
                )
                .label("rn"),
            )
            .subquery()
        )
        active_outsource_lot_subq = (
            select(OutsourceWorkGroupItem.lot_id.label("lot_id"))
            .join(
                OutsourceWorkGroup,
                OutsourceWorkGroup.outsource_work_group_id
                == OutsourceWorkGroupItem.outsource_work_group_id,
            )
            .where(
                or_(
                    OutsourceWorkGroup.status.is_(None),
                    OutsourceWorkGroup.status != "CANCELED",
                )
            )
            .distinct()
            .subquery()
        )

        stmt = (
            select(
                Lot,
                OrderLine.order_no.label("order_no"),
                OrderLine.line_no.label("line_no"),
                OrderLine.partner_id.label("partner_id"),
                Partner.name.label("partner_name"),
                Product.product_code.label("product_code"),
                Product.product_name.label("product_name"),
                OrderLine.order_date.label("order_date"),
                OrderLine.order_qty.label("order_qty"),
                latest_inspection_subq.c.inspection_schedule_id.label("inspection_schedule_id"),
                latest_inspection_subq.c.inspection_status.label("inspection_status"),
                active_outsource_lot_subq.c.lot_id.label("active_outsource_lot_id"),
            )
            .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
            .join(Partner, Partner.partner_id == OrderLine.partner_id)
            .join(Product, Product.product_id == Lot.product_id)
            .outerjoin(
                latest_inspection_subq,
                and_(
                    latest_inspection_subq.c.lot_id == Lot.lot_id,
                    latest_inspection_subq.c.rn == 1,
                ),
            )
            .outerjoin(
                active_outsource_lot_subq,
                active_outsource_lot_subq.c.lot_id == Lot.lot_id,
            )
        )

        conds = []
        if order_line_id:
            conds.append(Lot.order_line_id == order_line_id)
        if product_id:
            conds.append(Lot.product_id == product_id)
        if partner_id:
            conds.append(OrderLine.partner_id == partner_id)

        if status:
            if status == "CREATED":
                conds.append(
                    and_(
                        Lot.status == "WAITING",
                        active_outsource_lot_subq.c.lot_id.is_(None),
                        or_(
                            latest_inspection_subq.c.inspection_status.is_(None),
                            latest_inspection_subq.c.inspection_status.in_(("WAITING", "CANCELED")),
                        ),
                    )
                )

            elif status == "IN_PROGRESS":
                conds.append(
                    and_(
                        Lot.status.notin_(("DONE", "CANCELED")),
                        or_(
                            latest_inspection_subq.c.inspection_status.is_(None),
                            latest_inspection_subq.c.inspection_status.in_(("WAITING", "CANCELED")),
                        ),
                        or_(
                            Lot.status == "IN_PROGRESS",
                            active_outsource_lot_subq.c.lot_id.is_not(None),
                        ),
                    )
                )

            elif status == "INSPECTION_WAITING":
                conds.append(
                    latest_inspection_subq.c.inspection_status.in_(
                        ("RECEIVED", "IN_PROGRESS", "PARTIAL_DONE")
                    )
                )

            elif status == "INSPECTION_DONE":
                conds.append(
                    or_(
                        Lot.status == "DONE",
                        latest_inspection_subq.c.inspection_status == "DONE",
                    )
                )

            elif status == "CANCELED":
                conds.append(Lot.status == "CANCELED")

            else:
                conds.append(Lot.status == status)    

        if due_date_from:
            conds.append(Lot.due_date >= due_date_from)
        if due_date_to:
            conds.append(Lot.due_date <= due_date_to)

        if created_date_from:
            conds.append(Lot.created_date >= created_date_from)
        if created_date_to:
            conds.append(Lot.created_date <= created_date_to)

        if q and q.strip():
            normalized_q = q.strip()
            like = f"%{normalized_q}%"
            conds.append(
                or_(
                    Lot.lot_no.ilike(like),
                    OrderLine.order_no == normalized_q.upper(),
                    Partner.name.ilike(like),
                    Product.product_name.ilike(like),
                    Product.product_code.ilike(like),
                )
            )
        if inspection_schedule_registered is not None:
            inspection_schedule_exists = exists(
                select(1).where(InspectionSchedule.lot_id == Lot.lot_id)
            )

            if inspection_schedule_registered:
                conds.append(inspection_schedule_exists)
            else:
                conds.append(~inspection_schedule_exists)    

        if conds:
            stmt = stmt.where(*conds)

        count_stmt = (
            select(func.count())
            .select_from(Lot)
            .join(OrderLine, OrderLine.order_line_id == Lot.order_line_id)
            .join(Partner, Partner.partner_id == OrderLine.partner_id)
            .join(Product, Product.product_id == Lot.product_id)
            .outerjoin(
                latest_inspection_subq,
                and_(
                    latest_inspection_subq.c.lot_id == Lot.lot_id,
                    latest_inspection_subq.c.rn == 1,
                ),
            )
            .outerjoin(
                active_outsource_lot_subq,
                active_outsource_lot_subq.c.lot_id == Lot.lot_id,
            )
        )
        if conds:
            count_stmt = count_stmt.where(*conds)

        total = db.execute(count_stmt).scalar_one()

        normalized_sort = (sort or "").strip().lower()

        if normalized_sort == "latest":
            stmt = stmt.order_by(Lot.created_at.desc(), Lot.lot_id.desc())
        else:
            stmt = stmt.order_by(Lot.due_date.asc(), Lot.created_date.asc(), Lot.lot_id.asc())

        stmt = stmt.offset((page - 1) * size).limit(size)

        rows = db.execute(stmt).all()

        items: List[Dict] = []
        for  (lot, 
              order_no, 
              line_no, 
              ol_partner_id, 
              partner_name, 
              product_code, 
              product_name,
              order_date,
              order_qty,
              inspection_schedule_id,
              inspection_status,
              active_outsource_lot_id,
        ) in rows:
            list_status, list_status_display = _build_lot_list_status(
                lot.status,
                inspection_status,
                has_active_outsource_work=active_outsource_lot_id is not None,
            )

            lot_type = "REWORK" if lot.parent_lot_id is not None else "PRIMARY"
            lot_type_display = "재작업 LOT" if lot.parent_lot_id is not None else "기본 LOT"

            items.append(
                {
                    "lot_id": lot.lot_id,
                    "lot_no": lot.lot_no,
                    "order_line_id": lot.order_line_id,
                    "product_id": lot.product_id,
                    "parent_lot_id": lot.parent_lot_id,
                    "lot_qty": int(lot.lot_qty),
                    "uom": lot.uom,
                    "created_date": lot.created_date,
                    "due_date": lot.due_date,
                    "status": lot.status,
                    "memo": lot.memo,
                    "created_at": lot.created_at,
                    "updated_at": lot.updated_at,
                    "order_no": order_no,
                    "line_no": line_no,
                    "partner_id": ol_partner_id,
                    "partner_name": partner_name,
                    "product_code": product_code,
                    "product_name": product_name,
                    "order_date": order_date,
                    "order_qty": order_qty,
                    "inspection_schedule_id": inspection_schedule_id,
                    "inspection_status": inspection_status,
                    "list_status": list_status,
                    "list_status_display": list_status_display,
                    "lot_type": lot_type,
                    "lot_type_display": lot_type_display,
                }
            )
        return items, total


lot_crud = LotCRUD()
