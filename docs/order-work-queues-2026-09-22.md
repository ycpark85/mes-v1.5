# 발주 대기목록과 현재 실적으로 완료 — 2026-09-22

## 업무 흐름

발주리스트의 `생산중` / `생산완료` 탭은 유지한다. 생산중 탭 아래에 `LOT 생성 대기 (건수)`, `종료판단대기 (건수)` 버튼을 둔다. 선택한 버튼을 다시 누르면 생산중 전체로 돌아간다. 숫자는 검색어나 현재 페이지와 무관한 전체 대기 발주 **라인 수**다. 두 대기목록을 합쳐도 일반 생산 진행 건까지 포함한 생산중 전체와 같지는 않다.

| 구분 | 포함 조건 | 목록에서 빠지는 시점 |
| --- | --- | --- |
| LOT 생성 대기 | 등록 당시 가용재고가 있어 자동 LOT 생성을 보류했고, 활성 OPEN 상태이며 LOT가 하나도 없는 발주 | 기본 LOT 생성 또는 재고만 출고하여 종료 |
| 종료판단대기 | 활성 CLOSED 상태, 취소되지 않은 LOT가 하나 이상 존재, 해당 LOT 모두 DONE, 각 LOT의 최종검수 실적이 정산 완료, 진행 중 검수 없음, 실제 누적출고가 출고목표 미만, 현재 종료결정 없음 | 현재 실적으로 완료, 재작업 LOT 생성, 또는 기존 출고 기능으로 부족 해소 |

- LOT 생성 대기에는 처리계획 미확정과 확정 후 기본 LOT 생성 전 상태가 모두 포함된다. 등록 때의 보류 이력을 사용하므로 다른 발주가 재고를 사용해도 목록에서 사라지지 않는다. 재고가 0이 되면 기존 `AUTO_PRODUCTION` 계획을 `전량 생산`으로 선택하여 확정하고 기본 LOT를 생성할 수 있다.
- 검수 미등록, 부분검수 진행, 후속 검수 진행, 재작업 진행, 모든 LOT 취소, 정산되지 않은 최종검수는 종료판단대기에 포함하지 않는다. 단순 LOT 상태만으로 최종검수 완료를 추정하지 않는다.
- 전량 미검수·출고 0으로 최종검수 정산을 마친 경우도 종료판단대기에 포함한다. 이번 변경으로 폐기 수량을 추가 생성하거나 검사·불량·미검수 수량을 바꾸지 않는다.
- 재고생산 계획의 출고목표는 기존 규칙대로 0이므로 출고부족 대기로 분류하지 않는다.

## 완료와 재개

1. 선택한 종료판단대기 **라인**에만 하단 `현재 실적으로 완료` 버튼을 활성화한다. 확인창에는 발주번호/라인, 출고목표, 실제 출고, 미출고를 표시한다. 확인은 한 번이며 사유 입력을 요구하지 않는다.
2. 서버가 최신 상태를 다시 검증하고 `DONE + CONFIRMED + manual_closed=true`를 한 트랜잭션으로 기록한다. 처리자, 시간, 당시 목표/실제출고/미출고와 이전 상태는 기존 변경 이력에 남는다. 같은 완료 요청의 재시도로 이력이 중복 생성되지 않는다.
3. 생산완료 탭에서는 `완료(수동)`으로 표시한다. 해당 라인에만 `완료 취소`가 가능하다. 취소 후 자동 완료 조건을 다시 계산하므로 현재 출고가 이미 목표를 충족했다면 일반 완료로 남을 수 있다.
4. 수동완료 또는 과거 부족종료 발주에 재작업 LOT를 만들면 현재 종료결정을 해제하고 생산중으로 재개한다. 과거 이력은 보존한다. 새 재작업 LOT가 최종검수·정산을 마친 후에도 출고가 부족하면 종료판단대기로 돌아온다.
5. 기존 일반 완료 발주의 재작업 생성은 유지한다. 취소된 발주는 재작업 생성 대상이 아니다.

발주 잠금 → 필요 시 품목 재고 잠금 순서를 사용하여 검수 정산과 완료/재작업을 직렬화한다. 재작업 LOT 번호 충돌 재시도는 저장점을 사용하므로 발주 잠금이나 종료결정을 중간에 잃지 않는다. WPF는 처리 중 다른 버튼·탭 변경과 중복 제출을 막으며, 화면에서 확인한 갱신시각/목표/출고가 달라졌으면 서버가 409로 재조회를 요청한다.

## 수량과 예약

