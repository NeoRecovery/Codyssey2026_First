# 나만의 용돈 기입장

첨부 과제의 필수 요구사항을 구현한 **터미널용 파이썬 프로그램**입니다.
Python 3.10 이상에서 작동하며 표준 라이브러리만 사용합니다. `pip install`은 필요하지 않습니다.

## 1. 바로 실행하기

ZIP을 풀고 VS Code에서 `allowance_project` 폴더를 엽니다.
터미널의 현재 위치도 `budget_app` 폴더가 들어 있는 `allowance_project`여야 합니다.

```bash
python --version
python -m budget_app --help
python -m budget_app add
python -m budget_app list --limit 5
```

Windows에서 `python` 명령을 찾지 못하면 `py -3`으로 바꾸세요.
macOS/Linux에서는 `python3`으로 바꿔 실행할 수 있습니다.
프로그램은 명령 하나를 실행하면 종료됩니다. 다음 작업은 터미널에서 다시 명령을 실행합니다.

`add`는 날짜 → 타입 → 카테고리 → 금액 → 메모 → 태그를 차례로 묻습니다.
날짜는 엔터를 누르면 오늘 날짜가 됩니다. 금액은 `15000`처럼 쉼표 없는 양수 정수(원)를 입력하세요.
잘못된 날짜·타입·카테고리·금액은 재입력을 요청합니다.

## 2. 예제 데이터로 확인하기

아래 명령은 연습용 저장 폴더 `demo_data`를 사용합니다.

```bash
python -m budget_app --data-dir ./demo_data import --from examples/sample.csv
python -m budget_app --data-dir ./demo_data list --limit 5
python -m budget_app --data-dir ./demo_data budget set --month 2026-10 --amount 100000
python -m budget_app --data-dir ./demo_data summary --month 2026-10 --top 3
```

예제의 10월 합계는 수입 **3,000,000원**, 지출 **167,000원**, 잔액 **2,833,000원**입니다.
예산 사용률 **167.0%**, 예산 초과 **67,000원**이 출력됩니다.
새 저장 폴더에서 한 번 가져온 경우의 결과입니다. 같은 CSV를 다시 가져오면 거래가 추가됩니다.

## 3. 주요 명령

모든 명령과 하위 명령에서 `--help`로 사용법을 볼 수 있습니다.
아래 예시는 기본 저장 폴더 `./data`를 사용합니다.

### 거래 추가와 조회

```bash
python -m budget_app add
python -m budget_app list
python -m budget_app list --limit 10
```

기본 조회 건수는 20건입니다. 최신순은 **거래일 내림차순**입니다.
같은 날짜 안에서는 ID 내림차순으로 순서를 고정합니다. 입력 시간순은 아닙니다.
ID는 `TX-`와 UUID로 구성되며, 저장 후 화면에 표시됩니다.

### 조건 검색

```bash
python -m budget_app search --from 2026-10-01 --to 2026-10-31
python -m budget_app search --category food --type expense
python -m budget_app search --q 점심 --tag meal
```

여러 조건은 AND로 결합됩니다. 시작일과 종료일은 해당 날짜를 포함합니다.
카테고리·태그는 정확히 일치해야 하며, 메모는 대소문자를 무시한 부분 검색입니다.
태그 `meal`과 `meals`는 서로 다릅니다. 결과가 없으면 `데이터 없음`이 표시됩니다.

### 거래 수정과 삭제

수정은 **옵션 방식**으로 고정했습니다. `ID`를 `list`에서 확인한 실제 ID로 바꾸세요.

```bash
python -m budget_app update --id ID --amount 12000 --memo "점심 수정"
python -m budget_app update --id ID --date 2026-10-30 --category transport
python -m budget_app update --id ID --tags "meal,work"
python -m budget_app update --id ID --memo "" --tags ""
python -m budget_app delete --id ID
```

지정한 필드만 수정하며 ID는 유지합니다. 날짜를 수정하면 저장 순서도 다시 맞춥니다.
메모와 태그는 빈 문자열로 지울 수 있습니다. ID가 없거나 수정값이 잘못되면 오류로 종료합니다.
삭제는 명령을 실행하면 즉시 적용됩니다. 필요하면 먼저 `backup`을 실행하세요.

### 월별 요약과 예산

```bash
python -m budget_app budget set --month 2026-10 --amount 500000
python -m budget_app budget show --month 2026-10
python -m budget_app summary --month 2026-10 --top 3
```

잔액은 해당 월의 수입 - 지출입니다. 이전 달 잔액을 이월하지 않습니다.
카테고리 TOP은 지출만 합산하며, 동률이면 카테고리명 순입니다.
예산 사용률은 지출 / 예산 × 100이고, 지출이 예산보다 클 때 초과 경고를 표시합니다.
예산은 양수 정수만 허용합니다. 같은 월의 예산을 다시 설정하면 새 금액으로 바뀝니다.
데이터가 없는 월도 0원 요약과 설정된 예산을 보여줍니다.

### 카테고리 관리

```bash
python -m budget_app category list
python -m budget_app category add
python -m budget_app category remove
```

