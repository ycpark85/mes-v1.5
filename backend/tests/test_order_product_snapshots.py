"""Order names are transaction facts; master renaming is an independent choice."""
from unittest.mock import patch

import pytest
from sqlalchemy import select

import test_order_line_services as fixtures
from app.api.v1.products import update_product
from app.models.order_line import OrderLine
from app.models.product import Product
from app.models.routing_template_step import RoutingTemplateStep
from app.schemas.order_line import (
    OrderLineBulkCommitRequest, OrderLineBulkCommitRowChoice, OrderLineBulkImportRowIn,
)
from app.schemas.product import ProductUpdate
from app.services.bulk.order_line_bulk_service import order_line_bulk_service
from app.services.order_line_creation_service import create_order_line_with_policy
from app.services.order_line_response_builder import build_order_line_out


@pytest.fixture
def fixture():
    value = fixtures.OrderLineServicesTests()
    value.setUp()
    try:
        yield value
    finally:
        value.tearDown()


def row(number=1, name="Customer box [100x200]", order=None):
    return OrderLineBulkImportRowIn(
        row_number=number, erp_order_no=order or f"2026/10/20-{number}",
        product_code="P-001", partner_name="Customer", erp_product_display_name=name,
        order_qty_text="10", due_date_text="2026-10-31",
    )


def commit(fixture, rows, checked=()):
    with patch("app.services.order_line_creation_service.refresh_order_line_snapshot"):
        return order_line_bulk_service.commit_bulk(fixture.db, OrderLineBulkCommitRequest(
            items=rows, row_choices=[OrderLineBulkCommitRowChoice(
                row_number=item.row_number, apply_product_name_change=item.row_number in checked,
            ) for item in rows],
        ))


def test_unchecked_keeps_master_and_saves_each_order_name(fixture):
    original = fixture.db.get(Product, 1)
    original_name = original.product_name
    result = commit(fixture, [row(1), row(2, "Another box")])
    assert result.success_group_count == 2
    orders = fixture.db.scalars(select(OrderLine).order_by(OrderLine.order_line_id)).all()
    assert [(o.source_product_name, o.source_product_spec) for o in orders] == [
        ("Customer box", "100x200"), ("Another box", None),
    ]
    assert original.product_name == original_name
    assert original.product_spec is None
    assert {o.product_id for o in orders} == {1}


def test_checked_preserves_legacy_and_existing_snapshots_and_only_renames_master(fixture):
    product = fixture.db.get(Product, 1)
    product.product_spec = "MASTER-SPEC"
    legacy = fixture._seed_open_order_line_without_lots()
    old_name = product.product_name
    assert legacy.source_product_name is None
    assert commit(fixture, [row(1)]).success_group_count == 1
    previous = fixture.db.scalar(select(OrderLine).where(OrderLine.order_no == row(1).erp_order_no))
    assert commit(fixture, [row(2, "New master [ORDER-SPEC]")], checked=[2]).success_group_count == 1
    fixture.db.refresh(legacy)
    fixture.db.refresh(previous)
    assert product.product_name == "New master"
    assert product.product_spec == "MASTER-SPEC"
    assert (legacy.source_product_name, legacy.source_product_spec) == (old_name, "MASTER-SPEC")
    assert previous.source_product_name == "Customer box"
    assert build_order_line_out(fixture.db, legacy).product_name == old_name


def test_conflicting_renames_across_order_groups_do_not_partially_apply(fixture):
    result = commit(fixture, [row(1, "Name A"), row(2, "Name B")], checked=[1, 2])
    assert result.failure_group_count == 2
    assert result.success_group_count == 0
    assert fixture.db.scalar(select(OrderLine)) is None
    assert fixture.db.get(Product, 1).product_name == "제품"


@pytest.mark.parametrize("name", ["", "   ", "[SPEC]", "N" * 201, "Name [" + "S" * 101 + "]"])
def test_invalid_snapshot_is_rejected_even_without_master_rename(fixture, name):
    result = commit(fixture, [row(name=name)])
    assert result.failure_group_count == 1
    assert fixture.db.scalar(select(OrderLine)) is None


