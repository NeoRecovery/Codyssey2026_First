"""실제 임시 CSV와 CLI를 통한 주요 요구사항/실패 시 원본 보존 검증."""
from contextlib import redirect_stdout, redirect_stderr
import csv
import io
from itertools import islice
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from budget_app.cli import main
from budget_app.models import AppError
from budget_app.service import BudgetService
from budget_app.storage import CSV_FIELDS, atomic_csv, data_lock, initialize


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "data"
        self.directory.mkdir()
        initialize(self.directory)
        self.service = BudgetService(self.directory)

    def row(self, **changes):
        return {"date": "2026-10-15", "type": "expense", "category": "food",
                "amount": "15000", "memo": "점심, 커피\n후식", "tags": "meal,work", **changes}

    def cli(self, *args, inputs=()):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error), patch("builtins.input", side_effect=inputs):
            code = main(["--data-dir", str(self.directory), *args])
        return code, output.getvalue(), error.getvalue()

    def csv_input(self, rows, fields=CSV_FIELDS):
        path = Path(self.temp.name) / "input.csv"
        atomic_csv(path, fields, rows)
        return path

    def test_first_run_creates_three_persistent_files(self):
        self.assertEqual({p.name for p in self.directory.iterdir()},
                         {"transactions.csv", "categories.csv", "budgets.csv"})
        self.assertIn("food", self.service.categories.load())

    def test_interactive_add_reprompts_invalid_fields_and_persists(self):
        code, out, err = self.cli("add", inputs=["2026-02-30", "2026-10-31",
              "other", "expense", "unknown", "food", "-1", "15000", "식사", "meal,work"])
        self.assertEqual(code, 0, err)
        self.assertIn("[저장 완료]", out)
        tx = next(BudgetService(self.directory).transactions.iter_all())
        self.assertEqual((tx.date, tx.amount, tx.tags), ("2026-10-31", 15000, ("meal", "work")))

    def test_add_rejects_invalid_data(self):
        for changes in ({"date": "2026-2-01"}, {"date": "2026-02-30"},
                        {"type": "other"}, {"amount": "0"}, {"amount": "-1"},
                        {"amount": "1.5"}, {"category": "missing"}):
            with self.subTest(changes=changes), self.assertRaises(AppError):
                self.service.add(self.row(**changes))
        self.assertEqual(list(self.service.transactions.iter_all()), [])

    def test_list_latest_dates_and_limit(self):
        for day in ("20", "01", "31"):
            self.service.add(self.row(date=f"2026-10-{day}"))
        code, out, _ = self.cli("list", "--limit", "2")
        self.assertEqual(code, 0)
        self.assertLess(out.index("2026-10-31"), out.index("2026-10-20"))
        self.assertNotIn("2026-10-01", out)

    def test_limit_does_not_read_entire_storage(self):
        consumed = []
        tx = self.service.add(self.row())
        def stream():
            for i in range(10000):
                consumed.append(i)
                yield tx
        with patch("budget_app.storage.TransactionRepository.iter_all", side_effect=stream):
            code, _, _ = self.cli("list", "--limit", "3")
        self.assertEqual(code, 0)
        self.assertEqual(len(consumed), 3)

    def test_search_combines_all_filters(self):
        tx = self.service.add(self.row(memo="Lunch with team"))
        self.service.add(self.row(category="transport", amount="2000"))
        matches = list(self.service.search(start="2026-10-01", end="2026-10-31",
                      category="food", type_="expense", query="LUNCH", tag="work"))
        self.assertEqual([t.id for t in matches], [tx.id])
        self.assertEqual(list(self.service.search(tag="wor")), [])
        with self.assertRaises(AppError):
            list(self.service.search(start="2026-11-01", end="2026-10-01"))

    def test_summary_totals_top_and_budget_warning(self):
        self.service.add(self.row(type="income", category="salary", amount="100000"))
        self.service.add(self.row(amount="15000"))
        self.service.add(self.row(category="transport", amount="2000"))
        self.service.add(self.row(date="2026-11-01", amount="90000"))
        self.service.set_budget("2026-10", "10000")
        report = self.service.summary("2026-10")
        self.assertEqual((report["income"], report["expense"], report["balance"]), (100000, 17000, 83000))
        code, out, _ = self.cli("summary", "--month", "2026-10", "--top", "1")
        self.assertEqual(code, 0)
        self.assertIn("170.0%", out)
        self.assertIn("7,000원 초과", out)
        self.assertIn("1) food", out)
        self.assertNotIn("2) transport", out)

    def test_empty_month_with_budget_and_budget_show(self):
        self.service.set_budget("2026-01", "1000")
        code, out, _ = self.cli("summary", "--month", "2026-01")
        self.assertEqual(code, 0)
        self.assertIn("데이터 없음", out)
        self.assertIn("0.0%", out)
        self.assertIn("1,000원", self.cli("budget", "show", "--month", "2026-01")[1])
        self.assertNotEqual(self.cli("budget", "set", "--month", "2026-01", "--amount", "0")[0], 0)

    def test_category_management_and_in_use_protection(self):
        self.service.add_category("책")
        self.service.add(self.row(category="책"))
        with self.assertRaises(AppError):
            self.service.remove_category("책")
        self.service.add_category("unused")
        self.service.remove_category("unused")
        with self.assertRaises(AppError):
            self.service.add_category("food")

    def test_empty_categories_prevent_add(self):
        self.service.categories.save([])
        code, _, err = self.cli("add")
        self.assertNotEqual(code, 0)
        self.assertIn("category add", err)

    def test_update_reorders_and_delete_missing(self):
        first = self.service.add(self.row(date="2026-10-01"))
        other = self.service.add(self.row(date="2026-10-15"))
        self.service.update(first.id, {"date": "2026-10-31", "amount": "99", "memo": "", "tags": ""})
        rows = list(self.service.transactions.iter_all())
        self.assertEqual([t.id for t in rows], [first.id, other.id])
        self.assertEqual((rows[0].amount, rows[0].memo, rows[0].tags), (99, "", ()))
        self.service.delete(other.id)
        for action in (lambda: self.service.delete(other.id), lambda: self.service.update(other.id, {"amount": "1"})):
            with self.assertRaises(AppError):
                action()

    def test_invalid_update_preserves_original_bytes(self):
        tx = self.service.add(self.row())
        path = self.directory / "transactions.csv"
        original = path.read_bytes()
        with self.assertRaises(AppError):
            self.service.update(tx.id, {"amount": "0"})
        self.assertEqual(path.read_bytes(), original)

    def test_import_export_roundtrip_quoted_korean_and_bom(self):
        self.service.add(self.row())
        out = Path(self.temp.name) / "export.csv"
        self.assertEqual(self.service.export_csv(out, month="2026-10"), 1)
        # Excel 등에서 생성한 UTF-8 BOM 입력도 허용한다.
        out.write_bytes(b"\xef\xbb\xbf" + out.read_bytes())
        self.assertEqual(self.service.import_csv(out), 1)
        rows = list(self.service.transactions.iter_all())
        self.assertEqual(len({t.id for t in rows}), 2)
        self.assertEqual(rows[0].memo, "점심, 커피\n후식")
        self.assertEqual(rows[0].tags, ("meal", "work"))

    def test_import_only_required_columns(self):
        fields = ["date", "type", "category", "amount"]
        path = self.csv_input([{k: self.row()[k] for k in fields}], fields)
        self.assertEqual(self.service.import_csv(path), 1)
        self.assertEqual(next(self.service.transactions.iter_all()).tags, ())

    def test_large_import_external_sort_and_atomic_failure(self):
        path = self.csv_input([self.row(date=f"2026-10-{i % 31 + 1:02d}") for i in range(1100)])
        self.assertEqual(self.service.import_csv(path), 1100)
        dates = [tx.date for tx in self.service.transactions.iter_all()]
        self.assertEqual(dates, sorted(dates, reverse=True))
        original = (self.directory / "transactions.csv").read_bytes()
        path = self.csv_input([self.row() for _ in range(600)] + [self.row(amount="0")])
        with self.assertRaises(AppError):
            self.service.import_csv(path)
        self.assertEqual((self.directory / "transactions.csv").read_bytes(), original)
        self.assertFalse(list(self.directory.glob(".sort-*")))
        self.assertFalse(list(self.directory.glob(".write-*")))

    def test_import_bad_headers_missing_fields_and_unknown_categories(self):
        bad = Path(self.temp.name) / "bad.csv"
        for content in ("date,type\n", "date,date,type,category,amount\n",
                        "date,type,category,amount,extra\n",
                        "date,type,category,amount\n2026-10-01,expense,missing,1\n",
                        "date,type,category,amount\n2026-10-01,expense,food\n"):
            bad.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(AppError):
                self.service.import_csv(bad)

    def test_export_requires_filter_and_protects_storage(self):
        self.service.add(self.row())
        out = Path(self.temp.name) / "out.csv"
        self.assertNotEqual(self.cli("export", "--out", str(out))[0], 0)
        for name in ("transactions.csv", "categories.csv", "budgets.csv"):
            path = self.directory / name
            before = path.read_bytes()
            with self.assertRaises(AppError):
                self.service.export_csv(path, month="2026-10")
            self.assertEqual(path.read_bytes(), before)

    def test_export_validation_error_preserves_existing_output(self):
        out = Path(self.temp.name) / "out.csv"
        out.write_bytes(b"original")
        with self.assertRaises(AppError):
            self.service.export_csv(out, start="2026-12-01", end="2026-01-01")
        self.assertEqual(out.read_bytes(), b"original")

    def test_failed_replace_keeps_original(self):
        self.service.add(self.row())
        path = self.directory / "transactions.csv"
        before = path.read_bytes()
        with patch("budget_app.storage.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.service.add(self.row(amount="1"))
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(self.directory.glob(".write-*")))

    def test_lock_prevents_parallel_commands_and_cleans_up(self):
        with data_lock(self.directory):
            code, _, err = self.cli("list")
            self.assertEqual(code, 1)
            self.assertIn("다른 작업", err)
        self.assertFalse((self.directory / ".budget.lock").exists())

    def test_backup_contains_three_files(self):
        out = Path(self.temp.name) / "backups"
        self.assertEqual(self.cli("backup", "--out-dir", str(out))[0], 0)
        with ZipFile(next(out.glob("*.zip"))) as archive:
            self.assertEqual(set(archive.namelist()), {"transactions.csv", "categories.csv", "budgets.csv"})

    def test_real_process_errors_and_help(self):
        project = Path(__file__).resolve().parents[1]
        error = subprocess.run([sys.executable, "-m", "budget_app", "--data-dir", str(self.directory),
                                "delete", "--id", "missing"], cwd=project, capture_output=True, text=True)
        self.assertNotEqual(error.returncode, 0)
        self.assertNotIn("Traceback", error.stderr)
        for command in ([], ["add"], ["list"], ["search"], ["summary"], ["update"], ["delete"],
                        ["import"], ["export"], ["budget"], ["budget", "set"], ["budget", "show"],
                        ["category"], ["category", "add"], ["category", "list"], ["category", "remove"], ["backup"]):
            result = subprocess.run([sys.executable, "-m", "budget_app", *command, "--help"],
                                    cwd=project, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
