from contextlib import contextmanager

from sqlalchemy import select

import test_order_line_services as order_fixtures
import test_inspection_work_instruction_query as schedule_fixtures
import test_inspection_result_query as result_fixtures
from app.models.order_line import OrderLine
from app.models.product import Product
from app.services.order_line_list_query import list_order_lines_for_grid
from app.services.order_line_lot_context_query import get_lot_create_context_dto
from app.services.inspection_work_instruction_query import list_inspection_schedule_items
from app.services.inspection_result_query import list_inspection_results_for_grid
from app.services.inspection_result_query import get_inspection_result_detail


@contextmanager
def example(fixture_type):
    fixture = fixture_type()
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.tearDown()


def set_order_code(db, order):
    order.source_erp_product_code = 'SHARED-ERP-100'
    order.source_product_name = '거래처별 무지 품명'
    order.source_product_spec = '100×200'
    db.commit()
    return db.get(Product, order.product_id).product_code


def test_order_list_and_lot_context_separate_business_and_mes_codes():
    with example(order_fixtures.OrderLineServicesTests) as fixture:
        order = fixture._seed_open_order_line_without_lots()
        mes_code = set_order_code(fixture.db, order)
        items, total, _ = list_order_lines_for_grid(fixture.db, page=1, size=20, q='SHARED-ERP-100')
        assert total == 1
        assert items[0]['product_code'] == 'SHARED-ERP-100'
        assert items[0]['mes_product_code'] == mes_code
        context = get_lot_create_context_dto(fixture.db, order.order_line_id)
        assert context.product_code == 'SHARED-ERP-100'
        assert context.mes_product_code == mes_code


def test_inspection_schedule_search_and_display_use_order_code():
    with example(schedule_fixtures.InspectionWorkInstructionQueryTests) as fixture:
        for order in fixture.db.scalars(select(OrderLine)).all():
            set_order_code(fixture.db, order)
        rows = list_inspection_schedule_items(fixture.db, product_q='SHARED-ERP-100')
        assert rows
        assert all(row.product_code == 'SHARED-ERP-100' and row.mes_product_code for row in rows)


def test_inspection_results_search_and_display_use_order_code():
    with example(result_fixtures.InspectionResultQueryTests) as fixture:
        for order in fixture.db.scalars(select(OrderLine)).all():
            set_order_code(fixture.db, order)
        result = list_inspection_results_for_grid(fixture.db, q='SHARED-ERP-100')
        assert result.items
        assert all(row.product_code == 'SHARED-ERP-100' and row.mes_product_code for row in result.items)
        detail = get_inspection_result_detail(fixture.db, result.items[0].inspection_schedule_id, view_mode='saved')
        assert detail.product_code == 'SHARED-ERP-100'
        assert detail.mes_product_code == result.items[0].mes_product_code


def test_shared_code_still_keeps_different_mes_products_and_drawings():
    import test_unprinted_product_management as fixtures
    from app.services.lot_query import list_lots
    with example(fixtures.UnprintedProductManagementTests) as fixture:
        fixture.mapping(2)
        fixture.mapping(3)
        fixture.mapping(4, fixture.second.product_id)
        result = fixture.commit([fixture.row(1, '업체A'), fixture.row(2, '업체B'), fixture.row(3, '업체C')])
        assert result.success_group_count == 3
        rows, total, _ = list_order_lines_for_grid(fixture.db, page=1, size=20, q='MUJI-100')
        assert total == 3
        assert {row['product_code'] for row in rows} == {'MUJI-100'}
        assert {row['mes_product_code'] for row in rows} == {fixture.first.product_code, fixture.second.product_code}
        lots = list_lots(fixture.db, page=1, size=20, q='MUJI-100')
        assert lots.meta.total == 3
        assert {row.product_code for row in lots.items} == {'MUJI-100'}
        assert {row.product_id for row in lots.items} == {fixture.first.product_id, fixture.second.product_id}


def test_lot_trace_keeps_order_code():
    import test_lot_trace_query as fixtures
    from app.services.lot_trace_query import get_lot_trace_detail_for_lot
    with example(fixtures.LotTraceQueryTests) as fixture:
        fixture._seed_full_trace()
        for order in fixture.db.scalars(select(OrderLine)).all():
            set_order_code(fixture.db, order)
        trace = get_lot_trace_detail_for_lot(fixture.db, 1)
        assert trace.product_order.product_code == 'SHARED-ERP-100'
        assert trace.product_order.mes_product_code


