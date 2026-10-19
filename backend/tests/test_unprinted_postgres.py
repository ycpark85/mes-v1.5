"""Opt-in PostgreSQL migration/concurrency checks; never falls back to the app DB."""
import os
import configparser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, text, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import settings
from app.api.v1.products import create_product, create_partner_mapping
from app.models.product import Product
from app.models.partner_product_mapping import PartnerProductMapping
from app.models.user import User
from app.schemas.product import ProductCreate
from app.schemas.partner_product_mapping import PartnerProductMappingCreate
from app.services.partner_product_mapping_service import resolve_erp_product, deactivate_mapping


TEST_URL = os.environ.get("MES_UNPRINTED_TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_URL, reason="MES_UNPRINTED_TEST_DATABASE_URL is required for isolated PostgreSQL checks")
def test_migration_preservation_concurrency_and_rollback_guard():
    url = make_url(TEST_URL)
    assert url.host == "127.0.0.1" and url.port == 55440
    assert url.database == "mes_unprinted_test" and url.username == "mes_unprinted_test"
    schema = "test_unprinted_" + uuid4().hex
    admin = create_engine(url, connect_args={"connect_timeout": 5})
    with admin.begin() as db:
        db.execute(CreateSchema(schema))
        # Own version table prevents Alembic from discovering the public schema's version.
        db.execute(text(f'CREATE TABLE "{schema}".alembic_version (version_num varchar(32) NOT NULL PRIMARY KEY)'))
    scoped_url = url.update_query_dict({"options": f"-csearch_path={schema},public", "connect_timeout": "5"})
    engine = create_engine(scoped_url)
    previous_url = settings.database_url
    settings.database_url = scoped_url.render_as_string(hide_password=False)
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.file_config._interpolation = configparser.Interpolation()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    try:
        command.upgrade(cfg, "7c8d9e0f1a2b")
        with engine.begin() as db:
            db.execute(text("INSERT INTO partner (partner_id,partner_type,name,business_no,is_active) VALUES (1,'CUSTOMER','A','TEST-A',true),(2,'CUSTOMER','B','TEST-B',true)"))
            db.execute(text("INSERT INTO drawing (drawing_id,drawing_no,is_active) SELECT n, 'TEST-D-' || n, true FROM generate_series(1,8) n"))
            db.execute(text("INSERT INTO routing_template (routing_template_id,template_code,template_name,is_active) VALUES (1,'TEST-RT','Test routing',true)"))
            db.execute(text("INSERT INTO product (product_id,product_code,product_name,uom,drawing_id,routing_template_id,is_active) VALUES (1,'PRINT-OLD','Printed old','EA',1,1,true)"))
            db.execute(text("SELECT setval(pg_get_serial_sequence('product','product_id'),1)"))
            db.execute(text("INSERT INTO order_line (order_no,line_no,partner_id,product_id,order_date,due_date,order_qty,uom,memo,status,is_active,priority,extra_production_qty,decision_made) VALUES ('OLD',1,1,1,'2026-01-01','2026-01-31',10,'EA','Keep original','OPEN',true,0,0,false)"))
            db.execute(text("INSERT INTO product_inventory (product_id,current_qty) VALUES (1,77)"))
            before = {table: db.execute(text(f"SELECT row_to_json(t)::text FROM {table} t")).scalars().all()
                      for table in ("product", "order_line", "product_inventory")}
        command.upgrade(cfg, "head")
        command.check(cfg)
        with engine.connect() as db:
            assert db.execute(text("SELECT is_unprinted_managed FROM product WHERE product_id=1")).scalar() is False
            assert db.execute(text("SELECT source_product_name FROM order_line WHERE order_no='OLD'")).scalar() is None
            # Compare every legacy column, including timestamps and existing flags.
            import json
            for table, rows in before.items():
                actual = json.loads(db.execute(text(f"SELECT row_to_json(t)::text FROM {table} t")).scalar_one())
                old = json.loads(rows[0])
                assert {key: actual[key] for key in old} == old
        command.downgrade(cfg, "7c8d9e0f1a2b")
        command.upgrade(cfg, "head")

        barrier = Barrier(4)
        def register(n):
            with Session(engine) as db:
                barrier.wait(timeout=10)
                return create_product(ProductCreate(is_unprinted_managed=True, product_name=f"Unprinted {n}",
                    uom="EA", drawing_id=n + 2, routing_template_id=1), db=db)
        with ThreadPoolExecutor(max_workers=4) as executor:
            products = list(executor.map(register, range(4)))
        assert len({x.product_code for x in products}) == 4
        assert sorted(x.product_code for x in products) == [f"MES-U{n:06d}" for n in range(1,5)]

        duplicate_barrier = Barrier(2)
        def connect(product):
            with Session(engine) as db:
                duplicate_barrier.wait(timeout=10)
                try:
                    obj = create_partner_mapping(PartnerProductMappingCreate(partner_id=1, erp_product_code="SHARED",
                        customer_product_name="Customer name"), product_id=product.product_id, db=db,
                        current_user=User(user_id=1, login_id="tester", user_name="Tester", password_hash="unused"))
                    return obj.mapping_id
                except HTTPException as exc:
                    assert exc.status_code == 409
                    return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            links = list(executor.map(connect, products[:2]))
        assert sum(x is not None for x in links) == 1
        with Session(engine) as db:
            mapped_product, mapping = resolve_erp_product(db, 1, "SHARED", lock=True)
            assert mapped_product.is_unprinted_managed
            mapping_id, product_id = mapping.mapping_id, mapping.product_id
            # A committed order resolution holds the link stable until its transaction ends.
            def try_unlink():
                with Session(engine) as other:
                    other.execute(text("SET LOCAL lock_timeout='250ms'"))
                    from sqlalchemy.exc import OperationalError
                    try:
                        deactivate_mapping(other, product_id, mapping_id, actor="tester")
                    except OperationalError:
                        other.rollback()
                        return "blocked"
                    return "unexpected"
            with ThreadPoolExecutor(max_workers=1) as executor:
                assert executor.submit(try_unlink).result(timeout=5) == "blocked"
            db.rollback()
        with pytest.raises(RuntimeError, match="무지|unprinted|Unprinted"):
            command.downgrade(cfg, "7c8d9e0f1a2b")
        with engine.connect() as db:
            assert db.execute(text("SELECT version_num FROM alembic_version")).scalar() == "8d9e0f1a2b3c"
            assert db.execute(select(Product.product_code).where(Product.product_id == 1)).scalar() == "PRINT-OLD"
            assert len(db.execute(select(PartnerProductMapping)).all()) == 1
        command.check(cfg)
    finally:
        settings.database_url = previous_url
        engine.dispose()
        # Only the randomly named schema created above is removed, on the guarded test DB.
        with admin.begin() as db:
            db.execute(DropSchema(schema, cascade=True))
        admin.dispose()
