"""argparse 명령과 대화형 입력, 한국어 출력."""
import argparse
from decimal import Decimal
from datetime import date
from itertools import islice
from pathlib import Path
from typing import Callable, Iterable, TypeVar
from zipfile import ZipFile, ZIP_DEFLATED

from .decorators import handle_errors
from .models import (AppError, Transaction, nonempty, positive_int, valid_date, valid_type)
from .service import BudgetService
from .storage import data_lock, initialize

T = TypeVar("T")


def ask(prompt: str, validator: Callable[[str], T], default: str | None = None) -> T:
    while True:
        raw = input(prompt).strip()
        if not raw and default is not None:
            raw = default
        try:
            return validator(raw)
        except AppError as error:
            print(f"[오류] {error}")


def table(transactions: Iterable[Transaction]) -> int:
    count = 0
    for tx in transactions:
        if not count:
            print("ID | 날짜 | 타입 | 카테고리 | 금액(원) | 메모 | 태그")
        # 메모의 개행을 화면에서 이스케이프해 한 거래가 한 줄로 보이게 한다.
        memo = tx.memo.replace("\r", "\\r").replace("\n", "\\n")
        print(f"{tx.id} | {tx.date} | {tx.type} | {tx.category} | {tx.amount:,} | {memo} | {','.join(tx.tags)}")
        count += 1
    print(f"[조회] {count}건" if count else "데이터 없음")
    return count


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="나만의 용돈 기입장 (Python 3.10+, 표준 라이브러리)")
    root.add_argument("--data-dir", default="./data", help="저장 폴더 (기본: 현재 폴더/data)")
    commands = root.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text, description=help_text)
        # 전역 옵션은 명령 앞/뒤 어디에 적어도 적용된다.
        sub.add_argument("--data-dir", default=argparse.SUPPRESS, help="저장 폴더")
        return sub

    command("add", "대화형으로 거래 추가")
    listing = command("list", "최신 거래 조회 (거래일 내림차순)")
    listing.add_argument("--limit", type=positive_int, default=20, help="최대 건수 (기본 20)")
    search = command("search", "조건에 맞는 거래 검색 (조건은 AND)")
    search.add_argument("--from", dest="start", help="시작일 YYYY-MM-DD, 포함")
    search.add_argument("--to", dest="end", help="종료일 YYYY-MM-DD, 포함")
    search.add_argument("--category", help="카테고리 정확히 일치")
    search.add_argument("--type", dest="type_", choices=["income", "expense"])
    search.add_argument("--q", dest="query", help="메모 부분 검색, 대소문자 무시")
    search.add_argument("--tag", help="태그 정확히 일치")
    summary = command("summary", "월별 수입·지출·잔액·카테고리 TOP·예산 사용률")
    summary.add_argument("--month", required=True, help="YYYY-MM")
    summary.add_argument("--top", type=positive_int, default=3)
    update = command("update", "옵션 방식으로 거래 수정 (메모/태그는 빈 문자열로 지울 수 있음)")
    update.add_argument("--id", required=True)
    for field in ("date", "type", "category", "amount", "memo", "tags"):
        update.add_argument("--" + field)
    delete = command("delete", "ID로 거래 삭제")
    delete.add_argument("--id", required=True)
    importing = command("import", "UTF-8 CSV 가져오기 (잘못된 행이 있으면 전체 취소)")
    importing.add_argument("--from", dest="source", required=True, type=Path)
    exporting = command("export", "기간 또는 월을 지정해 CSV 내보내기")
    exporting.add_argument("--out", required=True, type=Path)
    exporting.add_argument("--month", help="YYYY-MM")
    exporting.add_argument("--from", dest="start", help="YYYY-MM-DD")
    exporting.add_argument("--to", dest="end", help="YYYY-MM-DD")
    budget = command("budget", "월 예산 설정/조회")
    budget_sub = budget.add_subparsers(dest="action", required=True)
    for action in ("set", "show"):
        sub = budget_sub.add_parser(action, help="예산 저장" if action == "set" else "예산 조회")
        sub.add_argument("--month", required=True, help="YYYY-MM")
        if action == "set":
            sub.add_argument("--amount", required=True)
    category = command("category", "카테고리 추가/조회/삭제 (사용 중이면 삭제 금지)")
    category_sub = category.add_subparsers(dest="action", required=True)
    for action in ("add", "list", "remove"):
        category_sub.add_parser(action, help={"add": "대화형 추가", "list": "목록", "remove": "대화형 삭제"}[action])
    backup = command("backup", "타임스탬프가 포함된 ZIP 백업 생성 (선택 과제)")
    backup.add_argument("--out-dir", type=Path, default=Path("./backups"))
    return root


