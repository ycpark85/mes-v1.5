from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.time import korea_today
from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.outsource_work_group import OutsourceWorkGroup
from app.models.outsource_work_group_item import OutsourceWorkGroupItem
from app.models.partner import Partner
from app.models.process import Process
from app.models.product import Product
from app.models.routing_template_step import RoutingTemplateStep
from app.models.shipment_coa import ShipmentCoa
from app.models.shipment_line import ShipmentLine
from app.schemas.shipment_coa import ShipmentCoaUpdateRequest
from app.services.order_line_display import order_product_name, order_product_spec


def _clean_text(value: Optional[str], default: str = "-") -> str:
    if value is None:
        return default

    normalized = value.strip()
    return normalized if normalized else default


def _append_unique(target: list[str], value: Optional[str]) -> None:
    if value is None:
        return

    normalized = value.strip()
    if not normalized:
        return

    if normalized not in target:
        target.append(normalized)


def _build_lot_text(values: list[str]) -> str:
    return ",\n".join(values) if values else "-"


def _is_printed_product(
    db: Session,
    product_id: int,
    lot_ids: list[int],
    outsource_work_group_ids: list[int],
) -> bool:
    if outsource_work_group_ids:
        actual_group = (
            db.execute(
                select(OutsourceWorkGroup.outsource_work_group_id)
                .where(
                    OutsourceWorkGroup.outsource_work_group_id.in_(outsource_work_group_ids),
                    func.upper(OutsourceWorkGroup.process_type) == "PRINT",
                )
                .limit(1)
            )
            .first()
        )

        if actual_group is not None:
            return True

    if lot_ids:
        actual_lot_group = (
            db.execute(
                select(OutsourceWorkGroup.outsource_work_group_id)
                .select_from(OutsourceWorkGroup)
                .join(
                    OutsourceWorkGroupItem,
                    OutsourceWorkGroupItem.outsource_work_group_id
                    == OutsourceWorkGroup.outsource_work_group_id,
                )
                .where(
                    OutsourceWorkGroupItem.lot_id.in_(lot_ids),
                    func.upper(OutsourceWorkGroup.process_type) == "PRINT",
                )
                .limit(1)
            )
            .first()
        )

        if actual_lot_group is not None:
            return True

    route_process = (
        db.execute(
            select(Process.process_id)
            .select_from(Product)
            .join(
                RoutingTemplateStep,
                RoutingTemplateStep.routing_template_id == Product.routing_template_id,
            )
            .join(Process, Process.process_id == RoutingTemplateStep.process_id)
            .where(
                Product.product_id == product_id,
                RoutingTemplateStep.is_active.is_(True),
                or_(
                    func.upper(Process.process_type) == "PRINT",
                    func.upper(Process.process_code).like("%PRINT%"),
                    Process.process_name.ilike("%인쇄%"),
                ),
            )
            .limit(1)
        )
        .first()
    )

    return route_process is not None


