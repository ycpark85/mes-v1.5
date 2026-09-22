import json
from pathlib import Path
import unittest

from app.services.inspection_quantity_policy import InspectionQuantityError, build_inspection_quantity_plan


class SharedInspectionQuantityTests(unittest.TestCase):
    def test_the_same_normalized_request_cases_are_used_by_backend_and_wpf(self):
        cases = json.loads((Path(__file__).parent / "fixtures/inspection_quantity_cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                arguments = dict(is_partial=case["partial"], good_qty=case["good"], defect_ship_qty=case["defect_ship"],
                    defect_qty=case["defect"], uninspected_qty=case["uninspected"], stock_ship_qty=case["stock_ship"],
                    result_ship_qty=case["production_ship"], stock_in_qty=case["stock_in"], discard_qty=case["discard"],
                    prior_unsettled_sellable_qty=case["carry"])
                if case["valid"]:
                    plan = build_inspection_quantity_plan(**arguments)
                    self.assertEqual(case["good"] + case["defect_ship"] + case["defect"], plan.inspected_qty)
                    self.assertEqual(case["good"] + case["defect_ship"] + case["carry"], plan.settlement_sellable_qty)
                else:
                    with self.assertRaises(InspectionQuantityError):
                        build_inspection_quantity_plan(**arguments)
