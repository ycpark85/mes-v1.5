from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.product import Product
from app.schemas.order_line import (
    OrderLineBulkCommitGroupResult,
    OrderLineBulkCommitRequest,
    OrderLineBulkCommitResult,
    OrderLineBulkImportRowIn,
    OrderLineCreate,
    OrderLineBulkValidateGroupOut,
    OrderLineBulkValidateMessage,
    OrderLineBulkValidateRequest,
    OrderLineBulkValidateResult,
    OrderLineBulkValidateRowOut,
)
from app.services.order_line_creation_service import create_order_line_with_policy
from app.services.partner_product_mapping_service import resolve_erp_product


_ORDER_NO_PATTERN = re.compile(r"^\s*(\d{4}/\d{2}/\d{2})\s*-\s*\d+\s*$")
_PRODUCT_DISPLAY_PATTERN = re.compile(r"^(?P<name>.*?)(?:\s*\[(?P<spec>[^\]]+)\])?\s*$")


@dataclass
class _ResolvedRow:
    row_number: int
    erp_order_no: str
    raw_partner_name: str
    product_code: str
    erp_product_display_name: str
    order_qty_text: str
    due_date_text: str
    remark: Optional[str]

    line_no: Optional[int] = None
    order_date: Optional[date] = None
    due_date: Optional[date] = None

    partner_id: Optional[int] = None
    partner_name: Optional[str] = None

    product_id: Optional[int] = None
    mes_product_display_name: Optional[str] = None
    mes_product_code: Optional[str] = None
    drawing_no: Optional[str] = None
    mapping_id: Optional[int] = None
    is_unprinted_managed: bool = False

    parsed_product_name: Optional[str] = None
    parsed_product_spec: Optional[str] = None

    order_qty: Optional[int] = None

    product_name_mismatch: bool = False
    can_apply_product_name_change: bool = False

    messages: list[OrderLineBulkValidateMessage] = field(default_factory=list)

    @property
    def has_error(self) -> bool:
        return any(x.level == "ERROR" for x in self.messages)

    @property
    def has_warning(self) -> bool:
        return any(x.level == "WARNING" for x in self.messages)

    @property
    def status(self) -> str:
        if self.has_error:
            return "ERROR"
        if self.has_warning:
            return "REVIEW"
        return "READY"