def get_or_create_shipment_coa(db: Session, order_line_id: int) -> ShipmentCoa:
    existing = (
        db.execute(
            select(ShipmentCoa).where(ShipmentCoa.order_line_id == order_line_id)
        )
        .scalar_one_or_none()
    )

    if existing is not None:
        if existing.is_printed_product_snapshot is None:
            rows_for_print = (
                db.execute(
                    select(
                        ShipmentLine.lot_id,
                        InspectionSchedule.outsource_work_group_id,
                    )
                    .select_from(ShipmentLine)
                    .outerjoin(
                        InspectionResult,
                        InspectionResult.inspection_result_id
                        == ShipmentLine.inspection_result_id,
                    )
                    .outerjoin(
                        InspectionSchedule,
                        InspectionSchedule.inspection_schedule_id
                        == InspectionResult.inspection_schedule_id,
                    )
                    .where(
                        ShipmentLine.order_line_id == order_line_id,
                        ShipmentLine.status == "DONE",
                    )
                )
                .all()
            )

            lot_ids = sorted(
                {
                    int(lot_id)
                    for lot_id, _ in rows_for_print
                    if lot_id is not None
                }
            )

            outsource_work_group_ids = sorted(
                {
                    int(outsource_work_group_id)
                    for _, outsource_work_group_id in rows_for_print
                    if outsource_work_group_id is not None
                }
            )

            existing.is_printed_product_snapshot = _is_printed_product(
                db,
                existing.product_id,
                lot_ids,
                outsource_work_group_ids,
            )

            db.commit()
            db.refresh(existing)

        return existing

    rows = (
        db.execute(
            select(
                ShipmentLine,
                OrderLine,
                Product,
                Partner,
                Lot,
                InspectionSchedule,
            )
            .select_from(ShipmentLine)
            .join(OrderLine, OrderLine.order_line_id == ShipmentLine.order_line_id)
            .join(Product, Product.product_id == ShipmentLine.product_id)
            .join(Partner, Partner.partner_id == OrderLine.partner_id)
            .outerjoin(Lot, Lot.lot_id == ShipmentLine.lot_id)
            .outerjoin(
                InspectionResult,
                InspectionResult.inspection_result_id
                == ShipmentLine.inspection_result_id,
            )
            .outerjoin(
                InspectionSchedule,
                InspectionSchedule.inspection_schedule_id
                == InspectionResult.inspection_schedule_id,
            )
            .where(
                ShipmentLine.order_line_id == order_line_id,
                ShipmentLine.status == "DONE",
            )
            .order_by(ShipmentLine.shipment_line_id.asc())
        )
        .all()
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="출하완료된 COA 대상이 없습니다.",
        )

    _, first_order_line, first_product, first_partner, _, _ = rows[0]

    stock_lot_nos: list[str] = []
    production_lot_nos: list[str] = []
    inspection_dates: list[date] = []
    shipped_dates: list[date] = []
    lot_ids: list[int] = []
    outsource_work_group_ids: list[int] = []

    quantity_snapshot = 0

    for shipment_line, _, _, _, lot, inspection_schedule in rows:
        quantity_snapshot += int(
            shipment_line.shipped_qty
            or shipment_line.ship_qty
            or 0
        )

        if shipment_line.lot_id is not None and shipment_line.lot_id not in lot_ids:
            lot_ids.append(shipment_line.lot_id)

        if shipment_line.source_type == "STOCK":
            _append_unique(stock_lot_nos, shipment_line.stock_lot_no or (lot.lot_no if lot else None))
        elif lot is not None:
            if shipment_line.source_type == "INSPECTION_RESULT":
                _append_unique(production_lot_nos, lot.lot_no)

        if inspection_schedule is not None:
            if inspection_schedule.inspection_date is not None:
                inspection_dates.append(inspection_schedule.inspection_date)

            if (
                inspection_schedule.outsource_work_group_id is not None
                and inspection_schedule.outsource_work_group_id not in outsource_work_group_ids
            ):
                outsource_work_group_ids.append(inspection_schedule.outsource_work_group_id)

        if shipment_line.shipped_at is not None:
            shipped_dates.append(shipment_line.shipped_at.date())

    all_lot_nos = stock_lot_nos + production_lot_nos

    if inspection_dates:
        inspection_date_snapshot = max(inspection_dates)
    elif shipped_dates:
        inspection_date_snapshot = max(shipped_dates)
    else:
        inspection_date_snapshot = korea_today()

    is_printed_product_snapshot = _is_printed_product(
        db,
        first_product.product_id,
        lot_ids,
        outsource_work_group_ids,
    )

    coa = ShipmentCoa(
        order_line_id=first_order_line.order_line_id,
        product_id=first_product.product_id,
        product_name_snapshot=_clean_text(order_product_name(first_order_line, first_product)),
        product_spec_snapshot=_clean_text(order_product_spec(first_order_line, first_product)),
        material_snapshot="COATED TYVEK",
        partner_name_snapshot=_clean_text(first_partner.name),
        lot_nos_snapshot=_build_lot_text(all_lot_nos),
        stock_lot_nos_snapshot=_build_lot_text(stock_lot_nos) if stock_lot_nos else None,
        production_lot_nos_snapshot=_build_lot_text(production_lot_nos) if production_lot_nos else None,
        quantity_snapshot=quantity_snapshot,
        inspection_date_snapshot=inspection_date_snapshot,
        is_printed_product_snapshot=is_printed_product_snapshot,
        memo=None,
    )

    db.add(coa)
    db.commit()
    db.refresh(coa)

    return coa


def update_shipment_coa(
    db: Session,
    order_line_id: int,
    payload: ShipmentCoaUpdateRequest,
) -> ShipmentCoa:
    coa = get_or_create_shipment_coa(db, order_line_id)

    coa.quantity_snapshot = payload.quantity_snapshot
    coa.inspection_date_snapshot = payload.inspection_date_snapshot
    coa.memo = payload.memo.strip() if payload.memo and payload.memo.strip() else None

    db.commit()
    db.refresh(coa)

    return coa
