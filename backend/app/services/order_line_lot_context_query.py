from __future__ import annotations

from app.services.order_line_display import order_product_code

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud.order_line import order_line_crud
from app.models.drawing import Drawing
from app.models.drawing_revision import DrawingRevision
from app.models.drawing_rivision_file import DrawingRevisionFile
from app.models.lot import Lot
from app.models.partner import Partner
from app.models.product import Product
from app.schemas.lot_create_context import (
    LotCreateContextDto,
    LotCreateDrawingDto,
    LotCreatePrimaryCandidateDto,
)


def get_lot_create_context_dto(db: Session, order_line_id: int) -> LotCreateContextDto:
    order_line = order_line_crud.get(db, order_line_id)
    if not order_line or not order_line.is_active:
        raise HTTPException(status_code=404, detail="OrderLine not found")

    partner = db.get(Partner, order_line.partner_id)
    product = db.get(Product, order_line.product_id)

    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found or inactive")

    drawing = db.get(Drawing, product.drawing_id) if product.drawing_id else None
    current_revision = db.get(DrawingRevision, drawing.current_revision_id) if drawing and drawing.current_revision_id else None
    drawing_file, original_file, plate_file = _load_revision_files(db, current_revision)
    primary_lot_candidates = _load_primary_lot_candidates(db, order_line_id)

    return LotCreateContextDto(
        order_line_id=order_line.order_line_id,
        order_no=order_line.order_no,
        partner_id=order_line.partner_id,
        partner_name=partner.name,
        product_id=product.product_id,
        product_code=order_product_code(order_line, product),
        mes_product_code=product.product_code if product else None,
        product_name=product.product_name,
        order_qty=order_line.order_qty,
        uom=order_line.uom,
        due_date=order_line.due_date,
        status=order_line.status,
        panel_width_mm=product.panel_width_mm,
        panel_length_mm=product.panel_length_mm,
        cut_qty_per_panel=product.cut_qty_per_panel,
        product_spec=product.product_spec,
        drawing=LotCreateDrawingDto(
            drawing_id=drawing.drawing_id if drawing else None,
            drawing_no=drawing.drawing_no if drawing else None,
            current_revision_id=current_revision.revision_id if current_revision else None,
            current_revision_no=current_revision.rev_no if current_revision else None,
            drawing_file_id=drawing_file.revision_file_id if drawing_file else None,
            drawing_file_name=drawing_file.original_filename if drawing_file else None,
            original_file_id=original_file.revision_file_id if original_file else None,
            original_file_name=original_file.original_filename if original_file else None,
            plate_file_id=plate_file.revision_file_id if plate_file else None,
            plate_file_name=plate_file.original_filename if plate_file else None,
        ),
        primary_lot_candidates=primary_lot_candidates,
        can_create_primary_lot=False,
    )


def _load_revision_files(
    db: Session,
    current_revision: DrawingRevision | None,
) -> tuple[DrawingRevisionFile | None, DrawingRevisionFile | None, DrawingRevisionFile | None]:
    drawing_file = None
    original_file = None
    plate_file = None

    if current_revision is None:
        return drawing_file, original_file, plate_file

    revision_files = (
        db.execute(
            select(DrawingRevisionFile).where(
                DrawingRevisionFile.revision_id == current_revision.revision_id
            )
        )
        .scalars()
        .all()
    )

    for f in revision_files:
        kind = (f.file_kind or "").strip().upper()

        if kind == "DRAWING" and drawing_file is None:
            drawing_file = f
        elif kind == "ORIGINAL" and original_file is None:
            original_file = f
        elif kind == "PLATE" and plate_file is None:
            plate_file = f

    return drawing_file, original_file, plate_file


def _load_primary_lot_candidates(db: Session, order_line_id: int) -> list[LotCreatePrimaryCandidateDto]:
    primary_lots = (
        db.execute(
            select(Lot)
            .where(
                Lot.order_line_id == order_line_id,
                Lot.parent_lot_id.is_(None),
            )
            .order_by(Lot.created_date.asc(), Lot.lot_id.asc())
        )
        .scalars()
        .all()
    )

    return [
        LotCreatePrimaryCandidateDto(
            lot_id=lot.lot_id,
            lot_no=lot.lot_no,
            lot_qty=lot.lot_qty,
            uom=lot.uom,
            status=lot.status,
            memo=lot.memo,
            can_create_rework=lot.status in ("DONE", "CANCELED"),
        )
        for lot in primary_lots
    ]
