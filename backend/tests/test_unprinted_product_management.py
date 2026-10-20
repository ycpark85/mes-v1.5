import unittest
from datetime import date
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import test_order_line_services as fixtures
from app.api.v1.products import create_product, update_product
from app.db.base import Base
from app.models.drawing import Drawing
from app.models.lot import Lot
from app.models.order_line import OrderLine
from app.models.partner import Partner
from app.models.partner_product_mapping import PartnerProductMapping, UnprintedProductCodeCounter
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate, ProductBulkCreateRequest, ProductBulkItem
from app.schemas.partner_product_mapping import PartnerProductMappingCreate
from app.schemas.order_line import (OrderLineCreate, OrderLineUpdate, OrderLineBulkImportRowIn,
    OrderLineBulkValidateRequest, OrderLineBulkCommitRequest, OrderLineBulkCommitRowChoice)
from app.services.bulk.order_line_bulk_service import order_line_bulk_service
from app.services.bulk.product_bulk_service import product_bulk_service
from app.services.order_line_creation_service import create_order_line_with_policy
from app.services.order_line_list_query import list_order_lines_for_grid
from app.services.order_line_update_service import update_order_line_fields
from app.services.partner_product_mapping_service import (create_mapping, deactivate_mapping,
    resolve_erp_product, generate_unprinted_code, list_mappings)
from app.services.product_query import list_products_for_grid


class UnprintedProductManagementTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.OrderLineServicesTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db
        Base.metadata.create_all(self.fixture.engine, tables=[UnprintedProductCodeCounter.__table__])
        self.db.add(UnprintedProductCodeCounter(counter_id=1, next_value=1))
        for i in range(2, 7):
            self.db.add(Drawing(drawing_id=i, drawing_no=f"D-{i:03d}", is_active=True))
        for i, name in enumerate(["업체A", "업체B", "업체C", "업체D"], 2):
            self.db.add(Partner(partner_id=i, partner_type="CUSTOMER", name=name, business_no=f"C-{i}", is_active=True))
        self.db.commit()
        self.first = self.new_product(2)
        self.second = self.new_product(3)

    def new_product(self, drawing_id):
        return create_product(ProductCreate(is_unprinted_managed=True, product_name="공통 무지", uom="EA",
            drawing_id=drawing_id, routing_template_id=1, product_spec="100×200"), db=self.db)

    def mapping(self, partner=2, product=None, code="MUJI-100", name="업체별 무지"):
        obj = create_mapping(self.db, product or self.first.product_id,
            PartnerProductMappingCreate(partner_id=partner, erp_product_code=code,
                customer_product_name=name, customer_product_spec="100×200"), actor="tester")
        self.db.commit()
        return obj

    def row(self, number=1, partner="업체A", code="MUJI-100", name="납품용 무지 [100×200]", order=None):
        return OrderLineBulkImportRowIn(row_number=number, erp_order_no=order or f"2026/10/19-{number}",
            partner_name=partner, product_code=code, erp_product_display_name=name, order_qty_text="10", due_date_text="2026-10-31")

    def commit(self, rows, choices=None):
        if choices is None:
            preview = order_line_bulk_service.validate_bulk(self.db, OrderLineBulkValidateRequest(items=rows))
            choices = [OrderLineBulkCommitRowChoice(row_number=row.row_number, expected_product_id=row.product_id,
                expected_mapping_id=row.mapping_id) for group in preview.groups for row in group.rows]
        with patch("app.services.order_line_creation_service.refresh_order_line_snapshot"):
            result = order_line_bulk_service.commit_bulk(self.db, OrderLineBulkCommitRequest(items=rows, row_choices=choices))
        self.db.commit()
        return result

    def test_auto_code_and_legacy_printed_registration_unchanged(self):
        self.assertEqual("MES-U000001", self.first.product_code)
        self.assertEqual("MES-U000002", self.second.product_code)
        printed = create_product(ProductCreate(product_code="PRINT-NEW", product_name="인쇄", uom="EA",
            drawing_id=4, routing_template_id=1), db=self.db)
        self.assertFalse(printed.is_unprinted_managed)
        self.assertEqual("PRINT-NEW", printed.product_code)
        original = self.db.get(Product, 1)
        self.assertEqual(("P-001", "제품", 1, False), (original.product_code, original.product_name, original.drawing_id, original.is_unprinted_managed))
        with self.assertRaises(ValidationError):
            ProductCreate(product_code="MANUAL", is_unprinted_managed=True, product_name="무지", uom="EA", drawing_id=4, routing_template_id=1)

    def test_one_drawing_per_product_and_no_managed_drawing_replacement(self):
        with self.assertRaises(HTTPException) as error:
            self.new_product(2)
        self.assertEqual(409, error.exception.status_code)
        with self.assertRaises(HTTPException):
            update_product(product_id=self.first.product_id, payload=ProductUpdate(drawing_id=4), db=self.db)
        self.db.rollback()
        with self.assertRaises(HTTPException):
            update_product(product_id=self.first.product_id, payload=ProductUpdate(is_unprinted_managed=False), db=self.db)

    def test_same_code_two_shared_one_distinct_and_original_names_kept(self):
        self.mapping(2, name="A용 상자")
        self.mapping(3, name="B용 포장")
        self.mapping(4, self.second.product_id, name="A용 상자")
        result = self.commit([self.row(1, "업체A", name="A용 상자 [100×200]"),
            self.row(2, "업체B", name="B용 포장 [100×200]"), self.row(3, "업체C", name="A용 상자 [100×200]")])
        self.assertEqual(3, result.success_group_count)
        orders = self.db.scalars(select(OrderLine).order_by(OrderLine.order_line_id)).all()
        self.assertEqual([self.first.product_id, self.first.product_id, self.second.product_id], [x.product_id for x in orders])
        self.assertEqual(["A용 상자", "B용 포장", "A용 상자"], [x.source_product_name for x in orders])
        self.assertEqual(["MUJI-100"] * 3, [x.source_erp_product_code for x in orders])
        self.assertEqual("공통 무지", self.db.get(Product, self.first.product_id).product_name)
        self.assertEqual([x.product_id for x in orders], list(self.db.scalars(select(Lot.product_id).order_by(Lot.lot_id))))
        items, total, _ = list_order_lines_for_grid(self.db, page=1, size=20, q="B용 포장")
        self.assertEqual(1, total)
        self.assertEqual("B용 포장", items[0]["product_name"])

    def test_managed_master_rename_is_explicit_and_preserves_customer_snapshot(self):
        self.mapping()
        preview = order_line_bulk_service.validate_bulk(self.db, OrderLineBulkValidateRequest(items=[self.row()]))
        row = preview.groups[0].rows[0]
        self.assertEqual("REVIEW", row.status)
        self.assertTrue(row.can_apply_product_name_change)
        self.assertFalse(row.apply_product_name_change)
        self.assertTrue(any("공통 기준 품목명" in item.message for item in row.messages))
        self.assertEqual(self.first.product_code, row.mes_product_code)
        self.assertEqual("D-002", row.drawing_no)
        result = self.commit([self.row()], [OrderLineBulkCommitRowChoice(row_number=1, apply_product_name_change=True,
            expected_product_id=row.product_id, expected_mapping_id=row.mapping_id)])
        self.assertEqual(1, result.success_group_count)
        self.assertEqual("납품용 무지", self.db.get(Product, self.first.product_id).product_name)
        self.assertEqual("납품용 무지", self.db.scalar(select(OrderLine)).source_product_name)

    def test_printed_name_change_workflow_still_works(self):
        result = self.commit([self.row(code="P-001", partner="Customer", name="새 인쇄명 [PRINT-SPEC]")],
            [OrderLineBulkCommitRowChoice(row_number=1, apply_product_name_change=True)])
        self.assertEqual(1, result.success_group_count)
        self.assertEqual("새 인쇄명", self.db.get(Product, 1).product_name)
        order = self.db.scalar(select(OrderLine))
        self.assertEqual("새 인쇄명", order.source_product_name)
        self.assertEqual("PRINT-SPEC", order.source_product_spec)
        self.assertIsNone(self.db.get(Product, 1).product_spec)

    def test_master_rename_keeps_other_partner_order_and_mapping_names(self):
        self.mapping(2, name="A 연결명")
        second = self.mapping(3, name="B 연결명")
        self.assertEqual(1, self.commit([self.row(1, "업체B", name="B 발주명 [B 규격]")]).success_group_count)
        old_order = self.db.scalar(select(OrderLine))
        incoming = self.row(2, "업체A", name="A 새 이름 [A 규격]")
        preview = order_line_bulk_service.validate_bulk(self.db, OrderLineBulkValidateRequest(items=[incoming]))
        reviewed = preview.groups[0].rows[0]
        result = self.commit([incoming], [OrderLineBulkCommitRowChoice(
            row_number=2, expected_product_id=reviewed.product_id,
            expected_mapping_id=reviewed.mapping_id, apply_product_name_change=True)])
        self.assertEqual(1, result.success_group_count)
        self.db.refresh(old_order)
        self.db.refresh(second)
        self.assertEqual("B 발주명", old_order.source_product_name)
        self.assertEqual("B 연결명", second.customer_product_name)
        product = self.db.get(Product, self.first.product_id)
        self.assertEqual(("A 새 이름", "100×200"), (product.product_name, product.product_spec))

    def test_duplicate_partner_code_blocked_in_service_and_database(self):
        self.mapping(code=" muji-100 ")
        with self.assertRaises(HTTPException) as error:
            self.mapping(product=self.second.product_id)
        self.assertEqual(409, error.exception.status_code)
        self.db.rollback()
        self.db.add(PartnerProductMapping(partner_id=2, product_id=self.second.product_id, erp_product_code="MUJI-100",
            customer_product_name="다른 품목", created_by="tester"))
        with self.assertRaises(IntegrityError):
            self.db.flush()
        self.db.rollback()

    def test_unknown_partner_and_deactivated_mapping_never_fall_back(self):
        mapping = self.mapping()
        for partner in ["업체D", "존재하지 않는 업체"]:
            result = self.commit([self.row(partner=partner)])
            self.assertEqual(1, result.failure_group_count)
        deactivate_mapping(self.db, self.first.product_id, mapping.mapping_id, actor="tester")
        self.db.commit()
        self.assertEqual(1, self.commit([self.row()]).failure_group_count)
        self.assertEqual(0, len(list(self.db.scalars(select(OrderLine)))))

    def test_inactive_product_or_partner_rejected(self):
        self.mapping()
        product = self.db.get(Product, self.first.product_id)
        product.is_active = False
        self.db.commit()
        self.assertEqual(1, self.commit([self.row()]).failure_group_count)
        product.is_active = True
        self.db.get(Partner, 2).is_active = False
        self.db.commit()
        self.assertEqual(1, self.commit([self.row()]).failure_group_count)

    def test_relink_requires_new_preview_and_preserves_old_orders(self):
        original = self.mapping()
        self.assertEqual(1, self.commit([self.row()]).success_group_count)
        old_order = self.db.scalar(select(OrderLine))
        stale = OrderLineBulkCommitRowChoice(row_number=2, expected_product_id=self.first.product_id, expected_mapping_id=original.mapping_id)
        deactivate_mapping(self.db, self.first.product_id, original.mapping_id, actor="tester")
        self.db.commit()
        self.mapping(product=self.second.product_id)
        self.assertEqual(1, self.commit([self.row(2)], [stale]).failure_group_count)
        self.assertEqual(1, self.commit([self.row(2)]).success_group_count)
        self.db.refresh(old_order)
        self.assertEqual(self.first.product_id, old_order.product_id)
        self.assertEqual("납품용 무지", old_order.source_product_name)
        history = list_mappings(self.db, self.first.product_id, page=1, size=20, is_active=None)
        self.assertFalse(history["items"][0].is_active)

    def test_explicit_legacy_conversion_keeps_identifiers_and_old_order(self):
        with patch("app.services.order_line_creation_service.refresh_order_line_snapshot"):
            old = create_order_line_with_policy(self.db, OrderLineCreate(order_no="OLD", line_no=1, partner_id=1,
                product_id=1, order_date=date(2026, 1, 1), due_date=date(2026, 1, 31), order_qty=10, uom="EA"))
        self.db.commit()
        with self.assertRaises(HTTPException):
            self.mapping(code="P-001")
        self.db.rollback()
        updated = update_product(product_id=1, payload=ProductUpdate(is_unprinted_managed=True), db=self.db)
        self.assertEqual((1, "P-001", 1), (updated.product_id, updated.product_code, updated.drawing_id))
        self.mapping(product=1, code="P-001")
        self.db.refresh(old)
        self.assertEqual(1, old.product_id)
        self.assertEqual("제품", old.source_product_name)

    def test_legacy_registration_cannot_shadow_managed_erp_code(self):
        self.mapping()
        with self.assertRaises(HTTPException):
            create_product(ProductCreate(product_code="MUJI-100", product_name="인쇄", uom="EA",
                drawing_id=4, routing_template_id=1), db=self.db)

    def test_legacy_bulk_preserves_printed_path_and_rejects_alias_collision(self):
        self.mapping()
        result = product_bulk_service.create_bulk(self.db, ProductBulkCreateRequest(items=[
            ProductBulkItem(row_number=1, product_code="MUJI-100", product_name="중복", uom="EA", drawing_no="D-004", template_code="RT-001"),
            ProductBulkItem(row_number=2, product_code="PRINT-BULK", product_name="인쇄 벌크", uom="EA", drawing_no="D-005", template_code="RT-001")]))
        self.assertEqual((1, 1), (result.success_count, result.failure_count))
        self.assertEqual("PRINT-BULK", result.created_items[0].product_code)
        self.assertFalse(result.created_items[0].is_unprinted_managed)

    def test_database_rejects_incomplete_order_source(self):
        self.db.add(OrderLine(order_no="INVALID", line_no=1, partner_id=2, product_id=self.first.product_id,
            order_date=date(2026, 10, 19), due_date=date(2026, 10, 31), order_qty=10, uom="EA",
            source_product_name="코드 없는 품명"))
        with self.assertRaises(IntegrityError):
            self.db.flush()
        self.db.rollback()

    def test_manual_registration_requires_mapping_and_snapshots_customer_name(self):
        payload = OrderLineCreate(order_no="MANUAL", line_no=1, partner_id=2, product_id=self.first.product_id,
            order_date=date(2026, 10, 19), due_date=date(2026, 10, 31), order_qty=10, uom="EA")
        with self.assertRaises(HTTPException):
            create_order_line_with_policy(self.db, payload)
        self.mapping(name="수기등록 품명")
        self.fixture._seed_inventory(product_id=self.first.product_id, qty=100)
        order = create_order_line_with_policy(self.db, payload)
        self.assertEqual("수기등록 품명", order.source_product_name)
        with self.assertRaises(HTTPException):
            update_order_line_fields(self.db, order.order_line_id, OrderLineUpdate(partner_id=3), actor="tester")

    def test_product_lookup_finds_erp_alias_and_partner_before_any_order(self):
        self.mapping(name="거래처 전용명")
        for term in ["MUJI-100", "거래처 전용명"]:
            items, total = list_products_for_grid(self.db, page=1, size=20, q=term, partner_q=None, is_active=True)
            self.assertEqual(1, total)
            self.assertEqual(self.first.product_id, items[0].product_id)
        _, total = list_products_for_grid(self.db, page=1, size=20, q=None, partner_q="업체A", is_active=True)
        self.assertEqual(1, total)

    def test_counter_rollback_and_collision_skip(self):
        before = self.db.get(UnprintedProductCodeCounter, 1).next_value
        generate_unprinted_code(self.db)
        self.db.rollback()
        self.assertEqual(before, self.db.get(UnprintedProductCodeCounter, 1).next_value)
        self.db.add(Product(product_code=f"MES-U{before:06d}", product_name="기존 코드", drawing_id=4, routing_template_id=1, uom="EA"))
        self.db.commit()
        self.assertEqual(f"MES-U{before + 1:06d}", generate_unprinted_code(self.db))
