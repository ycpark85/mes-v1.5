from app.services.order_line_plan_policy import evaluate_order_line_plan_policy


def test_no_inventory_keeps_automatic_production() -> None:
    policy = evaluate_order_line_plan_policy(
        available_inventory_qty=0,
        target_ship_qty=102,
    )

    assert policy.recommended_fulfillment_mode == "PRODUCTION_FIRST"
    assert policy.recommended_production_qty == 102
    assert policy.allowed_plan_types == ()


def test_enough_inventory_requires_stock_or_replenishment_choice() -> None:
    policy = evaluate_order_line_plan_policy(
        available_inventory_qty=102,
        target_ship_qty=102,
    )

    assert [plan.value for plan in policy.allowed_plan_types] == [
        "STOCK_SHIP_COMPLETE",
        "STOCK_REPLENISHMENT",
    ]


def test_partial_inventory_keeps_existing_choices_and_adds_replenishment() -> None:
    policy = evaluate_order_line_plan_policy(
        available_inventory_qty=50,
        target_ship_qty=102,
    )

    assert policy.recommended_fulfillment_mode == "HYBRID"
    assert policy.recommended_production_qty == 52
    assert [plan.value for plan in policy.allowed_plan_types] == [
        "PARTIAL_STOCK_PLUS_PRODUCTION",
        "PARTIAL_STOCK_ONLY_CLOSE",
        "STOCK_REPLENISHMENT",
    ]