- 미출고 = `max(확정 출고목표 - 실제 누적출고, 0)`. 실제 누적출고는 출고 재고수불의 부호를 포함한 합계다. LOT 계획수량과 누적 검사수량을 이 계산에 더하지 않는다.
- 기존의 최종검수 LOT 계획수량 미달 저장 허용, 미달사유 미요구, 출고목표 초과 저장 허용은 유지한다. 출고목표를 실제 출고에 맞춰 늘리거나 실제 출고를 목표에 맞춰 줄이지 않는다.
- 확정된 계획 생산수량·계획 재고사용은 저장된 최신 처리계획을 표시한다. 현재 가용재고가 달라졌다고 확정 계획수량을 다시 계산해 표시하지 않는다.
- 최종검수 정산은 기존대로 다른 진행 LOT가 없을 때 자기 발주의 남은 대기 예약을 해제한다. 수동완료는 남아 있는 자기 발주의 미사용 STOCK/WAITING 예약만 정리한다. 다른 발주의 예약이나 이미 출고된 내역은 변경하지 않는다.
- **예약 해제는 출고가 아니다.** 실제 재고, 검사실적, 수불은 그대로다. 완료 취소나 재작업 생성 때 과거 예약을 자동 복구하지 않는다.

## 목록 갱신

처리 성공 후 같은 화면에서 서버 목록과 전체 건수를 다시 조회한다. 대기조건에서 벗어난 행만 빠지고, 바뀌지 않은 행 객체·필터·페이지·스크롤을 유지한다. 처리한 선택 행이 빠지면 다음 행(마지막이면 이전 행)을 선택한다. 페이지의 마지막 행까지 없어지면 마지막 유효 페이지로 이동한다. 필요하면 다음 페이지의 행을 현재 페이지에 채운다.

실패한 쓰기는 목록을 변경하지 않는다. 쓰기가 성공했지만 후속 조회가 실패하면 기존 화면을 유지하고 갱신 실패를 알린다. 사용자는 `조회`로 상태를 확인한다. 이 갱신은 처리·상세창/재작업창 종료 후의 갱신이며 다른 PC의 변경을 계속 감시하는 주기적 자동갱신은 추가하지 않았다.

## API 계약

- `GET /api/v1/order-lines?work_queue=LOT_CREATION|CLOSE_DECISION`: 필터는 페이지 분할 전에 적용. 응답에 `queue_counts.lot_creation`, `queue_counts.close_decision`, 각 행에 `work_queue`, `lot_creation_deferred`, `manual_closed`, `planned_stock_ship_qty` 추가. 알 수 없는 필터는 422. 생산완료 전용 조회는 대기 건수를 계산하지 않고 `queue_counts: null`을 반환한다. 생산중 조회는 검색/페이지와 무관한 전체 건수를 항상 반환한다.
- `PATCH /api/v1/order-lines/{id}/manual-close`, `PATCH .../manual-reopen`: 로그인 사용자 필요. 기존 `short-close`도 동일한 엄격한 최종검수 조건을 거치는 호환 경로다.
- 완료 요청의 `expected_updated_at`, `expected_ship_target_qty`, `expected_shipped_qty`는 선택 필드로 기존 호출 호환성을 유지한다. 새 WPF는 세 값을 모두 보낸다. 사유는 필요하지 않다.
- LOT 생성 API는 로그인 사용자로 재개 이력을 남긴다.
- 이력의 `change_type=SHORT_CLOSE`를 재사용하고 `after_data.action=MANUAL_CLOSE|MANUAL_REOPEN|REWORK_REOPEN`으로 행동을 구분한다.

## DB 변경과 배포 순서

마이그레이션 `7c8d9e0f1a2b`는 `6b7c8d9e0f1a` 다음이다. `order_line`에 NOT NULL 기본값 false인 `lot_creation_deferred`, `manual_closed`를 추가한다. CHECK는 수동완료가 true이면 반드시 DONE/CONFIRMED임을 보장한다.

기존 데이터 중 활성 OPEN, 저장된 재고우선/혼합 방식, 재고만 종료 정책이 아님, LOT 없음인 경우에만 보류 이력을 보충한다. 저장된 처리방식으로 근거를 확인할 수 없는 과거 OPEN 건은 자동으로 보류 건이라 단정하지 않는다. 과거 완료를 새 수동완료로 재분류하지 않는다. 기존 수량·메모·상태·수불·이력은 수정하지 않는다.

서버 배포 시 API 정지 → 기존 복구 백업 1회 → migration upgrade → API 기동 및 목록 조회 → WPF 교체 순서로 진행한다. DDL 잠금 제한은 5초이며 잠금 실패 시 재시도 전에 접속 작업을 확인한다. 새 기록이 없을 때만 스키마 downgrade가 가능하다. 수동완료/재개 이력이 하나라도 있으면 파괴적인 downgrade를 거부하므로 이후 롤백은 이력을 유지하는 호환 수정으로 수행한다. 이 작업에서 서버컴퓨터 배포나 GitHub 업로드는 하지 않는다.

## 변경 파일

