from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
import asyncio
import json
from urllib.parse import urlsplit
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import test_order_line_services as fixtures
from app.api.v1.router import router
from app.core.auth import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.models.drawing import Drawing
from app.models.partner_product_mapping import UnprintedProductCodeCounter


class ApiClient:
    # Exercise the ASGI contract without adding an HTTP client dependency.
    def __init__(self, app):
        self.app = app

    def request(self, method, url, payload=None):
        async def run():
            parts = urlsplit(url)
            body = json.dumps(payload).encode() if payload is not None else b""
            events = []
            delivered = False
            async def receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                await asyncio.Future()
            async def send(event):
                events.append(event)
            await self.app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": method, "scheme": "http", "path": parts.path, "raw_path": parts.path.encode(),
                "query_string": parts.query.encode(), "root_path": "", "headers": [(b"content-type", b"application/json")],
                "client": ("127.0.0.1", 12345), "server": ("testserver", 80)}, receive, send)
            status = next(event["status"] for event in events if event["type"] == "http.response.start")
            data = b"".join(event.get("body", b"") for event in events if event["type"] == "http.response.body").decode()
            return SimpleNamespace(status_code=status, text=data, json=lambda: json.loads(data))
        return asyncio.run(run())

    def get(self, url):
        return self.request("GET", url)

    def post(self, url, json):
        return self.request("POST", url, json)

    def delete(self, url):
        return self.request("DELETE", url)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    names = fixtures.TEST_TABLE_NAMES + ["unprinted_product_code_counter"]
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in names])
    with Session(engine) as db:
        fixture = fixtures.OrderLineServicesTests()
        fixture.db = db
        fixture._seed_base_data()
        db.add(Drawing(drawing_id=2, drawing_no="U-2", is_active=True))
        db.add(UnprintedProductCodeCounter(counter_id=1, next_value=1))
        db.commit()
    app = FastAPI()
    app.include_router(router)
    def test_db():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=1, login_id="tester")
    try:
        yield ApiClient(app)
    finally:
        engine.dispose()


def test_unprinted_api_lifecycle_and_existing_contract(client):
    with patch("app.core.auth.get_user_permission_codes", return_value=["PRODUCTS.VIEW", "PRODUCTS.WRITE"]):
        old = client.get("/products/1").json()
        assert old["product_code"] == "P-001" and old["is_unprinted_managed"] is False
        result = client.post("/products", json={"is_unprinted_managed": True, "product_code": "",
            "product_name": "Shared blank", "uom": "EA", "drawing_id": 2, "routing_template_id": 1})
        assert result.status_code == 201, result.text
        product_id = result.json()["product_id"]
        assert result.json()["product_code"] == "MES-U000001"
        route = f"/products/{product_id}/partner-mappings"
        bad = client.post(route, json={"partner_id": 1, "erp_product_code": "   ", "customer_product_name": "test"})
        assert bad.status_code == 422
        payload = {"partner_id": 1, "erp_product_code": " blank-1 ", "customer_product_name": "Customer blank"}
        mapping = client.post(route, json=payload)
        assert mapping.status_code == 201, mapping.text
        assert mapping.json()["erp_product_code"] == "BLANK-1"
        assert client.post(route, json=payload).status_code == 409
        assert client.get(route).json()["items"][0]["partner_name"] == "Customer"
        assert client.delete(f"/products/1/partner-mappings/{mapping.json()['mapping_id']}").status_code == 404
        assert client.delete(f"{route}/{mapping.json()['mapping_id']}").status_code == 200
        assert client.get(route).json()["total"] == 0
        history = client.get(route + "?include_inactive=true").json()
        assert history["total"] == 1 and history["items"][0]["is_active"] is False
        assert client.get("/products/1").json() == old


def test_product_list_management_filter_contract(client):
    with patch("app.core.auth.get_user_permission_codes", return_value=["PRODUCTS.VIEW", "PRODUCTS.WRITE"]):
        created = client.post("/products", json={"is_unprinted_managed": True, "product_code": "",
            "product_name": "Shared blank", "uom": "EA", "drawing_id": 2, "routing_template_id": 1})
        assert created.status_code == 201, created.text
        managed_id = created.json()["product_id"]
        for suffix, expected_ids in [("", [managed_id, 1]),
                ("&is_unprinted_managed=true", [managed_id]), ("&is_unprinted_managed=false", [1])]:
            result = client.get("/products?page=1&size=1" + suffix)
            assert result.status_code == 200, result.text
            data = result.json()
            assert data["total"] == len(expected_ids)
            assert [row["product_id"] for row in data["items"]] == expected_ids[:1]
            assert (data["page"], data["size"]) == (1, 1)
            second = client.get("/products?page=2&size=1" + suffix).json()
            assert [row["product_id"] for row in second["items"]] == expected_ids[1:]
            assert second["total"] == len(expected_ids)
        assert client.get("/products?is_unprinted_managed=true&is_active=false").json()["total"] == 0
        assert client.get("/products?is_unprinted_managed=false&q=MES-U").json()["total"] == 0
        assert client.get("/products?is_unprinted_managed=invalid").status_code == 422


def test_mapping_mutations_require_products_write_permission(client):
    with patch("app.core.auth.get_user_permission_codes", return_value=["PRODUCTS.VIEW"]):
        assert client.get("/products/1/partner-mappings").status_code == 200
        assert client.post("/products/1/partner-mappings", json={"partner_id": 1,
            "erp_product_code": "X", "customer_product_name": "X"}).status_code == 403
        assert client.delete("/products/1/partner-mappings/1").status_code == 403