@handle_errors
def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    directory = Path(args.data_dir)
    with data_lock(directory):
        initialize(directory)
        service = BudgetService(directory)
        if args.command == "add":
            categories = service.categories.load()
            if not categories:
                raise AppError("카테고리가 비어 있습니다. category add로 먼저 등록하세요.")
            row = {"date": ask(f"날짜(YYYY-MM-DD, 엔터={date.today()}): ", valid_date, str(date.today())),
                   "type": ask("타입(income/expense): ", valid_type)}
            print("등록 카테고리: " + ", ".join(categories))
            row["category"] = ask("카테고리: ", service.require_category)
            row["amount"] = str(ask("금액(양수 정수, 원): ", positive_int))
            row["memo"] = input("메모(선택): ")
            row["tags"] = input("태그(쉼표 구분, 선택): ")
            tx = service.add(row)
            print(f"[저장 완료] id={tx.id}")
        elif args.command == "list":
            stream = service.transactions.iter_all()
            try:
                table(islice(stream, args.limit))
            finally:
                stream.close()
        elif args.command == "search":
            table(service.search(start=args.start, end=args.end, category=args.category,
                                 type_=args.type_, query=args.query, tag=args.tag))
        elif args.command == "update":
            changes = {key: getattr(args, key) for key in
                       ("date", "type", "category", "amount", "memo", "tags")
                       if getattr(args, key) is not None}
            if not changes:
                raise AppError("수정할 옵션이 없습니다. 예: update --id ID --amount 12000")
            service.update(args.id, changes)
            print(f"[수정 완료] id={args.id}")
        elif args.command == "delete":
            service.delete(args.id)
            print(f"[삭제 완료] id={args.id}")
        elif args.command == "summary":
            report = service.summary(args.month)
            print(f"[{args.month} 월별 요약]")
            if not report["count"]:
                print("데이터 없음")
            print(f"총 수입: {report['income']:,}원\n총 지출: {report['expense']:,}원\n잔액: {report['balance']:,}원")
            budget = report["budget"]
            if budget is None:
                print("예산 미설정")
            else:
                usage = Decimal(report["expense"]) * 100 / Decimal(budget)
                print(f"예산: {budget:,}원 (사용률 {usage:.1f}%)")
                if report["expense"] > budget:
                    print(f"[경고] 예산을 {report['expense'] - budget:,}원 초과했습니다.")
            print(f"카테고리별 지출 TOP {args.top}")
            for rank, (category, amount) in enumerate(report["categories"][:args.top], 1):
                print(f"{rank}) {category}: {amount:,}원")
        elif args.command == "budget":
            from .models import valid_month
            valid_month(args.month)
            if args.action == "set":
                service.set_budget(args.month, args.amount)
                print(f"[저장 완료] {args.month} 예산 {int(args.amount):,}원")
            else:
                amount = service.budgets.load().get(args.month)
                print("예산 미설정" if amount is None else f"{args.month} 예산 {amount:,}원")
        elif args.command == "category":
            if args.action == "list":
                names = service.categories.load()
                print("\n".join("- " + name for name in names) if names else "카테고리 없음: category add로 등록하세요.")
            else:
                name = ask("카테고리명: ", nonempty)
                if args.action == "add":
                    service.add_category(name)
                else:
                    service.remove_category(name)
                print(f"[{'저장' if args.action == 'add' else '삭제'} 완료] category={name}")
        elif args.command == "import":
            count = service.import_csv(args.source)
            print(f"[완료] imported={count}, skipped=0")
        elif args.command == "export":
            if not args.month and not args.start and not args.end:
                raise AppError("export에는 --month 또는 --from/--to 중 하나 이상을 지정하세요.")
            count = service.export_csv(args.out, month=args.month, start=args.start, end=args.end)
            print(f"[완료] {args.out} ({count} records)")
        elif args.command == "backup":
            from datetime import datetime
            from uuid import uuid4
            args.out_dir.mkdir(parents=True, exist_ok=True)
            output = args.out_dir / f"budget-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.zip"
            try:
                with ZipFile(output, "x", ZIP_DEFLATED) as archive:
                    for name in ("transactions.csv", "categories.csv", "budgets.csv"):
                        archive.write(directory / name, arcname=name)
            except BaseException:
                output.unlink(missing_ok=True)
                raise
            print(f"[백업 완료] {output}")
    return 0