| 영역 | 파일 | 이유 |
| --- | --- | --- |
| DB/계약 | `backend/app/models/order_line.py`, `backend/app/schemas/order_line.py`, `backend/migrations/versions/7c8d9e0f1a2b_order_work_queues.py` | 보류 기원, 수동완료, 목록 필터/건수 및 완료 요청 계약 |
| 분류/조회 | `backend/app/services/order_line_work_queue.py`, `order_line_list_query.py`, `ship_qty_policy.py` | 목록·전체 건수·완료 가능 여부가 같은 조건 사용, 기존 출고목표 계산과 SQL 필터 일치 |
| 처리 | `backend/app/services/order_line_manual_close_service.py`, `order_line_creation_service.py`, `order_line_base_lot_service.py`, `lot_rework_service.py`, `order_line_change_timeline.py` | 완료/재개, 잠금, 보류 기원 기록, 이력 표시 |
| API | `backend/app/api/v1/order_lines.py`, `lots.py` | 필터·건수·완료/취소 경로와 처리자 연결 |
| WPF | `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLineList/Dtos/OrderLineListItemDto.cs`, `OrderLineListResponse.cs`, `OrderLineShortCloseRequest.cs` | API 필드 연결과 한글 상태 표시 |
| WPF | 같은 모듈의 `ViewModels/OrderLineListPageViewModel.cs`, `Views/OrderLineListPage.xaml`, `OrderLineListPage.xaml.cs`; `Views/Shell/MainWindow.xaml.cs` | 대기 버튼, 처리 액션, 변경 행 반영, 페이지·스크롤 유지 |
| 검증 | `backend/tests/test_order_work_queues.py`, `frontend-wpf/tests/OrderLineRegression/OrderLineRegression.csproj`, `Program.cs` | 실제 정산/출고 흐름, PostgreSQL 동시성·migration·API, WPF 동작·렌더링 |
| 문서 | 이 문서, `project-operations.md`, `database-architecture.md`, `database-schema.svg` | 상태 정의, 운영과 배포 조건 기록 |

## 검증 및 수동 확인

대기목록 기능의 최초 검증 결과(후속 조회 최적화 검증은 아래 링크 참조):

- 분리 PostgreSQL 전체 백엔드: **413 passed, 1 skipped, 107 subtests passed**. 제외 1개는 Windows 테스트 계정의 심볼릭 링크 생성 권한에 따른 기존 항목이다. 새 완료/재작업 동시성, migration 무결성/이력 보호와 실제 API 요청 검증은 실행하여 통과했다.
- WPF 발주 **24**, 검수 **83**, 재고 **57**, API **34**개 검증 통과. 발주 검증은 실제 컨트롤의 화면 렌더링, 바인딩 오류 없음, 처리 후 스크롤 유지까지 포함한다.
- Debug 및 Release 빌드: 경고 0, 오류 0. `git diff --check` 통과.
- 로컬 개발 DB: `6b7c8d9e0f1a → 7c8d9e0f1a2b` 적용 완료. 백업 1회 후 분리 DB에서 복원·마이그레이션을 먼저 검증했다. 적용 전후 기존 11개 업무 테이블의 전체 데이터 해시가 동일하다(새 필드만 비교 제외). 백업은 `.tmp/order-work-queues-20260922/development-backup-20260922T063157Z/development-before.dump`, 결과는 같은 폴더 `result.json`에 보관한다.
- 개발 DB 읽기 전용 점검: LOT 생성 대기 0건, 종료판단대기 1건이며 전체 건수와 필터 목록이 일치했다. 현재 데이터에서 건수 조회 약 63ms, 각 대기목록 첫 페이지 약 32/44ms였다. 이는 현재 개발 데이터 기준이며 운영 규모의 부하 검증 결과는 아니다.
- 실행 중 개발 API `/api/v1/health`, `/api/v1/ready` 모두 200, 신규 완료/취소 경로 반영 확인. 서버컴퓨터의 DB·API·WPF와 GitHub는 이번 작업에서 변경하지 않았다.

자동검증은 합성 데이터만으로 재고 보류→계획→LOT 생성, 재고 소진, 전체 건수/페이지, 전량 미검수·출고 0, 수량 불변, 자기 예약만 해제, 부분검수/미정산 차단, 수동완료→취소/재작업→재대기, 목표 초과 출고, 동시 완료/재작업, migration/무결성/롤백 보호, API 인증/충돌을 다룬다. WPF는 실제 화면 렌더링과 버튼/페이지/행/스크롤 유지까지 검증한다.

운영 업무 데이터에서의 쓰기는 자동검증하지 않는다. 수동 확인은 개발 화면에서 실제 대기 분류가 의도한 발주와 맞는지, 긴 발주번호/품목명과 현장 화면 배율에서 버튼·수량이 보이는지, 테스트용 발주로 완료→취소→재작업 흐름이 자연스러운지 확인한다. 과거 데이터에 저장된 보류 근거가 없거나 검수/정산 상태가 불일치하는 건은 임의 보정하지 않으며 일반 생산중 목록에서 별도 확인한다.

후속 조회 최적화에서는 동일 SQL 안의 대기 평가를 공유하고 생산완료 탭의 불필요한 대기 건수 계산을 생략했다. WPF는 미조회와 0건을 구분하고 생산중 복귀 시 최신 건수를 읽는다. 완료 처리 직전 재검증은 유지한다. API와 WPF를 함께 배포하며 추가 DB migration은 없다. [성능 전후 비교·변경 파일·검증 결과](order-work-queue-performance-2026-09-22.md#후속-최적화-결과)를 참조한다.
