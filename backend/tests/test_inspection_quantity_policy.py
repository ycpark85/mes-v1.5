from __future__ import annotations

import unittest

from app.services.inspection_quantity_policy import (
    InspectionQuantityError,
    build_inspection_quantity_plan,
)


class InspectionQuantityPolicyTests(unittest.TestCase):
    def test_legacy_unsettled_qty_is_included_in_explicit_allocation(self) -> None:
        plan = build_inspection_quantity_plan(
            is_partial=False, good_qty=8, defect_ship_qty=2, defect_qty=1,
            stock_ship_qty=0, result_ship_qty=10, stock_in_qty=5,
            discard_qty=0, uninspected_qty=0,
            prior_unsettled_sellable_qty=5,
        )

        self.assertEqual(15, plan.result_ship_qty + plan.stock_in_qty + plan.discard_qty)
        self.assertEqual(5, plan.stock_in_qty)
        self.assertEqual(15, plan.settlement_sellable_qty)
        self.assertEqual(11, plan.inspected_qty)

    def test_mismatched_sellable_allocation_is_rejected(self) -> None:
        with self.assertRaises(InspectionQuantityError):
            build_inspection_quantity_plan(
                is_partial=False, good_qty=10, defect_ship_qty=0, defect_qty=0,
                stock_ship_qty=0, result_ship_qty=9, stock_in_qty=0,
                discard_qty=0, uninspected_qty=0,
                prior_unsettled_sellable_qty=0,
            )

    def test_partial_result_requires_immediate_round_allocation(self) -> None:
        plan = build_inspection_quantity_plan(
            is_partial=True, good_qty=3, defect_ship_qty=1, defect_qty=1,
            stock_ship_qty=2, result_ship_qty=2, stock_in_qty=1,
            discard_qty=1, uninspected_qty=0,
            prior_unsettled_sellable_qty=0,
        )

        self.assertEqual(
            (2, 2, 1, 1, 0),
            (plan.stock_ship_qty, plan.result_ship_qty, plan.stock_in_qty,
             plan.discard_qty, plan.uninspected_qty),
        )

    def test_partial_result_rejects_uninspected_qty(self) -> None:
        with self.assertRaises(InspectionQuantityError):
            build_inspection_quantity_plan(
                is_partial=True, good_qty=3, defect_ship_qty=0, defect_qty=0,
                stock_ship_qty=0, result_ship_qty=0, stock_in_qty=3,
                discard_qty=0, uninspected_qty=1,
                prior_unsettled_sellable_qty=0,
            )


if __name__ == "__main__":
    unittest.main()
