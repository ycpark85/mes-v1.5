from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.partner_product_mapping_service import ensure_legacy_code_available
from app.models.drawing import Drawing
from app.models.product import Product
from app.models.routing_template import RoutingTemplate
from app.schemas.product import (
    ProductBulkCreateRequest,
    ProductBulkCreateResult,
    ProductBulkError,
)


@dataclass
class _NormalizedProductRow:
    row_number: int
    product_code: str
    product_name: str
    uom: str
    drawing_no: str
    template_code: str
    panel_width_mm: int | None
    panel_length_mm: int | None
    product_spec: str | None
    cut_qty_per_panel: int | None
    is_active: bool
    memo: str | None


@dataclass
class _ResolvedProductRow:
    row_number: int
    product_code: str
    product_name: str
    uom: str
    drawing_id: int
    routing_template_id: int
    panel_width_mm: int | None
    panel_length_mm: int | None
    product_spec: str | None
    cut_qty_per_panel: int | None
    is_active: bool
    memo: str | None


class ProductBulkService:
    def create_bulk(
        self,
        db: Session,
        payload: ProductBulkCreateRequest,
    ) -> ProductBulkCreateResult:
        normalized_rows, errors = self._normalize_and_validate(payload.items)

        if normalized_rows:
            errors.extend(self._validate_duplicate_product_code_in_payload(normalized_rows))
            errors.extend(self._validate_duplicate_drawing_no_in_payload(normalized_rows))

        valid_rows = self._exclude_error_rows(normalized_rows, errors)

        resolved_rows: list[_ResolvedProductRow] = []
        if valid_rows:
            resolved_rows, resolve_errors = self._resolve_foreign_keys(db, valid_rows)
            errors.extend(resolve_errors)

        valid_resolved_rows = self._exclude_error_rows(resolved_rows, errors)

        for row in sorted(valid_resolved_rows, key=lambda x: x.product_code):
            try:
                ensure_legacy_code_available(db, row.product_code)
            except HTTPException as exc:
                errors.append(ProductBulkError(row_number=row.row_number, field="product_code", message=str(exc.detail)))

        if valid_resolved_rows:
            errors.extend(self._validate_duplicate_product_code_in_db(db, valid_resolved_rows))
            errors.extend(self._validate_duplicate_drawing_id_in_db(db, valid_resolved_rows))

        valid_resolved_rows = self._exclude_error_rows(valid_resolved_rows, errors)

        created_items: list[Product] = []
        if valid_resolved_rows:
            created_items = self._insert_rows(db, valid_resolved_rows)

        total_count = len(payload.items)
        success_count = len(created_items)
        failure_count = total_count - success_count

        return ProductBulkCreateResult(
            total_count=total_count,
            success_count=success_count,
            failure_count=failure_count,
            created_items=created_items,
            errors=sorted(errors, key=lambda x: x.row_number),
        )

    def _normalize_and_validate(self, items) -> tuple[list[_NormalizedProductRow], list[ProductBulkError]]:
        rows: list[_NormalizedProductRow] = []
        errors: list[ProductBulkError] = []

        for item in items:
            product_code = item.product_code.strip().upper()
            product_name = item.product_name.strip()
            uom = item.uom.strip().upper()
            drawing_no = item.drawing_no.strip().upper()
            template_code = item.template_code.strip().upper()
            product_spec = item.product_spec.strip() if item.product_spec else None
            memo = item.memo.strip() if item.memo else None

            if not product_code:
                errors.append(ProductBulkError(row_number=item.row_number, field="product_code", message="product_code is required"))
            if not product_name:
                errors.append(ProductBulkError(row_number=item.row_number, field="product_name", message="product_name is required"))
            if not uom:
                errors.append(ProductBulkError(row_number=item.row_number, field="uom", message="uom is required"))
            if not drawing_no:
                errors.append(ProductBulkError(row_number=item.row_number, field="drawing_no", message="drawing_no is required"))
            if not template_code:
                errors.append(ProductBulkError(row_number=item.row_number, field="template_code", message="template_code is required"))

            rows.append(
                _NormalizedProductRow(
                    row_number=item.row_number,
                    product_code=product_code,
                    product_name=product_name,
                    uom=uom,
                    drawing_no=drawing_no,
                    template_code=template_code,
                    panel_width_mm=item.panel_width_mm,
                    panel_length_mm=item.panel_length_mm,
                    product_spec=product_spec,
                    cut_qty_per_panel=item.cut_qty_per_panel,
                    is_active=item.is_active,
                    memo=memo,
                )
            )

        return rows, errors

    def _validate_duplicate_product_code_in_payload(
        self,
        rows: Iterable[_NormalizedProductRow],
    ) -> list[ProductBulkError]:
        errors: list[ProductBulkError] = []
        seen: dict[str, int] = {}

        for row in rows:
            first_row = seen.get(row.product_code)
            if first_row is None:
                seen[row.product_code] = row.row_number
                continue

            errors.append(
                ProductBulkError(
                    row_number=row.row_number,
                    field="product_code",
                    message=f"duplicated in payload (first row: {first_row})",
                )
            )

        return errors

    def _validate_duplicate_drawing_no_in_payload(
        self,
        rows: Iterable[_NormalizedProductRow],
    ) -> list[ProductBulkError]:
        errors: list[ProductBulkError] = []
        seen: dict[str, int] = {}

        for row in rows:
            first_row = seen.get(row.drawing_no)
            if first_row is None:
                seen[row.drawing_no] = row.row_number
                continue

            errors.append(
                ProductBulkError(
                    row_number=row.row_number,
                    field="drawing_no",
                    message=f"duplicated in payload (first row: {first_row})",
                )
            )

        return errors

    def _resolve_foreign_keys(
        self,
        db: Session,
        rows: Iterable[_NormalizedProductRow],
    ) -> tuple[list[_ResolvedProductRow], list[ProductBulkError]]:
        resolved_rows: list[_ResolvedProductRow] = []
        errors: list[ProductBulkError] = []

        drawing_nos = list({row.drawing_no for row in rows})
        template_codes = list({row.template_code for row in rows})

        drawing_map = {
            drawing_no: drawing_id
            for drawing_no, drawing_id in db.query(Drawing.drawing_no, Drawing.drawing_id)
            .filter(Drawing.drawing_no.in_(drawing_nos), Drawing.is_active == True)
            .all()
        }

        template_map = {
            template_code: routing_template_id
            for template_code, routing_template_id in db.query(
                RoutingTemplate.template_code,
                RoutingTemplate.routing_template_id,
            )
            .filter(
                RoutingTemplate.template_code.in_(template_codes),
                RoutingTemplate.is_active == True,
            )
            .all()
        }

        for row in rows:
            drawing_id = drawing_map.get(row.drawing_no)
            if drawing_id is None:
                errors.append(
                    ProductBulkError(
                        row_number=row.row_number,
                        field="drawing_no",
                        message="drawing_no not found",
                    )
                )
                continue

            routing_template_id = template_map.get(row.template_code)
            if routing_template_id is None:
                errors.append(
                    ProductBulkError(
                        row_number=row.row_number,
                        field="template_code",
                        message="template_code not found",
                    )
                )
                continue

            resolved_rows.append(
                _ResolvedProductRow(
                    row_number=row.row_number,
                    product_code=row.product_code,
                    product_name=row.product_name,
                    uom=row.uom,
                    drawing_id=drawing_id,
                    routing_template_id=routing_template_id,
                    panel_width_mm=row.panel_width_mm,
                    panel_length_mm=row.panel_length_mm,
                    product_spec=row.product_spec,
                    cut_qty_per_panel=row.cut_qty_per_panel,
                    is_active=row.is_active,
                    memo=row.memo,
                )
            )

        return resolved_rows, errors

    def _validate_duplicate_product_code_in_db(
        self,
        db: Session,
        rows: Iterable[_ResolvedProductRow],
    ) -> list[ProductBulkError]:
        errors: list[ProductBulkError] = []
        product_codes = list({row.product_code for row in rows})
        if not product_codes:
            return errors

        existing_product_codes = {
            value
            for (value,) in db.query(Product.product_code)
            .filter(Product.product_code.in_(product_codes))
            .all()
        }

        for row in rows:
            if row.product_code in existing_product_codes:
                errors.append(
                    ProductBulkError(
                        row_number=row.row_number,
                        field="product_code",
                        message="product_code already exists",
                    )
                )

        return errors

    def _validate_duplicate_drawing_id_in_db(
        self,
        db: Session,
        rows: Iterable[_ResolvedProductRow],
    ) -> list[ProductBulkError]:
        errors: list[ProductBulkError] = []
        drawing_ids = list({row.drawing_id for row in rows})
        if not drawing_ids:
            return errors

        existing_drawing_ids = {
            value
            for (value,) in db.query(Product.drawing_id)
            .filter(Product.drawing_id.in_(drawing_ids))
            .all()
        }

        for row in rows:
            if row.drawing_id in existing_drawing_ids:
                errors.append(
                    ProductBulkError(
                        row_number=row.row_number,
                        field="drawing_no",
                        message="drawing_no already assigned to another product",
                    )
                )

        return errors

    def _exclude_error_rows(self, rows, errors):
        error_row_numbers = {error.row_number for error in errors}
        return [row for row in rows if row.row_number not in error_row_numbers]

    def _insert_rows(
        self,
        db: Session,
        rows: Iterable[_ResolvedProductRow],
    ) -> list[Product]:
        objects = [
            Product(
                product_code=row.product_code,
                product_name=row.product_name,
                uom=row.uom,
                drawing_id=row.drawing_id,
                routing_template_id=row.routing_template_id,
                panel_width_mm=row.panel_width_mm,
                panel_length_mm=row.panel_length_mm,
                product_spec=row.product_spec,
                cut_qty_per_panel=row.cut_qty_per_panel,
                is_active=row.is_active,
                memo=row.memo,
            )
            for row in rows
        ]

        try:
            db.add_all(objects)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise

        for obj in objects:
            db.refresh(obj)

        return objects


product_bulk_service = ProductBulkService()