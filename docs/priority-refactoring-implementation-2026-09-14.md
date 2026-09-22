# 우선순위 리팩토링 실행·DB 전환 계획

대상: 개발 소스의 R01~R04. 운영 서버 배포·운영 DB 변경은 포함하지 않는다.

## 유지할 규칙

검수 출고량은 사용자가 입력하고 남은 판매가능수량만 재고편입한다. 분할검수 저장 시 즉시 수불을 반영한다. 기존 실적 수정의 수불·동시성 보호, LOT 초과 허용, 미달 최종검수 사유, 기존재고 표의 두 열은 유지한다.

## R01: 부족종료 상태와 메모 분리

실행 코드 수정 전에 다음 전환 방식을 고정한다.

- `order_line.short_close_state`를 추가한다. `NONE`(일반), `CONFIRMED`(결정 확인), `REVIEW_REQUIRED`(과거 근거 확인 필요)만 허용하고 기본값은 `NONE`이다.
- 새 부족종료는 상태와 기존 변경이력(`SHORT_CLOSE`)에 결정자·시각·사유·잔여 출고량을 같은 트랜잭션으로 기록한다. 일반 메모에 특수 문자열을 추가하지 않는다.
- 처리계획의 `is_short_close`는 당시 계획의 기록으로 유지한다. 현재 종료 상태와 과거 계획 기록을 혼용하지 않는다.
- 기존 자료는 DONE이고 최신 확정 계획이 부족종료인 경우에만 `CONFIRMED`로 전환한다. DONE이고 기존 메모에 `[SHORT_CLOSE]`만 있는 자료는 `REVIEW_REQUIRED`로 보존한다. 메모만으로 승인 사실을 만들어내지 않는다.
- 확인 필요 자료는 자동 완료 재계산에서 보존하고 조회 응답으로 식별한다. 원인 자료·사용자 결정 없이 일괄 확정하지 않는다.
- 발주·LOT·검수·출고·재고 수량과 기존 메모·이력은 바꾸지 않는다.

### 적용·검증·복구

1. 합성 SQLite 자료로 메모 수정/문구 삽입, 종료 이력, 예약 해제 회귀 검증.
2. 운영과 분리된 로컬 PostgreSQL에서 이전 스키마 → 신규 migration → 상태별 전환, CHECK 제약, rollback 검증. DB 전용 검증은 전용 주소·계정·DB 이름을 확인한다.
3. 업무 DB 적용 전 복구 가능한 백업과 기존 migration head, 상태별 전환 예상 건수, 미확정 자료를 확인한다. DDL은 잠금 시간을 제한하고 하나의 트랜잭션에서 적용한다. 적용 실패 시 트랜잭션 rollback한다.
4. 새 `SHORT_CLOSE` 결정 이력이 존재하면 자동 downgrade를 거부한다. 새 결정이 없을 때만 추가 열/제약을 제거할 수 있다. 구버전 앱으로 복귀하면 메모 의존 버그가 다시 생기므로 앱과 스키마를 함께 검토한다.
5. 업무 DB에 아직 적용하지 않은 경우 완료 보고에 명시한다. 신규 모델을 이전 스키마에 연결하여 서비스하지 않는다.

## R02: 공통 오류 해석

문자열·배열·객체 응답에서 설명/필드/오류코드/상태코드/요청 ID를 보존한다. 서버의 입력 원문과 검증 context는 출력하지 않는다. 쓰기 요청의 시간 초과는 처리 결과를 확인하도록 안내한다. 합성 HTTP 응답으로 통신 없이 검증한다.

## R03: 버전 확인

실제 실행 WPF의 어셈블리 버전/빌드 식별자를 요청에 포함한다. 서버는 환경/빌드/지원 검수규칙 정보를 제공하고 요청 로그에 제한된 버전 정보를 남긴다. 검수 저장의 서버 규칙 검증을 유지하며 새 클라이언트도 로그인 전에 호환 정보를 확인한다. `MES_SERVER_BUILD_ID`가 없으면 서버 프로세스가 시작할 때의 실행 소스로 계산한 식별자를 사용한다. 소스를 읽을 수 없는 경우만 `unknown`이며 임의의 배포 버전을 만들지 않는다.

새 저장 계약은 헤더 `X-MES-Client-Contract: 1`과 본문 `quantity_rule_version: 2`다. 헤더가 없는 구버전, 지원 범위 밖 계약, 다른 수량 규칙은 수불 처리 전에 409로 거부한다. **구버전 WPF도 읽을 수 있도록 업데이트 안내는 문자열로 반환**하고, 오류코드는 별도 헤더로 보존한다. 버전 표시는 로그인 창 하단에, 자세한 WPF/서버 빌드는 도움말에 둔다. 검수 입력 화면의 항목은 늘리지 않았다.

