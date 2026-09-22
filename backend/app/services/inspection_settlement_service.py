from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.inspection_result import InspectionResult
from app.models.inspection_schedule import InspectionSchedule
from app.models.shipment_line import ShipmentLine


def get_settlement_sources(
    db: Session, *, schedule: InspectionSchedule, result: InspectionResult | None,
) -> tuple[list[InspectionResult], str | None]:
    """Read explicit ownership on edits; take only earlier unsettled rounds on insert."""
    if result is not None:
        if (result.settlement_owner_id != result.inspection_result_id
                or result.settled_sellable_qty != result.good_qty + result.defect_ship_qty):
            return [], "기존 실적의 정산 연결을 확인해야 합니다. 수량을 줄이지 말고 정산 자료를 점검하세요."
        if db.execute(select(ShipmentLine.shipment_line_id).where(
            ShipmentLine.inspection_result_id == result.inspection_result_id,
            ShipmentLine.status == "WAITING",
        ).limit(1)).scalar_one_or_none() is not None:
            return [], "이전 방식의 미완료 출고가 남아 있습니다. 기존 출고와 예약을 먼저 점검하세요."
        sources = db.execute(select(InspectionResult).where(
            InspectionResult.settlement_owner_id == result.inspection_result_id,
            InspectionResult.inspection_result_id != result.inspection_result_id,
        )).scalars().all()
        for source in sources:
            source_schedule = db.get(InspectionSchedule, source.inspection_schedule_id)
            if (source.settled_sellable_qty != source.good_qty + source.defect_ship_qty
                    or source_schedule is None or source_schedule.lot_id != schedule.lot_id
                    or (source_schedule.inspection_date, source_schedule.inspection_schedule_id)
                    >= (schedule.inspection_date, schedule.inspection_schedule_id)):
                return [], "이월 정산 연결의 LOT 또는 회차 순서가 일치하지 않습니다."
        return sources, None

    sources = db.execute(
        select(InspectionResult).join(InspectionSchedule).where(
            InspectionSchedule.lot_id == schedule.lot_id,
            InspectionSchedule.status == "PARTIAL_DONE",
            InspectionResult.settled_at.is_(None),
            InspectionResult.settlement_owner_id.is_(None),
            or_(
                InspectionSchedule.inspection_date < schedule.inspection_date,
                and_(InspectionSchedule.inspection_date == schedule.inspection_date,
                     InspectionSchedule.inspection_schedule_id < schedule.inspection_schedule_id),
            ),
        ).order_by(InspectionSchedule.inspection_date, InspectionSchedule.inspection_schedule_id)
    ).scalars().all()
    return sources, None


def settlement_carry_qty(sources: list[InspectionResult], *, existing: bool) -> int:
    return sum(int(row.settled_sellable_qty or 0) if existing else
               int(row.good_qty or 0) + int(row.defect_ship_qty or 0) for row in sources)