def test_outsource_documents_and_search_keep_order_code():
    import test_outsource_work_instruction_query as fixtures
    from app.services.outsource_work_instruction_query import (
        build_work_instruction_out, get_work_group_detail, list_candidate_lots, list_work_groups,
    )
    from app.models.outsource_work_instruction import OutsourceWorkInstruction
    from app.models.outsource_work_group import OutsourceWorkGroup
    with example(fixtures.OutsourceWorkInstructionQueryTests) as fixture:
        for order in fixture.db.scalars(select(OrderLine)).all():
            set_order_code(fixture.db, order)
        candidates = list_candidate_lots(fixture.db, q='SHARED-ERP-100')
        assert [row.lot_id for row in candidates.items] == [2]
        assert candidates.items[0].product_code == 'SHARED-ERP-100'
        assert candidates.items[0].mes_product_code == 'P-002'
        groups = list_work_groups(fixture.db, q='SHARED-ERP-100')
        assert groups.total_count == 1
        assert groups.items[0].product_codes_text == 'SHARED-ERP-100'
        assert groups.items[0].mes_product_codes_text == 'P-001'
        for instruction in fixture.db.scalars(select(OutsourceWorkInstruction)).all():
            output = build_work_instruction_out(fixture.db, instruction)
            assert output.items
            assert all(row.product_code == 'SHARED-ERP-100' and row.mes_product_code for row in output.items)
        for group in fixture.db.scalars(select(OutsourceWorkGroup)).all():
            detail = get_work_group_detail(fixture.db, group.outsource_work_group_id)
            assert all(row.product_code == 'SHARED-ERP-100' and row.mes_product_code for row in detail.lots)


def test_existing_production_snapshot_displays_order_code_without_rebuild():
    import test_production_daily_query as fixtures
    from app.models.production_progress_snapshot import ProductionProgressSnapshot
    from app.services.production_daily_query import list_production_daily_rows
    with example(fixtures.ProductionDailyQueryTests) as fixture:
        ProductionProgressSnapshot.__table__.create(fixture.engine)
        fixture.db.flush()
        order = fixture.db.get(OrderLine, 1)
        mes_code = set_order_code(fixture.db, order)
        snapshot = ProductionProgressSnapshot(
            order_line_id=1, order_no=order.order_no, line_no=order.line_no, due_date=order.due_date,
            partner_id=1, partner_name='Customer', product_id=1, product_code=mes_code,
            product_name='Product', work_type='BASIC', current_process='LOT_CREATED',
            current_process_order=1, progress_rate=10, status='IN_PROGRESS',
        )
        fixture.db.add(snapshot)
        fixture.db.commit()
        for keyword in ['SHARED-ERP-100', mes_code]:
            rows, total = list_production_daily_rows(fixture.db, page=1, size=20, product_q=keyword)
            assert total == 1
            assert rows[0]['product_code'] == 'SHARED-ERP-100'
            assert rows[0]['mes_product_code'] == mes_code
        fixture.db.refresh(snapshot)
        assert snapshot.product_code == mes_code


def test_shipment_display_and_search_keep_order_code():
    import test_shipment_list_query as fixtures
    from app.services.shipment_list_query import list_shipments_for_grid
    with example(fixtures.ShipmentListQueryTests) as fixture:
        mes_code = set_order_code(fixture.db, fixture.db.get(OrderLine, 1))
        rows, total = list_shipments_for_grid(fixture.db, status='DONE', page=1, size=20, q='SHARED-ERP-100')
        assert total == 4
        assert all(row.product_code == 'SHARED-ERP-100' and row.mes_product_code == mes_code for row in rows)


def test_existing_order_without_source_keeps_its_code():
    with example(order_fixtures.OrderLineServicesTests) as fixture:
        order = fixture._seed_open_order_line_without_lots()
        original = fixture.db.get(Product, order.product_id).product_code
        context = get_lot_create_context_dto(fixture.db, order.order_line_id)
        assert context.product_code == context.mes_product_code == original


def test_outsource_purchase_order_retains_each_lots_business_code():
    import test_outsource_purchase_order_query as fixtures
    from app.services.outsource_purchase_order_query import get_purchase_order_detail
    with example(fixtures.OutsourcePurchaseOrderQueryTests) as fixture:
        for order in fixture.db.scalars(select(OrderLine)).all():
            set_order_code(fixture.db, order)
        result = get_purchase_order_detail(fixture.db, 1)
        assert len(result.items) == 2
        assert all(row.product_code == 'SHARED-ERP-100' and row.mes_product_code for row in result.items)
        assert len({row.mes_product_code for row in result.items}) == 2


def test_bohyun_group_search_and_display_keep_business_code():
    import test_bohyun_outsource_service as fixtures
    from app.services.bohyun_outsource_service import list_bohyun_outsource_groups
    with example(fixtures.BohyunOutsourceServiceTests) as fixture:
        fixture._add_work_group(group_id=1, status=None)
        for order in fixture.db.scalars(select(OrderLine)).all():
            set_order_code(fixture.db, order)
        result = list_bohyun_outsource_groups(fixture.db, q='SHARED-ERP-100')
        assert len(result.items) == 1
        assert result.items[0].items
        assert all(row.product_code == 'SHARED-ERP-100' and row.mes_product_code for row in result.items[0].items)