## R04: 배포 검증

기존 검수 화면 회귀 검사와 공통 API 회귀 검사를 배포 검사에 포함한다. PostgreSQL 전용 검증이 생략된 상태를 배포 성공으로 처리하지 않는다. Windows PowerShell 검증의 모듈 경로는 자식 프로세스에만 설정하고 사용자/시스템 환경은 바꾸지 않는다.

## 실행 결과

R01~R04 개발 소스와 개발 DB 반영을 완료했다. 운영 배포·운영 데이터 변경은 수행하지 않았다. 기존 출고 자동배분을 다시 도입하지 않았으며, 일반 메모의 특수 문자열을 읽던 완료 판단과 문자열만 읽던 이전 오류 해석 코드는 제거했다. 과거 자료를 판별하는 문자열은 migration에만 남긴다.

### 검증

| 검증 | 결과 |
|---|---|
| 전체 백엔드, 전용 PostgreSQL 포함 | **357 통과 / 1 환경상 생략 / 세부 검사 35 통과** |
| 분리된 PostgreSQL 검수·재고·동시성·migration | 21 통과. 전체 검사에도 포함 |
| 기존 검수 화면 로직 | 23 통과: 수동 출고, 1차 재고편입→2차 사용, 계획 초과/미달, 실적 수정 등 |
| 공통 API·버전 | 34 통과: 입력 오류 필드, 요청 ID, 민감 입력 제외, 문자열/배열/객체 오류, 시간 초과, 실행본 헤더·호환성 |
| WPF 전체 Debug / Release | 빌드 성공, Debug 경고 0 / 오류 0. 내부·외주 Release 산출물 검사 성공 |
| DB head / 모델 일치 | `6b7c8d9e0f1a`, `alembic current --check-heads` 및 `alembic check` 성공 |
| 개발 서버 읽기 확인 | `/api/v1/runtime-info`에서 Development와 새 계약 확인, `/health` ok, `/ready` ready |
| 문서/변경 형식 | SVG XML 파싱 및 `git diff --check` 성공 |

재현 검사를 먼저 실행하여 구코드의 필드 오류 안내 누락과 메모 기반 완료 판단 실패를 확인했다. 전체 검사 중 발생한 Windows 자식 PowerShell 환경 문제는 자식 프로세스에만 적용하는 환경 보정으로 수정했고, 최종 전체 검사에서 통과했다.

실제 `Test-MesRelease.ps1`도 실행했다. 백엔드, 필수 PostgreSQL 검사, WPF 두 회귀 프로그램, Release 빌드·산출물, Alembic 검사는 모두 OK다. **최종 배포 검사 등급은 WARNING**이다. 이유는 현재 작업 내용이 아직 커밋되지 않았고 `-SkipDotnetRestore`로 패키지 재복원을 생략했기 때문이다. 배포 승인 결과로 해석하면 안 된다.

최종 보고서 위치:

`C:\Users\jaewon\Documents\Codex\mes-v1.5-db-safety\priority-refactor-20260914T012903Z\release-validation\20260914T013308Z-ae892e8a-25780\release-validation.json`

### 개발 DB 백업·적용

- 적용 전 head: `5a6b7c8d9e0f` → 적용 후: `6b7c8d9e0f1a`.
- 백업: `C:\Users\jaewon\Documents\Codex\mes-v1.5-db-safety\priority-refactor-20260914T012903Z\development-before.dump`.
- SHA-256: `6290919238f5c245c83980a2892cffcf31317aa22cff49dac87e0ab98eb4c0f7`.
- 별도의 로컬 임시 DB에 실제 복원한 뒤 migration과 모델 검사를 먼저 통과시켰다. 테스트가 만든 임시 DB만 제거했다.
- 개발 적용 전후 발주, LOT, 검수 일정·실적, 품목/LOT 재고, 수불, 출고, 계획이력, 발주 변경이력, 검수 정정이력 **11개 테이블의 기존 필드 전체 행 수·내용 해시가 같았다**. 새 상태 열만 비교에서 제외했다.
- 발주 622건 중 `CONFIRMED` 3건, `NONE` 619건, `REVIEW_REQUIRED` 0건. 3건은 기존의 최신 확정 부족종료 계획으로 확인된 자료다.
- 백업·전환 증빙은 동일 폴더의 `before.json`, `rehearsal.json`, `after.json`, `result.json`에 있다.
- 검증용 PostgreSQL 55439 인스턴스는 작업 후 원래의 중지 상태로 돌렸다. 개발 업무 DB 5432는 유지했다.

