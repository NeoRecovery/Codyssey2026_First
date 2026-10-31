"""거래 규칙과 요약. 화면 출력/사용자 입력은 CLI의 책임이다."""
from collections import defaultdict
from itertools import chain
from pathlib import Path
from typing import Iterator

from .models import (AppError, Transaction, nonempty, order_key, positive_int,
                     valid_date, valid_month)
from .storage import (BudgetStore, CategoryStore, CSV_FIELDS, TransactionRepository,
                      atomic_csv, read_csv, sorted_transactions)


class BudgetService:
    def __init__(self, directory: Path):
        self.directory = directory
        self.transactions = TransactionRepository(directory / "transactions.csv")
        self.categories = CategoryStore(directory / "categories.csv")
        self.budgets = BudgetStore(directory / "budgets.csv")

    def require_category(self, category: str) -> str:
        category = nonempty(category)
        if category not in self.categories.load():
            raise AppError(f"등록되지 않은 카테고리: {category}. category add로 먼저 등록하세요.")
        return category

    def add(self, row: dict[str, str]) -> Transaction:
        tx = Transaction.from_row(row, new_id=True)
        self.require_category(tx.category)
        self.transactions.merge([tx])
        return tx

    def get(self, identifier: str) -> Transaction:
        stream = self.transactions.iter_all()
        try:
            for tx in stream:
                if tx.id == identifier:
                    return tx
        finally:
            stream.close()
        raise AppError(f"없는 데이터: {identifier}. list로 ID를 확인하세요.")

    def update(self, identifier: str, changes: dict[str, str]) -> None:
        current = self.get(identifier)
        row = current.to_row()
        row.update(changes)
        updated = Transaction.from_row(row)
        self.require_category(updated.category)
        # 날짜가 바뀌어도 정렬을 유지한다. 기존 데이터 전체를 메모리에 올리지 않는다.
        import heapq
        others = (tx for tx in self.transactions.iter_all() if tx.id != identifier)
        self.transactions.replace(heapq.merge(others, [updated], key=order_key, reverse=True))

    def delete(self, identifier: str) -> None:
        self.get(identifier)
        self.transactions.replace(tx for tx in self.transactions.iter_all() if tx.id != identifier)

    def search(self, *, start: str | None = None, end: str | None = None,
               category: str | None = None, type_: str | None = None,
               query: str | None = None, tag: str | None = None,
               month: str | None = None) -> Iterator[Transaction]:
        if start:
            valid_date(start)
        if end:
            valid_date(end)
        if start and end and start > end:
            raise AppError("시작일이 종료일보다 늦습니다. --from/--to를 확인하세요.")
        if month:
            valid_month(month)
        for tx in self.transactions.iter_all():
            if start and tx.date < start:
                continue
            if end and tx.date > end:
                continue
            if month and tx.date[:7] != month:
                continue
            if category and tx.category != category:
                continue
            if type_ and tx.type != type_:
                continue
            if query and query.casefold() not in tx.memo.casefold():
                continue
            if tag and tag not in tx.tags:
                continue
            yield tx

    def summary(self, month: str) -> dict:
        valid_month(month)
        income = expense = count = 0
        categories: dict[str, int] = defaultdict(int)
        for tx in self.search(month=month):
            count += 1
            if tx.type == "income":
                income += tx.amount
            else:
                expense += tx.amount
                categories[tx.category] += tx.amount
        return {"count": count, "income": income, "expense": expense,
                "balance": income - expense,
                "categories": sorted(categories.items(), key=lambda pair: (-pair[1], pair[0])),
                "budget": self.budgets.load().get(month)}

    def set_budget(self, month: str, amount: str) -> None:
        valid_month(month)
        budgets = self.budgets.load()
        budgets[month] = positive_int(amount)
        self.budgets.save(budgets)

    def add_category(self, name: str) -> None:
        name = nonempty(name)
        categories = self.categories.load()
        if name in categories:
            raise AppError(f"이미 등록된 카테고리: {name}")
        self.categories.save(chain(categories, [name]))

    def remove_category(self, name: str) -> None:
        name = self.require_category(name)
        stream = self.transactions.iter_all()
        try:
            if any(tx.category == name for tx in stream):
                raise AppError("사용 중인 카테고리는 삭제할 수 없습니다. 거래를 먼저 수정/삭제하세요.")
        finally:
            stream.close()
        self.categories.save(n for n in self.categories.load() if n != name)

    def check_external_path(self, path: Path) -> None:
        if path.resolve() in {(self.directory / name).resolve() for name in
                              ("transactions.csv", "categories.csv", "budgets.csv", ".budget.lock")}:
            raise AppError("저장 파일을 가져오기/내보내기 경로로 지정할 수 없습니다. 별도 CSV를 사용하세요.")

    def import_csv(self, path: Path) -> int:
        self.check_external_path(path)
        # 빈 CSV라도 헤더 오류를 놓치지 않는다.
        import csv
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            header = next(csv.reader(file, strict=True), [])
        if set(header) - set(CSV_FIELDS):
            raise AppError("지원하지 않는 CSV 열입니다. date,type,category,amount,memo,tags를 사용하세요.")
        categories = set(self.categories.load())
        count = 0

        def rows() -> Iterator[Transaction]:
            nonlocal count
            # memo/tags는 선택 열이다. id 등 스키마 밖 열은 거부해 오해를 방지한다.
            required = ["date", "type", "category", "amount"]
            for number, row in enumerate(read_csv(path, required, exact=False), start=2):
                if set(row) - set(CSV_FIELDS):
                    raise AppError("지원하지 않는 CSV 열입니다. date,type,category,amount,memo,tags를 사용하세요.")
                try:
                    tx = Transaction.from_row(row, new_id=True)
                    if tx.category not in categories:
                        raise AppError(f"등록되지 않은 카테고리: {tx.category}. category add로 등록하세요.")
                except AppError as error:
                    raise AppError(f"CSV {number}번째 레코드: {error}") from None
                count += 1
                yield tx

        # 모든 입력을 검증/외부 정렬한 뒤 원자적으로 한 번만 교체한다.
        # 잘못된 행이 하나라도 있으면 전체 가져오기를 취소한다.
        ordered = sorted_transactions(rows(), self.directory)
        try:
            self.transactions.merge(ordered)
        finally:
            ordered.close()
        return count

    def export_csv(self, path: Path, **filters: str | None) -> int:
        self.check_external_path(path)
        def rows() -> Iterator[dict[str, str]]:
            for tx in self.search(**filters):
                row = tx.to_row()
                del row["id"]
                yield row
        return atomic_csv(path, CSV_FIELDS, rows())
