from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.inspection_regression_gate import REQUIRED_TESTS, validate_report, validate_test_url

TEST_URL = "postgresql+psycopg://mes_regression@127.0.0.1:55439/mes_regression"


class InspectionReleaseGateTests(unittest.TestCase):
    def test_only_the_dedicated_database_is_allowed(self):
        validate_test_url(TEST_URL)
        for url in (None, "not a URL", TEST_URL.replace("55439", "5432"),
                    TEST_URL.replace("127.0.0.1", "172.30.1.240"),
                    TEST_URL.replace("/mes_regression", "/mes_db"),
                    TEST_URL.replace("mes_regression@", "mes_user@")):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_test_url(url)

    def test_skipped_missing_failed_or_duplicate_pg_tests_block_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tests.xml"
            for outcome in ("passed", "skipped", "failure", "error", "missing", "duplicate"):
                root = ET.Element("testsuite")
                for index, name in enumerate(sorted(REQUIRED_TESTS)):
                    if index == 0 and outcome == "missing":
                        continue
                    case = ET.SubElement(root, "testcase", classname="test_inspection_corrections.InspectionCorrectionsTests", name=name)
                    if index == 0 and outcome in ("skipped", "failure", "error"):
                        ET.SubElement(case, outcome)
                    if index == 0 and outcome == "duplicate":
                        ET.SubElement(root, "testcase", **case.attrib)
                ET.ElementTree(root).write(path)
                with self.subTest(outcome=outcome):
                    self.assertEqual(outcome != "passed", bool(validate_report(path, TEST_URL)))
            self.assertTrue(validate_report(path, None))
