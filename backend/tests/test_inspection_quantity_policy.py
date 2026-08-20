from __future__ import annotations

import unittest

from app.services.inspection_quantity_policy import (
    InspectionQuantityError,
    build_inspection_quantity_plan,
)


class InspectionQuantityPolicyTests(unittest.TestCase):
    def test_prior_sellable_qty_is_allocated_to_stock_for_legacy_request(self) -> None:
        plan = build_inspection_quantity_plan(
            is_partial=False, good_qty=8, defect_ship_qty=2, defect_qty=1,
            stock_ship_qty=0, result_ship_qty=10, stock_in_qty=0,
            discard_qty=0, uninspected_qty=0, prior_good_qty=4,
            prior_defect_ship_qty=1,
        )

        self.assertEqual(15, plan.result_ship_qty + plan.stock_in_qty + plan.discard_qty)
        self.assertEqual(5, plan.stock_in_qty)
        self.assertEqual(11, plan.inspected_qty)

    def test_mismatched_sellable_allocation_is_rejected(self) -> None:
        with self.assertRaises(InspectionQuantityError):
            build_inspection_quantity_plan(
                is_partial=False, good_qty=10, defect_ship_qty=0, defect_qty=0,
                stock_ship_qty=0, result_ship_qty=9, stock_in_qty=0,
                discard_qty=0, uninspected_qty=0, prior_good_qty=0,
                prior_defect_ship_qty=0,
            )

    def test_partial_result_does_not_change_inventory_allocations(self) -> None:
        plan = build_inspection_quantity_plan(
            is_partial=True, good_qty=3, defect_ship_qty=1, defect_qty=1,
            stock_ship_qty=2, result_ship_qty=2, stock_in_qty=2,
            discard_qty=1, uninspected_qty=10, prior_good_qty=0,
            prior_defect_ship_qty=0,
        )

        self.assertEqual(
            (0, 0, 0, 0, 0),
            (plan.stock_ship_qty, plan.result_ship_qty, plan.stock_in_qty,
             plan.discard_qty, plan.uninspected_qty),
        )


if __name__ == "__main__":
    unittest.main()
