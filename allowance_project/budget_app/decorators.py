"""CLI 공통 예외 처리를 업무 코드에서 분리한다."""
import csv
from functools import wraps
import sys
from typing import Callable, ParamSpec

from .models import AppError

P = ParamSpec("P")


def handle_errors(func: Callable[P, int]) -> Callable[P, int]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            return func(*args, **kwargs)
        except (AppError, OSError, UnicodeError, csv.Error, ValueError, KeyError) as error:
            print(f"[오류] {error}", file=sys.stderr)
            print("[힌트] 입력값·CSV 헤더·파일 권한을 확인하고 --help를 참고하세요.", file=sys.stderr)
            return 1
        except (EOFError, KeyboardInterrupt):
            print("\n[취소] 입력이 중단되었습니다. 작업을 다시 실행하세요.", file=sys.stderr)
            return 130
    return wrapper
