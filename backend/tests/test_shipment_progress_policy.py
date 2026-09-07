from app.services.ship_qty_policy import build_shipment_progress


def test_saved_result_is_excluded_from_prior_shipment_quantity() -> None:
    progress = build_shipment_progress(
        ship_target_qty=40_800,
        total_shipped_qty=12_000,
        current_result_shipped_qty=12_000,
    )

    assert progress.prior_shipped_qty == 0
    assert progress.remaining_before_current_result_qty == 40_800
    assert progress.remaining_after_current_result_qty == 28_800


def test_later_split_round_keeps_earlier_shipment_as_prior() -> None:
    progress = build_shipment_progress(
        ship_target_qty=40_800,
        total_shipped_qty=22_000,
        current_result_shipped_qty=10_000,
    )

    assert progress.prior_shipped_qty == 12_000
    assert progress.total_shipped_qty == 22_000
    assert progress.remaining_before_current_result_qty == 28_800
    assert progress.remaining_after_current_result_qty == 18_800
