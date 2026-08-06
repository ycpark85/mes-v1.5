from __future__ import annotations

import unittest

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.order_line_change_log import OrderLineChangeLog
from app.services.order_line_change_history_service import (
    ORDER_LINE_DUE_DATE_CHANGE,
    ORDER_LINE_MEMO_CHANGE,
    ORDER_LINE_QUANTITY_CHANGE,
    record_order_line_change,
)
from app.services.order_line_change_timeline import (
    get_order_line_change_timeline_events,
)


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, compiler, **kw):
    return "JSON"


class OrderLineChangeHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[Base.metadata.tables["order_line_change_log"]],
        )
        SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
        )
        self.db = SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_records_and_builds_quantity_due_date_and_memo_events(self) -> None:
        record_order_line_change(
            self.db,
            order_line_id=1,
            lot_id=10,
            change_type=ORDER_LINE_QUANTITY_CHANGE,
            before_data={"order_qty": 100, "lot_qty": 102},
            after_data={"order_qty": 120, "lot_qty": 123},
            actor=" tester ",
        )
        record_order_line_change(
            self.db,
            order_line_id=1,
            change_type=ORDER_LINE_DUE_DATE_CHANGE,
            before_data={"due_date": "2026-08-10"},
            after_data={"due_date": "2026-08-15"},
            actor="tester",
        )
        record_order_line_change(
            self.db,
            order_line_id=1,
            change_type=ORDER_LINE_MEMO_CHANGE,
            before_data={"memo": None},
            after_data={"memo": "긴급"},
            actor="tester",
        )
        self.db.flush()

        events = get_order_line_change_timeline_events(
            self.db,
            order_line_id=1,
            uom="EA",
            lot_no_by_id={10: "LOT-010"},
        )

        self.assertEqual(
            [
                "ORDER_QUANTITY_CHANGED",
                "ORDER_DUE_DATE_CHANGED",
                "ORDER_MEMO_CHANGED",
            ],
            [event.event_type for event in events],
        )
        self.assertIn("LOT-010 계획수량 102 EA → 123 EA", events[0].summary)
        self.assertEqual("tester", events[0].actor)
        self.assertEqual("납기일 2026-08-10 → 2026-08-15", events[1].summary)
        self.assertEqual("메모 - → 긴급", events[2].summary)

    def test_database_rejects_unknown_change_type(self) -> None:
        self.db.add(
            OrderLineChangeLog(
                order_line_id=1,
                change_type="UNKNOWN",
                before_data={"value": 1},
                after_data={"value": 2},
                created_by="tester",
            )
        )

        with self.assertRaises(IntegrityError):
            self.db.flush()


if __name__ == "__main__":
    unittest.main()
