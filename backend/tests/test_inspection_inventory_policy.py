import unittest

from app.services.inspection_inventory_policy import (
    InspectionInventoryDelta, InspectionInventoryPlanError, ShipmentAllocation,
    ShipmentChange, build_inventory_delta, inventory_lot_deltas, plan_shipment_changes,
)


class InspectionInventoryPolicyTests(unittest.TestCase):
    def test_equal_save_has_no_inventory_actions_but_still_checks_ledger(self):
        arguments = dict(stock_ship_qty=10, result_ship_qty=50, stock_in_qty=30,
            previous_inventory_in=80, previous_stock_ship=10, previous_production_ship=50, posted_shipment=60)
        delta = build_inventory_delta(**arguments)
        self.assertFalse(delta.has_changes)
        with self.assertRaises(InspectionInventoryPlanError):
            build_inventory_delta(**{**arguments, "posted_shipment": 59})

    def test_reservations_precede_fifo_and_input_rows_are_unchanged(self):
        waiting = (ShipmentAllocation(8, 2, "STOCK", 40),)
        available = ((1, 30), (2, 40), (3, 10))
        changes = plan_shipment_changes(delta=InspectionInventoryDelta(50, 60, 20),
            existing=(), waiting=waiting, available_stock=available, production_lot_id=4)
        self.assertEqual((ShipmentChange(8, 2, "STOCK", 40), ShipmentChange(None, 1, "STOCK", 20),
            ShipmentChange(None, 4, "INSPECTION_RESULT", 20)), changes)
        self.assertEqual(40, waiting[0].qty)
        self.assertEqual(((1, 30), (2, 40), (3, 10)), available)
        self.assertEqual({4: 30, 2: -40, 1: -20}, inventory_lot_deltas(4, InspectionInventoryDelta(50, 60, 20), changes))

    def test_reduction_keeps_older_allocations_and_reverses_latest_first(self):
        existing = (ShipmentAllocation(1, 1, "STOCK", 25), ShipmentAllocation(2, 2, "STOCK", 30),
                    ShipmentAllocation(3, 4, "INSPECTION_RESULT", 10))
        changes = plan_shipment_changes(delta=InspectionInventoryDelta(-10, -35, -10),
            existing=existing, waiting=(), available_stock=(), production_lot_id=4)
        self.assertEqual((ShipmentChange(2, 2, "STOCK", -30), ShipmentChange(1, 1, "STOCK", -5),
            ShipmentChange(3, 4, "INSPECTION_RESULT", -10)), changes)

    def test_insufficient_stock_or_unreconciled_allocations_fail(self):
        for delta in (InspectionInventoryDelta(0, 11, 0), InspectionInventoryDelta(0, -1, 0)):
            with self.subTest(delta=delta), self.assertRaises(InspectionInventoryPlanError):
                plan_shipment_changes(delta=delta, existing=(), waiting=(), available_stock=((1, 10),), production_lot_id=2)

    def test_total_stock_change_conserves_new_input_minus_shipment_across_cases(self):
        for stock_qty in (0, 1, 20, 50, 80):
            for production_qty in (0, 5, 40):
                delta = InspectionInventoryDelta(60, stock_qty, production_qty)
                changes = plan_shipment_changes(delta=delta, existing=(),
                    waiting=(ShipmentAllocation(1, 2, "STOCK", 20),),
                    available_stock=((1, 30), (2, 50)), production_lot_id=3)
                self.assertEqual(60 - stock_qty - production_qty, sum(inventory_lot_deltas(3, delta, changes).values()))
                self.assertEqual(stock_qty, sum(change.qty for change in changes if change.source == "STOCK"))
