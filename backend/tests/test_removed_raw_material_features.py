from __future__ import annotations

import unittest

from fastapi.routing import APIRoute

from app.main import app
from app.schemas.outsource_work_instruction import (
    OutsourceWorkGroupDetailOut,
    OutsourceWorkGroupListItemOut,
    OutsourceWorkGroupUpdateIn,
    OutsourceWorkInstructionGroupCreate,
)
from app.services.auth_seed import PERMISSION_SEEDS


class RemovedRawMaterialFeatureTests(unittest.TestCase):
    def test_raw_material_routes_are_not_registered(self) -> None:
        raw_material_paths = {
            route.path
            for route in app.routes
            if isinstance(route, APIRoute)
            and route.path.startswith("/api/v1/raw-materials")
        }

        self.assertEqual(set(), raw_material_paths)

    def test_raw_material_permissions_are_not_seeded(self) -> None:
        permission_codes = {
            seed["permission_code"]
            for seed in PERMISSION_SEEDS
        }

        self.assertNotIn("RAW_MATERIALS.VIEW", permission_codes)
        self.assertNotIn("RAW_MATERIALS.WRITE", permission_codes)
        self.assertNotIn("RAW_MATERIAL_INVENTORIES.VIEW", permission_codes)
        self.assertNotIn("RAW_MATERIAL_INVENTORIES.WRITE", permission_codes)

    def test_outsource_contract_does_not_expose_raw_material_allocations(self) -> None:
        for schema in (
            OutsourceWorkInstructionGroupCreate,
            OutsourceWorkGroupListItemOut,
            OutsourceWorkGroupDetailOut,
            OutsourceWorkGroupUpdateIn,
        ):
            self.assertNotIn("raw_material_allocations", schema.model_fields)
            self.assertNotIn("raw_material_qty", schema.model_fields)
            self.assertNotIn("raw_material_lot_nos_text", schema.model_fields)


if __name__ == "__main__":
    unittest.main()
