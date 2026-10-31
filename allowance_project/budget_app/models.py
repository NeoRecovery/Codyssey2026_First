"""데이터 계약과 입력 검증. 금액은 원 단위 양수 정수만 허용한다."""
from dataclasses import dataclass, field
from datetime import date as Date
import re
from uuid import uuid4


class AppError(Exception):
    """사용자에게 원인과 해결 방법을 표시할 수 있는 오류."""


def valid_date(value: str) -> str:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError
        Date.fromisoformat(value)
    except ValueError:
        raise AppError("날짜가 올바르지 않습니다. YYYY-MM-DD 예: 2026-10-31") from None
    return value


def valid_month(value: str) -> str:
    valid_date(value + "-01")
    return value


def positive_int(value: str | int) -> int:
    if not re.fullmatch(r"[0-9]+", str(value)) or int(value) <= 0:
        raise AppError("금액/개수는 0보다 큰 정수여야 합니다. 예: 15000")
    return int(value)


def valid_type(value: str) -> str:
    if value not in {"income", "expense"}:
        raise AppError("타입은 income(수입) 또는 expense(지출)을 입력하세요.")
    return value


def nonempty(value: str) -> str:
    value = value.strip()
    if not value or any(c in value for c in "\r\n\x00"):
        raise AppError("이름은 비어 있거나 줄바꿈/널 문자를 포함할 수 없습니다.")
    return value


def parse_tags(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(s.strip() for s in value.split(",") if s.strip()))


@dataclass(frozen=True)
class Transaction:
    id: str
    date: str
    type: str
    category: str
    amount: int
    memo: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_row(cls, row: dict[str, str], *, new_id: bool = False) -> "Transaction":
        return cls(
            id="TX-" + uuid4().hex if new_id else nonempty(row["id"]),
            date=valid_date(row["date"]), type=valid_type(row["type"]),
            category=nonempty(row["category"]), amount=positive_int(row["amount"]),
            memo=row.get("memo", "") or "", tags=parse_tags(row.get("tags", "") or ""),
        )

    def to_row(self) -> dict[str, str]:
        return {"id": self.id, "date": self.date, "type": self.type,
                "category": self.category, "amount": str(self.amount),
                "memo": self.memo, "tags": ",".join(self.tags)}


def order_key(tx: Transaction) -> tuple[str, str]:
    # 거래일 내림차순. 같은 날짜 안에서는 ID 내림차순으로 순서를 고정한다.
    return tx.date, tx.id