추가/삭제는 카테고리명을 대화형으로 입력합니다.
초기 카테고리는 `food`, `transport`, `rent`, `salary`, `etc`입니다.
`책`, `생활비`처럼 한글 카테고리도 등록할 수 있습니다. 수입/지출 공통 목록입니다.
중복 등록과 사용 중인 카테고리 삭제는 막습니다. 삭제하려면 관련 거래를 먼저 수정/삭제하세요.
카테고리를 모두 지운 상태에서는 새 카테고리를 등록해야 거래를 추가할 수 있습니다.

### CSV 가져오기와 내보내기

```bash
python -m budget_app import --from examples/sample.csv
python -m budget_app export --out export.csv --month 2026-10
python -m budget_app export --out export.csv --from 2026-10-01 --to 2026-10-15
```

내보내기는 `--month` 또는 `--from`/`--to` 중 하나 이상이 필수입니다.
`--from`만 지정하면 그 날짜 이후, `--to`만 지정하면 그 날짜 이전을 내보냅니다.
월과 기간을 함께 지정하면 교집합을 내보냅니다. 내보내기 경로의 부모 폴더는 미리 생성하세요.
결과가 없어도 헤더가 있는 CSV가 만들어집니다. 같은 출력 파일은 덮어씁니다.

**교환용 CSV 스키마**

| 열 | 필수 | 형식 |
| --- | --- | --- |
| date | 예 | YYYY-MM-DD, 실제 존재하는 날짜 |
| type | 예 | income 또는 expense |
| category | 예 | 사전에 등록한 카테고리 |
| amount | 예 | 원 단위 양수 정수, 쉼표 없음 |
| memo | 아니요 | 문자열, 생략/빈 값 허용 |
| tags | 아니요 | 쉼표로 구분한 태그 문자열, 생략/빈 값 허용 |

```csv
date,type,category,amount,memo,tags
2026-10-01,income,salary,3000000,월급,salary
2026-10-15,expense,food,15000,"점심, 커피","meal,work"
```

헤더가 필수이며 UTF-8 또는 UTF-8 BOM 파일을 읽습니다. 내보내기는 UTF-8입니다.
쉼표·큰따옴표·줄바꿈이 있는 메모는 `csv` 표준 규칙으로 처리합니다.
Excel에서 한글이 깨지면 데이터 가져오기에서 UTF-8 인코딩을 선택하세요.
금액 셀은 `15,000`이나 `15000.0`이 아닌 `15000`으로 저장하세요.

가져오기는 **모든 행을 검증한 뒤 한 번에 반영**합니다. 오류가 있으면 파일 전체를 취소합니다.
이 경우 기존 거래는 바뀌지 않고 종료 코드 1을 반환합니다. 오류 원인을 고친 뒤 다시 실행하세요.
성공 시 `imported=N, skipped=0`을 표시합니다. 자동 건너뛰기는 하지 않습니다.
모든 행에 새 ID를 부여하므로, 같은 파일을 반복해서 가져오면 중복 거래가 생깁니다.
교환 CSV는 ID 열을 포함하지 않습니다. 등록되지 않은 카테고리는 자동 생성하지 않습니다.

### 백업 (선택 기능)

```bash
python -m budget_app backup
python -m budget_app backup --out-dir ./my_backups
```

기본 `./backups`에 날짜·시간과 식별자가 포함된 ZIP이 생깁니다.
복구할 때는 실행 중인 프로그램을 모두 종료하고 ZIP의 CSV 3개를 저장 폴더에 덮어쓰세요.
복구 전 현재 저장 폴더도 별도로 복사해 두면 되돌릴 수 있습니다.

## 4. 저장 위치와 파일 형식

기본 위치는 **명령을 실행한 현재 폴더 아래의 `./data`**입니다.
처음 실행하면 다음 CSV 3개를 자동 생성합니다. 프로그램 종료 후에도 남습니다.

| 파일 | 헤더 | 역할 |
| --- | --- | --- |
| transactions.csv | id,date,type,category,amount,memo,tags | 모든 거래, 거래일/ID 내림차순 |
| categories.csv | name | 등록 카테고리 목록 |
| budgets.csv | month,amount | 월별 예산 |

예산 파일의 `month` 형식은 `YYYY-MM`입니다. 모두 UTF-8, 헤더 포함 CSV입니다.
저장 폴더는 아래처럼 바꿀 수 있습니다. 서로 다른 폴더는 서로 독립된 기입장입니다.

```bash
python -m budget_app --data-dir ./my_data list
python -m budget_app list --data-dir ./my_data
```

하위 명령을 사용하는 경우 `--data-dir`은 맨 앞에 쓰면 확실합니다.
예: `python -m budget_app --data-dir ./my_data category list`

거래 저장 파일은 내부 정렬 규칙이 있으므로 직접 편집하지 마세요.
외부 자료는 별도 CSV로 만들어 `import`로 등록하세요. 저장 파일 자체를 import/export 경로로 지정하면 거부합니다.

## 5. 구조와 학습 포인트

