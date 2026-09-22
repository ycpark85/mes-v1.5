from __future__ import annotations

from typing import Sequence
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.models.inspection_result import InspectionResult
from app.models.inspection_defect import InspectionDefect
from app.models.inspection_defect_attachment import InspectionDefectAttachment
from app.models.inspection_certificate import InspectionCertificate
from app.models.shipment_coa import ShipmentCoa
from app.models.shipment_line import ShipmentLine
from app.schemas.inspection_result import DefectLineIn

def defect_snapshot(db: Session, result_id: int) -> list[dict]:
    rows = db.execute(select(InspectionDefect).where(
        InspectionDefect.inspection_result_id == result_id,
    ).order_by(InspectionDefect.inspection_defect_id)).scalars().all()
    values = []
    for row in rows:
        attachments = db.execute(select(InspectionDefectAttachment).where(
            InspectionDefectAttachment.inspection_defect_id == row.inspection_defect_id,
        ).order_by(InspectionDefectAttachment.inspection_defect_attachment_id)).scalars().all()
        values.append(dict(defect_type_id=row.defect_type_id, defect_qty=row.defect_qty,
                           disposition=row.disposition, memo=row.memo,
                           attachments=[dict(file_uri=a.file_uri, file_name=a.file_name,
                                             mime_type=a.mime_type, memo=a.memo) for a in attachments]))
    return values



def result_snapshot(db: Session, result: InspectionResult) -> dict:
    values = {key: getattr(result, key) for key in (
        "good_qty", "defect_ship_qty", "defect_qty", "uninspected_qty", "discard_qty",
        "is_partial", "partial_reason", "shortage_reason", "memo",
        "settlement_owner_id", "settled_sellable_qty",
    )}
    values["next_inspection_date"] = result.next_inspection_date.isoformat() if result.next_inspection_date else None
    values["defects"] = defect_snapshot(db, result.inspection_result_id)
    values["shipments"] = [dict(id=line.shipment_line_id, source=line.source_type,
        lot_id=line.product_inventory_lot_id, qty=int(line.shipped_qty))
        for line in db.execute(select(ShipmentLine).where(
            ShipmentLine.inspection_result_id == result.inspection_result_id,
            ShipmentLine.status == "DONE",
        ).order_by(ShipmentLine.shipment_line_id)).scalars()]
    return values



def replace_defects_and_attachments(
    db: Session,
    *,
    inspection_result_id: int,
    defects: Sequence[DefectLineIn],
):
    if defect_snapshot(db, inspection_result_id) == [line.model_dump(mode="json") for line in defects]:
        return
    defect_ids = db.execute(
        select(InspectionDefect.inspection_defect_id).where(
            InspectionDefect.inspection_result_id == inspection_result_id
        )
    ).scalars().all()

    if defect_ids:
        db.execute(
            delete(InspectionDefectAttachment).where(
                InspectionDefectAttachment.inspection_defect_id.in_(defect_ids)
            )
        )
        db.execute(
            delete(InspectionDefect).where(
                InspectionDefect.inspection_defect_id.in_(defect_ids)
            )
        )
        db.flush()

    for line in defects:
        defect = InspectionDefect(
            inspection_result_id=inspection_result_id,
            defect_type_id=line.defect_type_id,
            defect_qty=line.defect_qty,
            disposition=line.disposition,
            memo=line.memo,
        )
        db.add(defect)
        db.flush()

        for att in line.attachments:
            db.add(
                InspectionDefectAttachment(
                    inspection_defect_id=defect.inspection_defect_id,
                    file_uri=att.file_uri,
                    file_name=att.file_name,
                    mime_type=att.mime_type,
                    memo=att.memo,
                )
            )

    db.flush()



def ensure_no_issued_documents(db: Session, result_id: int, order_line_id: int) -> None:
    certificate = db.execute(select(InspectionCertificate.inspection_certificate_id).where(
        InspectionCertificate.basis_inspection_result_id == result_id,
    ).limit(1)).scalar_one_or_none()
    coa = db.execute(select(ShipmentCoa.shipment_coa_id).where(
        ShipmentCoa.order_line_id == order_line_id,
    ).limit(1)).scalar_one_or_none()
    if certificate is not None or coa is not None:
        raise HTTPException(status_code=409, detail="성적서/COA가 발행된 실적은 발행자료 정정 절차를 먼저 확인해야 합니다.")
