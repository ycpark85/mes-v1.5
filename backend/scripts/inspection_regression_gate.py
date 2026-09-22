"""Fail release validation when mandatory PostgreSQL tests were not executed."""
import argparse
import os
from pathlib import Path
import xml.etree.ElementTree as ET

from sqlalchemy.engine import make_url

REQUIRED_TESTS = frozenset({
    "test_concurrent_result_edit_has_one_winner",
    "test_concurrent_reservations_cannot_reserve_same_stock_twice",
    "test_postgres_migration_upgrade_downgrade_and_history_guard",
    "test_short_close_migration_constraints_backfill_and_history_guard",
    "test_inspection_read_snapshot_stays_consistent_during_stock_change",
    "test_inspection_read_session_is_read_only_and_resets_on_close",
})


def validate_test_url(value: str | None) -> None:
    try:
        url = make_url(value or "")
        valid = (url.get_backend_name() == "postgresql" and
            (url.host, url.port, url.username, url.database) ==
            ("127.0.0.1", 55439, "mes_regression", "mes_regression"))
    except Exception:
        valid = False
    if not valid:
        raise ValueError("MES_INSPECTION_TEST_PG_URL must point to the dedicated local mes_regression database and role on port 55439; connection details are not logged")


def validate_report(path: Path, pg_url: str | None) -> list[str]:
    try:
        validate_test_url(pg_url)
    except ValueError as error:
        return [str(error)]
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return ["Backend JUnit report is missing or invalid"]
    cases = [case for case in root.iter("testcase")
             if case.get("classname", "").endswith("InspectionCorrectionsTests")]
    failures = []
    for name in sorted(REQUIRED_TESTS):
        matches = [case for case in cases if case.get("name") == name]
        if len(matches) != 1 or any(matches[0].find(tag) is not None for tag in ("skipped", "error", "failure")):
            failures.append(f"Required PostgreSQL regression did not pass: {name}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    failures = validate_report(args.report, os.environ.get("MES_INSPECTION_TEST_PG_URL"))
    print("\n".join(failures) if failures else "Required PostgreSQL regressions passed")
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