class OrderLineBulkService:
    def commit_bulk(
        self,
        db: Session,
        payload: OrderLineBulkCommitRequest,
    ) -> OrderLineBulkCommitResult:
        validation = self.validate_bulk(
            db,
            OrderLineBulkValidateRequest(items=payload.items),
        )

        items_by_order_no: dict[str, list[OrderLineBulkImportRowIn]] = defaultdict(list)
        for item in payload.items:
            items_by_order_no[item.erp_order_no.strip()].append(item)

        choice_map = {
            item.row_number: item.apply_product_name_change
            for item in payload.row_choices
        }

        expected = {item.row_number: item for item in payload.row_choices}

        results: list[OrderLineBulkCommitGroupResult] = []
        success_group_count = 0
        failure_group_count = 0

        for group in validation.groups:
            if not group.can_commit:
                failure_group_count += 1
                results.append(
                    OrderLineBulkCommitGroupResult(
                        erp_order_no=group.erp_order_no,
                        status="ERROR",
                        message="검증 오류가 있어 등록할 수 없습니다.",
                        created_order_line_ids=[],
                    )
                )
                continue

            try:
                created_ids: list[int] = []

                with db.begin_nested():
                    self._validate_product_name_change_choices(group, choice_map)

                    group_memo = self._build_group_memo(items_by_order_no, group.erp_order_no)

                    for row in group.rows:
                        if row.status == "ERROR":
                            raise HTTPException(
                                status_code=409,
                                detail=f"row_number={row.row_number} 검증 오류로 등록할 수 없습니다.",
                            )

                        product, mapping = resolve_erp_product(db, row.partner_id, row.product_code, lock=True)
                        if product.product_id != row.product_id or (mapping.mapping_id if mapping else None) != row.mapping_id:
                            raise HTTPException(status_code=409, detail="품목 연결이 변경되었습니다. 다시 검증하세요.")
                        choice = expected.get(row.row_number)
                        if mapping and (choice is None or choice.expected_product_id != product.product_id
                                        or choice.expected_mapping_id != mapping.mapping_id):
                            raise HTTPException(status_code=409, detail="무지 품목 연결을 다시 검증한 후 등록하세요.")
                        if choice and choice.expected_product_id is not None and choice.expected_product_id != product.product_id:
                            raise HTTPException(status_code=409, detail="검증 후 품목 연결이 변경되었습니다. 다시 검증하세요.")

                        if choice_map.get(row.row_number, False) and row.product_name_mismatch:
                            product = db.get(Product, row.product_id)
                            if product is None or not product.is_active:
                                raise HTTPException(
                                    status_code=404,
                                    detail=f"row_number={row.row_number} 품목을 찾을 수 없습니다.",
                                )

                            if row.parsed_product_name:
                                product.product_name = row.parsed_product_name
                            product.product_spec = row.parsed_product_spec

                            db.add(product)
                            db.flush()

                        create_payload = OrderLineCreate(
                            order_no=row.erp_order_no,
                            line_no=row.line_no,
                            partner_id=row.partner_id,
                            product_id=row.product_id,
                            order_date=row.order_date,
                            due_date=row.due_date,
                            order_qty=row.order_qty,
                            uom="",
                            customer_po=None,
                            memo=group_memo,
                        )

                        source = None
                        if mapping:
                            source = dict(source_erp_product_code=row.product_code,
                                          source_product_name=row.parsed_product_name,
                                          source_product_spec=row.parsed_product_spec)
                        created = create_order_line_with_policy(db, create_payload, erp_source=source)
                        created_ids.append(created.order_line_id)

                success_group_count += 1
                results.append(
                    OrderLineBulkCommitGroupResult(
                        erp_order_no=group.erp_order_no,
                        status="SUCCESS",
                        message=None,
                        created_order_line_ids=created_ids,
                    )
                )

            except HTTPException as exc:
                failure_group_count += 1
                results.append(
                    OrderLineBulkCommitGroupResult(
                        erp_order_no=group.erp_order_no,
                        status="ERROR",
                        message=str(exc.detail),
                        created_order_line_ids=[],
                    )
                )
            except IntegrityError:
                failure_group_count += 1
                results.append(
                    OrderLineBulkCommitGroupResult(
                        erp_order_no=group.erp_order_no,
                        status="ERROR",
                        message="Duplicate order_no+line_no or integrity error",
                        created_order_line_ids=[],
                    )
                )

        return OrderLineBulkCommitResult(
            total_group_count=len(validation.groups),
            success_group_count=success_group_count,
            failure_group_count=failure_group_count,
            groups=results,
        )

    def validate_bulk(
        self,
        db: Session,
        payload: OrderLineBulkValidateRequest,
    ) -> OrderLineBulkValidateResult:
        resolved_rows = [self._resolve_row(db, item) for item in payload.items]
        self._apply_group_rules(db, resolved_rows)

        grouped: dict[str, list[_ResolvedRow]] = defaultdict(list)
        for row in resolved_rows:
            grouped[row.erp_order_no].append(row)

        groups: list[OrderLineBulkValidateGroupOut] = []
        ready_row_count = 0
        review_row_count = 0
        error_row_count = 0
        duplicate_group_count = 0

        for erp_order_no, rows in grouped.items():
            rows = sorted(rows, key=lambda x: x.row_number)

            for row in rows:
                if row.status == "READY":
                    ready_row_count += 1
                elif row.status == "REVIEW":
                    review_row_count += 1
                else:
                    error_row_count += 1

            group_messages: list[OrderLineBulkValidateMessage] = []
            if any(
                msg.field == "erp_order_no" and "이미 등록된 주문번호" in msg.message
                for row in rows
                for msg in row.messages
            ):
                duplicate_group_count += 1

            if any(row.has_error for row in rows):
                group_status = "ERROR"
                can_commit = False
            elif any(row.has_warning for row in rows):
                group_status = "REVIEW"
                can_commit = True
            else:
                group_status = "READY"
                can_commit = True

            first = rows[0]
            groups.append(
                OrderLineBulkValidateGroupOut(
                    erp_order_no=erp_order_no,
                    order_date=first.order_date,
                    due_date=first.due_date,
                    partner_id=first.partner_id,
                    partner_name=first.partner_name,
                    status=group_status,
                    can_commit=can_commit,
                    messages=group_messages,
                    rows=[self._to_row_out(x) for x in rows],
                )
            )

        groups.sort(key=lambda x: (x.erp_order_no, x.partner_name or ""))

        return OrderLineBulkValidateResult(
            total_row_count=len(payload.items),
            ready_row_count=ready_row_count,
            review_row_count=review_row_count,
            error_row_count=error_row_count,
            duplicate_group_count=duplicate_group_count,
            groups=groups,
        )

    def _resolve_row(self, db: Session, item: OrderLineBulkImportRowIn) -> _ResolvedRow:
        row = _ResolvedRow(
            row_number=item.row_number,
            erp_order_no=(item.erp_order_no or "").strip(),
            raw_partner_name=(item.partner_name or "").strip(),
            product_code=(item.product_code or "").strip(),
            erp_product_display_name=(item.erp_product_display_name or "").strip(),
            order_qty_text=(item.order_qty_text or "").strip(),
            due_date_text=(item.due_date_text or "").strip(),
            remark=(item.remark or "").strip() or None,
        )

        if not row.erp_order_no:
            row.messages.append(self._err("erp_order_no", "ERP 주문번호가 없습니다."))
        else:
            row.order_date = self._parse_order_date(row.erp_order_no, row)

        if not row.raw_partner_name:
            row.messages.append(self._err("partner_name", "거래처명이 없습니다."))
        else:
            self._resolve_partner(db, row)

        if not row.product_code:
            row.messages.append(self._err("product_code", "품목코드가 없습니다."))
        else:
            self._resolve_product(db, row)

        row.order_qty = self._parse_qty(row.order_qty_text, row)
        row.due_date = self._parse_date(row.due_date_text, "due_date_text", "납기일자", row)

        return row

    def _build_group_memo(
        self,
        items_by_order_no: dict[str, list[OrderLineBulkImportRowIn]],
        erp_order_no: str,
    ) -> str | None:
        remarks: list[str] = []

        for item in items_by_order_no.get(erp_order_no, []):
            remark = (item.remark or "").strip()
            if remark and remark not in remarks:
                remarks.append(remark)

        if not remarks:
            return None

        if len(remarks) == 1:
            return remarks[0]

        return "\n".join(remarks)

    def _validate_product_name_change_choices(self, group, choice_map: dict[int, bool]) -> None:
        product_updates: dict[int, set[tuple[str | None, str | None]]] = defaultdict(set)

        for row in group.rows:
            if not choice_map.get(row.row_number, False):
                continue

            if row.is_unprinted_managed:
                raise HTTPException(status_code=409, detail="무지 품목은 거래처 품명으로 공통 품목명을 변경할 수 없습니다.")

            if not row.product_name_mismatch:
                continue

            if not row.can_apply_product_name_change:
                raise HTTPException(
                    status_code=409,
                    detail=f"row_number={row.row_number} 품목명 변경 반영이 불가능합니다.",
                )

            product_updates[row.product_id].add(
                (row.parsed_product_name, row.parsed_product_spec)
            )

        for product_id, values in product_updates.items():
            if len(values) > 1:
                raise HTTPException(
                    status_code=409,
                    detail=f"같은 품목(product_id={product_id})에 서로 다른 품목명 변경이 동시에 요청되었습니다.",
                )

    def _resolve_partner(self, db: Session, row: _ResolvedRow) -> None:
        normalized_name = row.raw_partner_name.strip().upper()

        items = db.execute(
            select(Partner)
            .where(
                Partner.is_active == True,
                func.upper(func.trim(Partner.name)) == normalized_name,
            )
            .order_by(Partner.partner_id.asc())
        ).scalars().all()

        if len(items) == 0:
            row.messages.append(self._err("partner_name", "MES 거래처 매핑 실패"))
            return

        if len(items) > 1:
            row.messages.append(self._err("partner_name", "동일 거래처명이 2건 이상입니다."))
            return

        partner = items[0]
        row.partner_id = int(partner.partner_id)
        row.partner_name = partner.name

    def _resolve_product(self, db: Session, row: _ResolvedRow) -> None:
        try:
            product, mapping = resolve_erp_product(db, row.partner_id, row.product_code)
        except HTTPException as exc:
            row.messages.append(self._err("product_code", str(exc.detail)))
            return

        row.is_unprinted_managed = product.is_unprinted_managed
        row.mapping_id = mapping.mapping_id if mapping else None
        row.mes_product_code = product.product_code
        row.drawing_no = product.drawing.drawing_no if product.drawing else None
        row.product_id = int(product.product_id)
        row.mes_product_display_name = self._build_mes_product_display_name(product)

        parsed_name, parsed_spec = self._split_erp_product_display_name(row.erp_product_display_name)
        row.parsed_product_name = parsed_name
        row.parsed_product_spec = parsed_spec

        if row.is_unprinted_managed:
            if not parsed_name or len(parsed_name) > 200 or (parsed_spec and len(parsed_spec) > 100):
                row.messages.append(self._err("erp_product_display_name", "무지 수주 품명은 1~200자, 규격은 100자 이내여야 합니다."))
            return

        if self._normalize_text(row.erp_product_display_name) != self._normalize_text(row.mes_product_display_name):
            row.product_name_mismatch = True
            row.can_apply_product_name_change = parsed_name is not None
            row.messages.append(
                self._warn(
                    "erp_product_display_name",
                    "품목코드는 같지만 ERP 품목명[규격]과 MES 품목명이 다릅니다.",
                )
            )

    def _apply_group_rules(self, db: Session, rows: list[_ResolvedRow]) -> None:
        grouped: dict[str, list[_ResolvedRow]] = defaultdict(list)
        for row in rows:
            grouped[row.erp_order_no].append(row)

        existing_order_nos = set()
        target_order_nos = [key for key in grouped.keys() if key]
        if target_order_nos:
            existing_order_nos = set(
                db.execute(
                    select(OrderLine.order_no)
                    .where(OrderLine.order_no.in_(target_order_nos))
                    .distinct()
                ).scalars().all()
            )

        for erp_order_no, group_rows in grouped.items():
            group_rows.sort(key=lambda x: x.row_number)

            for index, row in enumerate(group_rows, start=1):
                row.line_no = index

            if erp_order_no in existing_order_nos:
                for row in group_rows:
                    row.messages.append(self._err("erp_order_no", "이미 등록된 주문번호입니다."))

            partner_names = {self._normalize_text(x.raw_partner_name) for x in group_rows if x.raw_partner_name}
            if len(partner_names) > 1:
                for row in group_rows:
                    row.messages.append(self._err("partner_name", "같은 주문번호에 거래처명이 서로 다릅니다."))

            due_dates = {x.due_date for x in group_rows if x.due_date is not None}
            if len(due_dates) > 1:
                for row in group_rows:
                    row.messages.append(self._err("due_date_text", "같은 주문번호에 납기일자가 서로 다릅니다."))

            remarks = {self._normalize_text(x.remark) for x in group_rows if x.remark}
            if len(remarks) > 1:
                for row in group_rows:
                    row.messages.append(self._warn("remark", "같은 주문번호에 특이사항이 서로 다릅니다."))

    def _parse_order_date(self, erp_order_no: str, row: _ResolvedRow) -> Optional[date]:
        match = _ORDER_NO_PATTERN.match(erp_order_no)
        if not match:
            row.messages.append(self._err("erp_order_no", "ERP 주문번호에서 주문일자를 추출할 수 없습니다."))
            return None

        try:
            return datetime.strptime(match.group(1), "%Y/%m/%d").date()
        except ValueError:
            row.messages.append(self._err("erp_order_no", "ERP 주문번호의 주문일자 형식이 잘못되었습니다."))
            return None

    def _parse_date(
        self,
        value: str,
        field_name: str,
        field_label: str,
        row: _ResolvedRow,
    ) -> Optional[date]:
        text = (value or "").strip()
        if not text:
            row.messages.append(self._err(field_name, f"{field_label}가 없습니다."))
            return None

        for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue

        row.messages.append(self._err(field_name, f"{field_label} 형식이 잘못되었습니다."))
        return None

    def _parse_qty(self, value: str, row: _ResolvedRow) -> Optional[int]:
        text = (value or "").strip().replace(",", "")
        if not text:
            row.messages.append(self._err("order_qty_text", "잔량이 없습니다."))
            return None

        try:
            qty = int(text)
        except ValueError:
            row.messages.append(self._err("order_qty_text", "잔량 숫자 변환에 실패했습니다."))
            return None

        if qty <= 0:
            row.messages.append(self._err("order_qty_text", "잔량은 0보다 커야 합니다."))
            return None

        return qty

    def _build_mes_product_display_name(self, product: Product) -> str:
        product_name = (product.product_name or "").strip()
        product_spec = (product.product_spec or "").strip()

        if product_spec:
            return f"{product_name} [{product_spec}]"

        return product_name

    def _split_erp_product_display_name(self, value: str) -> tuple[Optional[str], Optional[str]]:
        text = (value or "").strip()
        if not text:
            return None, None

        match = _PRODUCT_DISPLAY_PATTERN.match(text)
        if not match:
            return text, None

        name = (match.group("name") or "").strip() or None
        spec = (match.group("spec") or "").strip() or None
        return name, spec

    def _normalize_text(self, value: Optional[str]) -> str:
        return (value or "").strip().upper()

    def _err(self, field: str, message: str) -> OrderLineBulkValidateMessage:
        return OrderLineBulkValidateMessage(field=field, level="ERROR", message=message)

    def _warn(self, field: str, message: str) -> OrderLineBulkValidateMessage:
        return OrderLineBulkValidateMessage(field=field, level="WARNING", message=message)

    def _to_row_out(self, row: _ResolvedRow) -> OrderLineBulkValidateRowOut:
        return OrderLineBulkValidateRowOut(
            row_number=row.row_number,
            erp_order_no=row.erp_order_no,
            line_no=row.line_no,
            order_date=row.order_date,
            due_date=row.due_date,
            partner_id=row.partner_id,
            partner_name=row.partner_name,
            product_id=row.product_id,
            product_code=row.product_code,
            erp_product_display_name=row.erp_product_display_name,
            mes_product_display_name=row.mes_product_display_name,
            mes_product_code=row.mes_product_code,
            drawing_no=row.drawing_no,
            mapping_id=row.mapping_id,
            is_unprinted_managed=row.is_unprinted_managed,
            parsed_product_name=row.parsed_product_name,
            parsed_product_spec=row.parsed_product_spec,
            order_qty=row.order_qty,
            status=row.status,
            product_name_mismatch=row.product_name_mismatch,
            can_apply_product_name_change=row.can_apply_product_name_change,
            apply_product_name_change=False,
            messages=row.messages,
        )


order_line_bulk_service = OrderLineBulkService()