def test_failed_registration_rolls_back_preservation_and_rename(fixture):
    legacy = fixture._seed_open_order_line_without_lots()
    product = fixture.db.get(Product, 1)
    fixture.db.scalar(select(RoutingTemplateStep)).is_active = False
    fixture.db.commit()
    result = commit(fixture, [row()], checked=[1])
    assert result.failure_group_count == 1
    fixture.db.refresh(legacy)
    fixture.db.refresh(product)
    assert legacy.source_product_name is None
    assert product.product_name == "제품"


def test_product_management_rename_also_preserves_old_orders(fixture):
    legacy = fixture._seed_open_order_line_without_lots()
    update_product(1, ProductUpdate(product_name="Master changed"), fixture.db)
    fixture.db.refresh(legacy)
    assert legacy.source_product_name == "제품"
    assert build_order_line_out(fixture.db, legacy).product_name == "제품"


def test_manual_registration_snapshots_current_master(fixture):
    with patch("app.services.order_line_creation_service.refresh_order_line_snapshot"):
        order = create_order_line_with_policy(fixture.db, fixture._payload("MANUAL", 10))
    assert order.source_product_name == "제품"
    assert order.source_erp_product_code == "P-001"


def test_maximum_name_and_specification_fit_the_import_contract(fixture):
    result = commit(fixture, [row(name="N" * 200 + " [" + "S" * 100 + "]")])
    assert result.success_group_count == 1


def test_same_name_different_specs_are_not_conflicting_master_renames(fixture):
    result = commit(fixture, [row(1, "Name [SPEC A]"), row(2, "Name [SPEC B]")], checked=[1, 2])
    assert result.success_group_count == 2
    assert fixture.db.get(Product, 1).product_spec is None
    orders = fixture.db.scalars(select(OrderLine).order_by(OrderLine.order_no)).all()
    assert [o.source_product_spec for o in orders] == ["SPEC A", "SPEC B"]


def test_omitted_order_spec_never_falls_back_to_later_master_spec(fixture):
    from app.services.order_line_lot_context_query import get_lot_create_context_dto
    assert commit(fixture, [row(name="Without spec")]).success_group_count == 1
    order = fixture.db.scalar(select(OrderLine))
    update_product(1, ProductUpdate(product_name="Later name", product_spec="LATER SPEC"), fixture.db)
    context = get_lot_create_context_dto(fixture.db, order.order_line_id)
    assert context.product_name == "Without spec"
    assert context.product_spec is None


@pytest.mark.parametrize("status, active", [("OPEN", True), ("DONE", True), ("CANCELED", False)])
def test_legacy_preservation_includes_completed_and_inactive_orders(fixture, status, active):
    legacy = fixture._seed_open_order_line_without_lots()
    legacy.status, legacy.is_active = status, active
    fixture.db.commit()
    timestamp = legacy.updated_at
    update_product(1, ProductUpdate(product_name="Rename 1"), fixture.db)
    update_product(1, ProductUpdate(product_name="Rename 2"), fixture.db)
    fixture.db.refresh(legacy)
    assert legacy.source_product_name == "제품"
    assert (legacy.status, legacy.is_active, legacy.updated_at) == (status, active, timestamp)


@pytest.mark.parametrize("display_name, expected_spec", [("Customer box [ORDER-SPEC]", "ORDER-SPEC"), ("Customer box", "-")])
def test_new_coa_uses_order_snapshot_and_existing_coa_is_not_rewritten(fixture, display_name, expected_spec):
    from app.models.shipment_line import ShipmentLine
    from app.services.shipment_coa_service import get_or_create_shipment_coa
    assert commit(fixture, [row(name=display_name)]).success_group_count == 1
    order = fixture.db.scalar(select(OrderLine))
    fixture.db.add(ShipmentLine(order_line_id=order.order_line_id, product_id=1,
                               source_type="STOCK", status="DONE", ship_qty=10, shipped_qty=10))
    fixture.db.commit()
    update_product(1, ProductUpdate(product_name="Later master", product_spec="MASTER"), fixture.db)
    coa = get_or_create_shipment_coa(fixture.db, order.order_line_id)
    assert coa.product_name_snapshot == "Customer box"
    assert coa.product_spec_snapshot == expected_spec
    update_product(1, ProductUpdate(product_name="Another master"), fixture.db)
    existing = get_or_create_shipment_coa(fixture.db, order.order_line_id)
    assert existing.shipment_coa_id == coa.shipment_coa_id
    assert existing.product_name_snapshot == "Customer box"
