import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.v1.inspection_results import put_result
from app.core.observability import observe_request
from app.core.runtime_contract import get_runtime_info, validate_inspection_client
from app.schemas.inspection_result import InspectionResultUpsertIn


class RuntimeContractTests(unittest.TestCase):
    def test_runtime_metadata_is_explicit_and_excludes_secrets(self):
        with patch("app.core.runtime_contract.settings") as settings:
            settings.MES_SERVER_BUILD_ID = "release-20260914"
            result = get_runtime_info().model_dump()
        self.assertEqual("release-20260914", result["server_build"])
        self.assertEqual(2, result["inspection_quantity_rule_version"])
        self.assertEqual({"environment", "server_build", "min_wpf_contract_version",
            "max_wpf_contract_version", "inspection_quantity_rule_version"}, set(result))

    def test_missing_old_future_or_invalid_contract_rejected(self):
        for contract, quantity in [(None, 2), ("0", 2), ("2", 2), ("1", None), ("1", 1),
                                   ("1", 3), ("invalid", 2), ("1\n", 2)]:
            with self.subTest(contract=contract, quantity=quantity):
                with self.assertRaises(HTTPException) as caught:
                    validate_inspection_client(contract, quantity)
                self.assertEqual(409, caught.exception.status_code)
                self.assertIn("프로그램 업데이트", caught.exception.detail)
                self.assertEqual("CLIENT_UPDATE_REQUIRED", caught.exception.headers["X-MES-Error-Code"])
        validate_inspection_client("1", 2)

    def test_unconfigured_release_uses_source_fingerprint(self):
        with patch("app.core.runtime_contract.settings") as settings:
            settings.MES_SERVER_BUILD_ID = "unknown"
            result = get_runtime_info()
        self.assertRegex(result.server_build, r"^src-[0-9a-f]{40}$")

    def test_old_wpf_is_rejected_before_any_database_mutation(self):
        db = MagicMock()
        request = Request({"type": "http", "headers": []})
        payload = InspectionResultUpsertIn(good_qty=10, defect_qty=0, stock_in_qty=10, quantity_rule_version=2)
        with patch("app.api.v1.inspection_results.upsert_inspection_result") as save:
            with self.assertRaises(HTTPException):
                put_result(1, payload, request, db, SimpleNamespace(login_id="tester"))
        save.assert_not_called()
        self.assertEqual([], db.mock_calls)

    def test_supported_client_reaches_existing_save_path(self):
        db = MagicMock()
        request = Request({"type": "http", "headers": [(b"x-mes-client-contract", b"1")]})
        payload = InspectionResultUpsertIn(good_qty=10, defect_qty=0, stock_in_qty=10, quantity_rule_version=2)
        with patch("app.api.v1.inspection_results.upsert_inspection_result", return_value=(object(), "DONE", None)) as save:
            result = put_result(1, payload, request, db, SimpleNamespace(login_id="tester"))
        self.assertEqual("DONE", result["schedule_status"])
        self.assertEqual(10, save.call_args.kwargs["stock_in_qty"])
        db.commit.assert_called_once()


class RuntimeTraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_headers_are_correlated_and_sanitized(self):
        request = Request({"type": "http", "method": "GET", "path": "/runtime-info",
            "headers": [(b"x-request-id", b"trace-test"), (b"x-mes-client-version", b"1.0.0.0"),
                        (b"x-mes-client-build", b"unsafe\nPRIVATE")]})
        async def next_call(_):
            return JSONResponse({"ok": True})
        with self.assertLogs("mes.request", "INFO") as captured:
            response = await observe_request(request, next_call, 60000)
        output = "\n".join(captured.output)
        self.assertIn("request_id=trace-test", output)
        self.assertIn("client_version=1.0.0.0", output)
        self.assertIn("client_build=unknown", output)
        self.assertNotIn("PRIVATE", output)
        self.assertIn("X-MES-Server-Build", response.headers)