### 변경 파일

아래는 이번 우선순위 작업의 파일이다. 이전 검수 수정에서 남아 있던 파일·캐시·배포 설정은 별도로 되돌리거나 정리하지 않았다.

| 구분 | 파일 |
|---|---|
| 부족종료 상태·저장 | `backend/app/models/order_line.py`, `order_line_change_log.py`; `backend/app/services/order_fulfillment_policy.py`, `order_line_short_close_service.py`, `order_line_plan_service.py`, `order_line_change_history_service.py`, `order_line_change_timeline.py` |
| 부족종료 조회·계약 | `backend/app/services/order_line_list_query.py`, `order_line_response_builder.py`; `backend/app/schemas/order_line.py`; `backend/app/api/v1/order_lines.py` |
| DB 전환 | `backend/migrations/versions/6b7c8d9e0f1a_separate_short_close_decision.py` |
| 서버 실행본·호환 확인 | `backend/app/core/runtime_contract.py`, `config.py`, `observability.py`; `backend/app/main.py`; `backend/app/api/v1/endpoints/health.py`, `inspection_results.py` |
| 서버 검사 | `backend/tests/test_order_line_services.py`, `test_inspection_corrections.py`, `test_inspection_result_service.py`, `test_short_close_migration.py`, `test_runtime_contract.py` |
| 배포 검사 | `deploy/windows/Test-MesRelease.ps1`; `backend/scripts/inspection_regression_gate.py`; `backend/tests/test_inspection_regression_gate.py`, `windows_test_support.py`, `test_windows_deployment_scripts.py`, `test_windows_release_installation.py` |
| WPF 공통 | 아래 WPF 루트의 `Core/Models/ApiResult.cs`, `ApiError.cs`, `ApiRuntimeInfo.cs`; `Core/Configuration/ClientRuntime.cs`; `Core/Constants/ApiRoutes.cs`; `Infrastructure/Api/ApiClient.cs`, `ApiErrorParser.cs` |
| WPF 화면 연결 | 아래 WPF 루트의 `Modules/Auth/ViewModels/LoginViewModel.cs`, `Modules/Auth/Views/LoginWindow.xaml`, `Modules/InspectionSchedules/Dtos/InspectionResultDtos.cs`, `Modules/OrderLineList/Dtos/OrderLineListItemDto.cs` |
| WPF 검사 | `frontend-wpf/tests/ApiRegression/ApiRegression.csproj`, `Program.cs`; `frontend-wpf/tests/InspectionRegression/InspectionRegression.csproj` |
| 문서 | 이 문서, `docs/project-operations.md`, `docs/database-architecture.md`, `docs/database-schema.svg` |

WPF 루트: `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/`.

로컬 검증 보조 자료는 `.tmp/priority-refactor-20260914/`에 있다. 의존성은 추가하지 않았다.

### 미실행 검증·남은 위험·수동 확인

- 심볼릭 링크 생성 권한이 없는 환경이어서 기존 `test_linked_file_is_rejected` 1개가 생략됐다. PostgreSQL 필수 검사는 생략되지 않았다.
- 패키지 신규 복원, ClickOnce 게시·설치, 운영 서버 연결·배포는 수행하지 않았다. 운영 반영 시 쓰기를 중단한 유지보수 시간에 백업 → schema → 서버 → WPF 업데이트 및 확인 후 쓰기를 재개한다. 전환 도중 구서버가 메모 방식으로 새 부족종료를 기록하지 않도록 버전을 섞어 운영하지 않는다. 실제 운영의 전환 예상 건수와 복구 계획은 적용 전에 다시 확인해야 한다.
- 실제 화면의 마우스·키보드 조작과 실제 로그인/업무 저장은 수동 확인이 남았다. 개발 서버의 읽기 확인과 합성 API/화면 로직 검사는 완료했다.
- **새 개발 실행본으로 로그인 → 1차 분할검수에서 출고 0으로 저장 → 2차 기존재고 표시/수동 출고 → 기존 실적 수정**을 확인한다. 부족종료 후 메모 수정에서도 종료가 유지되는지 확인한다. 기존에 켜둔 구버전 WPF는 새 서버의 검수 저장 조건을 충족하지 못하므로 새 실행본으로 다시 열어야 한다.
- 이후 P2의 검수 저장 서비스 분리, 대형 화면 분리, 재고 조회 개선, DB 수량 제약 보강은 이번 범위에 포함하지 않았다. 기존 운영/백업에서 확인했던 수량 불일치도 임의 보정하지 않았다.
