"""CSV 스트리밍 입출력, 원자적 교체, 제한 메모리 외부 정렬."""
from contextlib import contextmanager, ExitStack
import csv
import heapq
from itertools import islice
import os
from pathlib import Path
import tempfile
from typing import Iterable, Iterator

from .models import AppError, Transaction, order_key

FIELDS = ["id", "date", "type", "category", "amount", "memo", "tags"]
CSV_FIELDS = FIELDS[1:]
DEFAULT_CATEGORIES = ("food", "transport", "rent", "salary", "etc")


def read_csv(path: Path, fields: list[str], *, exact: bool = True) -> Iterator[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, strict=True)
        header = reader.fieldnames
        if (not header or len(header) != len(set(header))
                or not set(fields).issubset(header)
                or (exact and set(header) != set(fields))):
            raise AppError(f"{path.name}: CSV 헤더를 확인하세요. 필수 열: {', '.join(fields)}")
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise AppError(f"{path.name} {reader.line_num}행: CSV 열 수가 맞지 않습니다.")
            yield row


def atomic_csv(path: Path, fields: list[str], rows: Iterable[dict[str, str]]) -> int:
    """쓰기 실패/검증 오류가 발생하면 원본은 그대로 두고 임시 파일을 지운다."""
    handle, name = tempfile.mkstemp(prefix=".write-", suffix=".csv", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            count = 0
            for row in rows:
                writer.writerow(row)
                count += 1
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        return count
    finally:
        temporary.unlink(missing_ok=True)


class TransactionRepository:
    def __init__(self, path: Path):
        self.path = path

    def iter_all(self) -> Iterator[Transaction]:
        previous = None
        for row in read_csv(self.path, FIELDS):
            tx = Transaction.from_row(row)
            key = order_key(tx)
            if previous is not None and key >= previous:
                raise AppError("거래 파일 정렬 또는 ID가 올바르지 않습니다. 백업을 복구하세요.")
            previous = key
            yield tx

    def replace(self, rows: Iterable[Transaction]) -> int:
        return atomic_csv(self.path, FIELDS, (tx.to_row() for tx in rows))

    def merge(self, rows: Iterable[Transaction]) -> int:
        return self.replace(heapq.merge(self.iter_all(), rows, key=order_key, reverse=True))


def sorted_transactions(rows: Iterable[Transaction], directory: Path) -> Iterator[Transaction]:
    """500건 단위 정렬 후 최대 32개 파일씩 병합해 대량 import도 스트리밍한다."""
    with tempfile.TemporaryDirectory(prefix=".sort-", dir=directory) as name:
        root = Path(name)
        paths: list[Path] = []
        iterator = iter(rows)
        index = 0
        while chunk := list(islice(iterator, 500)):
            path = root / f"chunk-{index}.csv"
            chunk.sort(key=order_key, reverse=True)
            atomic_csv(path, FIELDS, (tx.to_row() for tx in chunk))
            paths.append(path)
            index += 1
        while len(paths) > 1:
            next_paths = []
            for offset in range(0, len(paths), 32):
                group = paths[offset:offset + 32]
                path = root / f"merge-{index}.csv"
                index += 1
                with ExitStack() as stack:
                    streams = [stack.enter_context(contextmanager_stream(p)) for p in group]
                    merged = heapq.merge(*streams, key=order_key, reverse=True)
                    atomic_csv(path, FIELDS, (tx.to_row() for tx in merged))
                next_paths.append(path)
                for old in group:
                    old.unlink()
            paths = next_paths
        if paths:
            yield from TransactionRepository(paths[0]).iter_all()


@contextmanager
def contextmanager_stream(path: Path) -> Iterator[Iterator[Transaction]]:
    stream = TransactionRepository(path).iter_all()
    try:
        yield stream
    finally:
        stream.close()


class CategoryStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[str]:
        return [row["name"] for row in read_csv(self.path, ["name"])]

    def save(self, names: Iterable[str]) -> None:
        atomic_csv(self.path, ["name"], ({"name": n} for n in names))


class BudgetStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, int]:
        from .models import valid_month, positive_int
        return {valid_month(r["month"]): positive_int(r["amount"])
                for r in read_csv(self.path, ["month", "amount"])}

    def save(self, budgets: dict[str, int]) -> None:
        atomic_csv(self.path, ["month", "amount"],
                   ({"month": m, "amount": str(a)} for m, a in sorted(budgets.items())))


@contextmanager
def data_lock(directory: Path) -> Iterator[None]:
    """동시 실행의 덮어쓰기를 방지한다. 비정상 강제 종료 시 잠금이 남을 수 있다."""
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".budget.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise AppError("다른 작업이 실행 중입니다. 종료 후 다시 시도하세요. "
                       "강제 종료했다면 실행 중인 프로그램이 없는지 확인한 뒤 .budget.lock을 삭제하세요.") from None
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def initialize(directory: Path) -> None:
    for name, fields, rows in (
        ("transactions.csv", FIELDS, []),
        ("categories.csv", ["name"], [{"name": n} for n in DEFAULT_CATEGORIES]),
        ("budgets.csv", ["month", "amount"], []),
    ):
        path = directory / name
        if not path.exists():
            atomic_csv(path, fields, rows)