```text
allowance_project/
  budget_app/
    __init__.py       패키지 표시
    __main__.py       python -m budget_app 진입점
    cli.py            명령 정의, 대화형 입력, 화면 출력
    models.py         dataclass Transaction, 날짜/타입/금액 검증
    storage.py        CSV 저장소, yield 조회, 원자적 파일 교체, 외부 정렬
    service.py        CRUD, 검색, 요약, 예산/카테고리 업무 규칙
    decorators.py     공통 예외 처리 데코레이터
  examples/
    sample.csv        실행해 볼 수 있는 예제 거래
  tests/
    test_budget_app.py
  README.md
  .gitignore
```

`Transaction`은 한 거래의 데이터 계약을 나타내는 불변 dataclass입니다.
`TransactionRepository`, `CategoryStore`, `BudgetStore`는 파일 입출력을 담당합니다.
`BudgetService`는 업무 규칙을 처리하고, CLI는 입력과 출력에 집중합니다.
공개 함수에는 타입 힌트를 적용했습니다.

`iter_all()`과 `search()`는 `yield`로 한 건씩 반환합니다.
파일 자체를 최신순으로 유지하므로 `list --limit N`은 N건을 읽고 멈출 수 있습니다.
검색·요약·내보내기도 거래 전체를 메모리 리스트로 만들지 않습니다.
요약은 카테고리별 합계만 메모리에 유지합니다. 카테고리/예산 목록은 작은 관리 데이터로 메모리에 읽습니다.

가져오기에서는 500건 단위로 정렬한 임시 CSV를 만들고 최대 32개씩 병합합니다.
거래가 많아도 입력 전체를 메모리에 올리지 않습니다.
추가·수정·삭제는 정렬된 거래 흐름을 임시 파일에 쓴 후 `os.replace()`로 교체합니다.
실패하면 임시 파일을 정리해 기존 파일을 보존합니다. 전원 손실까지 완전히 보장하는 DB 트랜잭션은 아닙니다.
파일 전체를 다시 쓰는 구조여서 잦은 대규모 수정 작업에는 DB 방식보다 느릴 수 있습니다.

`@handle_errors`는 CLI에 실제 적용한 예외 처리 데코레이터입니다.
예상 가능한 입력/파일 오류는 스택트레이스 대신 원인과 해결 힌트를 출력합니다.
정상 종료 코드는 0, 처리된 오류는 1, 명령 문법 오류는 argparse의 2, 입력 취소는 130입니다.
대화형 검증 오류는 재입력 후 정상 완료하면 0으로 끝납니다.

한 저장 폴더의 동시 실행은 `.budget.lock`으로 막아 덮어쓰기 충돌을 방지합니다.
강제 종료 후 잠금이 남으면 실행 중인 프로그램이 없는지 확인한 다음 해당 파일을 삭제하세요.
잠금은 앱 실행 간 충돌만 막습니다. 외부 프로그램에서 CSV를 동시에 편집하면 안 됩니다.

## 6. 요구사항 대응표

| PDF 필수 요구사항 | 구현 |
| --- | --- |
| 거래 추가, ID 출력, 대화형 검증 | add, cli.ask, Transaction.from_row |
| 최신순 목록, 기본 limit, 스트리밍 | list, TransactionRepository.iter_all |
| 날짜/카테고리/타입/메모/태그 검색 | search, BudgetService.search |
| 월 요약, 잔액, 지출 TOP, 빈 월 안내 | summary |
| 월 예산 영구 저장, 사용률/초과 경고 | budget set/show, summary |
| 카테고리 추가/조회/삭제, 사용 중 삭제 차단 | category add/list/remove |
| ID 기반 수정과 삭제, 없는 ID 처리 | update/delete |
| CSV 가져오기/내보내기, 처리 건수 | import/export |
| CSV 3개, 폴더 변경, 첫 실행 초기화 | storage.initialize, --data-dir |
| 클래스 2개 이상, dataclass, 모듈 3개 이상, 타입 힌트 | models/storage/service/cli 분리 |
| 제너레이터, 공통 데코레이터 실제 사용 | iter_all/search, @handle_errors |
| 표준 라이브러리만, Python 3.10 이상 | 외부 패키지 없음 |
| 오류 원인/힌트, 종료 코드, 도움말 | handle_errors, argparse |
| README 실행법/저장 형식/CSV 스키마 | 본 문서 |

선택 과제 중 백업과 원자적 교체를 구현했습니다. 반복 거래 자동 생성은 구현 범위에 포함하지 않았습니다.

## 7. 테스트

```bash
python -m unittest discover -s tests -v
```

22개 테스트는 임시 폴더를 사용하므로 실제 `data`를 변경하지 않습니다.
CRUD·검색·요약·예산·카테고리, CSV 한글/쉼표/줄바꿈/BOM,
1,100건 가져오기 정렬, 601번째 레코드 오류 시 전체 취소,
파일 교체 실패 시 원본 보존, 제한 조회 스트리밍, 잠금, 백업, 실제 프로세스 종료 코드와 도움말을 확인합니다.

Python 3.10에서 도입된 타입 표기만 사용하도록 작성했습니다.
전달 전 테스트는 제작 환경의 Python에서 실행했습니다. Windows에서 직접 실행한 결과는 포함하지 않습니다.
