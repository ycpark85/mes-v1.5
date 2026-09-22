import importlib.util
from pathlib import Path
import unittest

from sqlalchemy import create_engine, text


def load_migration():
    path = Path(__file__).resolve().parents[1] / "migrations/versions/6b7c8d9e0f1a_separate_short_close_decision.py"
    spec = importlib.util.spec_from_file_location("short_close_schema_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ShortCloseBackfillTests(unittest.TestCase):
    def test_only_latest_confirmed_plan_is_trusted_and_memos_are_not_rewritten(self):
        migration = load_migration()
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE order_line (order_line_id INTEGER PRIMARY KEY, status TEXT, decision_made BOOLEAN, memo TEXT, order_qty INTEGER DEFAULT 100, short_close_state TEXT DEFAULT 'NONE')"))
            conn.execute(text("CREATE TABLE order_line_plan_history (plan_history_id INTEGER PRIMARY KEY, order_line_id INTEGER, is_short_close BOOLEAN, created_at TEXT)"))
            conn.execute(text("INSERT INTO order_line (order_line_id,status,decision_made,memo) VALUES (:id,:status,:decision,:memo)"), [
                {"id": 1, "status": "DONE", "decision": True, "memo": "ordinary"},
                {"id": 2, "status": "DONE", "decision": True, "memo": "[SHORT_CLOSE] legacy"},
                {"id": 3, "status": "CLOSED", "decision": True, "memo": "[SHORT_CLOSE] mention"},
                {"id": 4, "status": "DONE", "decision": True, "memo": "ordinary"},
                {"id": 5, "status": "DONE", "decision": True, "memo": "[SHORT_CLOSE] old plan"},
                {"id": 6, "status": "DONE", "decision": False, "memo": "unconfirmed plan"},
                {"id": 7, "status": "DONE", "decision": True, "memo": "[SHORTXCLOSE] is not a marker"},
            ])
            conn.execute(text("INSERT INTO order_line_plan_history VALUES (1,1,true,'2026-09-14'),(2,5,true,'2026-09-14'),(3,5,false,'2026-09-14'),(4,6,true,'2026-09-14')"))
            before = conn.execute(text("SELECT order_line_id,status,memo,order_qty FROM order_line ORDER BY order_line_id")).all()
            migration.backfill_short_close_state(conn)
            migration.backfill_short_close_state(conn)
            self.assertEqual(["CONFIRMED", "REVIEW_REQUIRED", "NONE", "NONE", "REVIEW_REQUIRED", "NONE", "NONE"],
                conn.execute(text("SELECT short_close_state FROM order_line ORDER BY order_line_id")).scalars().all())
            self.assertEqual(before, conn.execute(text("SELECT order_line_id,status,memo,order_qty FROM order_line ORDER BY order_line_id")).all())
