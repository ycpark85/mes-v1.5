# 검수 재고 조회 리팩토링(R07) 결과 — 2026-09-14

검수실적등록의 재고 요약과 LOT 목록을 하나의 상세 응답으로 통합하고, LOT마다 반복하던 조회와 예약·수불 합산을 정리했다. 생산 LOT와 재고 LOT의 내부 식별자도 분리했다.

화면은 기존의 **LOT 번호 / 재고수량** 두 열을 유지한다. 수동 출고 입력, 잔량 재고편입, 분할검수 저장 시 정산, 예약 우선·FIFO, 기존 실적 수정과 LOT 미달·초과 규칙은 바꾸지 않았다. 운영 배포 및 개발 업무 DB의 데이터·스키마 변경은 수행하지 않았다.

## 바뀐 조회 흐름

| 항목 | 이전 | 현재 |
|---|---|---|
| 검수 상세·재고 목록 요청 | 상세와 `/stock-lots`를 각각 요청 | 상세의 `inventory.stock_lots`를 사용 |
| 재고의 조회 기준 | 별도 요청 사이에 재고가 변할 수 있음 | 상세·재고 응답을 같은 PostgreSQL 읽기 스냅샷으로 생성 |
| 생산 LOT 연결 조회 | 재고 LOT마다 SELECT | 품목의 생산 LOT 연결을 한 번에 조회 |
| 예약·수불 계산 | LOT마다 전체 예약·수불 목록 재순회 | LOT별 합계를 한 번 구한 뒤 사용 |
| LOT 내부 식별자 | `lot_id`에 생산 또는 재고 ID 혼용 | `product_inventory_lot_id`와 nullable `production_lot_id` 구분 |
| 지원되지 않는 서버 | 재고 정보를 별도 요청 | 통합 정보 누락 시 서버 업데이트 안내 및 저장 차단 |

검수 상세와 재고에 필요한 요청은 2회에서 1회로 줄었다. 불량유형 표시 등 별도 업무 조회까지 모두 한 요청으로 합친 것은 아니다.

상세와 호환용 재고 목록 GET에서만 새 읽기 세션을 사용한다. PostgreSQL에서 `REPEATABLE READ, READ ONLY`를 설정하고 응답 생성이 끝나면 세션을 닫아 트랜잭션을 종료한다. 다른 사용자의 재고 변경은 계속 가능하며, 현재 응답 안의 값만 같은 조회 시점을 유지한다. 인증·권한 검사 및 저장 경로의 잠금·격리 수준은 기존대로 유지한다.

화면을 연 뒤 바뀐 재고는 저장할 때 서버가 최신 값으로 다시 검사한다. 이번 변경은 재고를 예약하거나 저장 성공을 보장하는 기능이 아니다. 조회 이후 사용 가능량이 줄어든 경우 기존 저장 검증이 차단하고 데이터 전체를 되돌리는 것을 검사했다.

## 계약과 호환성

- 상세 응답의 `inventory.stock_lots`에는 재고가 없어도 빈 배열이 명시적으로 포함된다. 누락과 재고 0을 구분한다.
- 각 행의 `product_inventory_lot_id`는 실제 재고 LOT 식별자다. 생산 LOT가 없는 기존재고의 `production_lot_id`는 `null`이다.
- WPF는 두 식별자를 64비트 정수로 읽고 기존의 혼용 `lot_id`를 사용하지 않는다. ID 누락·중복 또는 가용수량 합계 불일치는 저장 전에 차단한다.
- 기존 지원 클라이언트가 사용하는 `/stock-lots` GET과 그 응답의 `lot_id`는 호환성을 위해 유지한다. `lot_id`는 API 문서에 폐기 예정 필드로 표시한다. 신규 화면의 별도 조회 함수와 전용 목록 DTO는 삭제했다.
- 응답에 새 필드를 추가하는 방식이며 저장 요청 버전, 수량 규칙 버전, 인증·권한 및 DB 모델은 변경하지 않았다.
- 새 WPF는 R07 서버의 통합 응답이 필요하다. 서버를 먼저 업데이트한 뒤 WPF를 업데이트할 수 있다. 새 WPF를 이전 서버에 연결하면 빈 재고로 처리하지 않고 업데이트 안내 후 저장을 막는다. 서버를 이전 버전으로 되돌릴 때 클라이언트 조합도 확인해야 한다.

## 변경 파일

| 파일 | 변경 이유 |
|---|---|
| `backend/app/db/inspection_read.py` — 신규 | 두 재고 관련 읽기 API에 한정된 읽기 전용 스냅샷 세션 |
| `backend/app/api/v1/inspection_results.py` | 상세 GET을 읽기 세션에 연결 |
| `backend/app/api/v1/inspection_schedules.py` | 호환용 재고 LOT GET을 같은 읽기 방식에 연결 |
| `backend/app/schemas/inspection_result.py` | 상세 재고 요약에 `stock_lots` 추가 |
| `backend/app/schemas/inspection_schedule.py` | 생산·재고 식별자 분리와 기존 필드 폐기 예정 표시 |
| `backend/app/services/inspection_stock_service.py` | 예약·수불·기존 출고의 LOT별 합산을 단일 순회로 정리 |
| `backend/app/services/inspection_schedule_query.py` | 생산 LOT 연결 일괄 조회, 같은 재고 자료를 상세·호환 응답으로 변환 |
| `backend/app/services/inspection_result_query.py` | 한 번 읽은 재고 자료로 요약과 LOT 행 생성 |
| `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Dtos/InspectionResultDtos.cs` | 통합 목록·64비트 식별자 수신, 사용하지 않는 별도 목록 DTO 삭제 |
| `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/ViewModels/InspectionResultWindowViewModel.cs` | 별도 LOT 요청 삭제, 통합 응답 검증·표시 |
| `backend/tests/test_inspection_schedule_query.py` | LOT 수 증가에도 조회 횟수 일정, 생산 LOT 없는 재고와 식별자 연결 검사 |
| `backend/tests/test_inspection_result_query.py` | 상세·재고 목록의 단일 기준과 추가 응답 필드 검사 |
| `backend/tests/test_inspection_corrections.py` | 조회 중 동시 재고 변경, 읽기 전용·세션 복원, 조회 후 저장 재검증 |
| `backend/scripts/inspection_regression_gate.py` | 새 PostgreSQL 스냅샷 검사 2개를 배포 전 필수 검사로 등록 |
| `frontend-wpf/tests/InspectionRegression/Program.cs` | 단일 요청·빈 목록·누락·불일치·ID·재조회·기존 수정 규칙 검사 |
| `docs/project-operations.md`, 이 문서 | 조회 구조·호환성·검증 결과 누적 |

새 외부 패키지, DB 마이그레이션, 화면 열은 추가하지 않았다. 기존 사용자 변경과 이전 단계의 소스를 보존했다.

## 검증 결과

| 검사 | 결과 |
|---|---|
| 변경 전 실패 재현 | LOT 수에 따른 SELECT 증가 및 별도 식별자 부재 확인 |
| 서버 전체 회귀검사 | **372 통과, 49 하위 사례 통과, 1 건너뜀** |
| PostgreSQL 필수 검사 | **6개 모두 통과**, 새 스냅샷 검사 2개 포함 |
| WPF 검수 검사 | **62 통과**, 이전 52개 포함 |
| WPF API 검사 | **34 통과** |
| Debug 전체 빌드 | 성공, 경고 0·오류 0 |
| Release 전체 빌드·산출물 확인 | 성공 |
| 개발 DB 스키마 조회 | `6b7c8d9e0f1a (head)`, 추가 변경 필요 없음 |
| 변경 전후 예약·수불 조합 비교 | **40개 모두 동일** |
| 변경 공백 검사 | 통과 |
| 배포 전 통합 검사 | **WARNING**, 미커밋 변경사항·명시적으로 생략한 NuGet 복원 때문 |

건너뛴 검사는 `test_linked_file_is_rejected` 1개다. 현재 Windows 검사 사용자가 심볼릭 링크를 만들 수 없어 실행하지 못했다. PostgreSQL 필수 검사는 모두 실제 전용 DB에서 실행했다.

변경 전후 비교에는 자기예약·다른예약·현재 실적 출고, 기존 실적의 수불 되돌림 기준, 연결 없는 자료, 음수·합계 불일치 자료를 포함했다. 수량과 행 순서, 오류 안내가 동일했다. 이 검사는 합성 자료만 사용했으며 실제 업무 데이터를 고치지 않았다.

### 조회 횟수

동일한 합성 SQLite 자료에서 기존 실적이 있는 재고 LOT 목록 조회를 측정했다. 세 크기 모두 기존 응답 필드의 값이 변경 전후 일치했다.

| 재고 LOT 수 | 변경 전 SELECT | 변경 후 SELECT |
|---:|---:|---:|
| 1 | 9 | 9 |
| 20 | 28 | 9 |
| 200 | 208 | 9 |

이는 LOT 목록 조회의 횟수 측정이며 전체 상세 API의 SELECT 수나 운영 응답시간 측정 결과는 아니다. 조회량은 일정해졌지만 실제 운영 환경에서의 시간·실행계획·메모리 효과는 별도로 측정해야 한다.

### 동시 변경과 화면 보호

- PostgreSQL에서 재고 LOT를 읽은 직후 별도 연결로 재고를 65에서 60으로 변경·확정했다. 같은 상세 응답은 요약과 LOT 모두 65를 유지했고, 새 조회에서는 모두 60을 반환했다.
- 읽기 전용 세션에서는 쓰기가 거부됐으며, 종료 후 일반 세션은 기존 `READ COMMITTED`·쓰기 가능 상태를 유지했다. 기존 저장 실적도 읽기 전용 세션에서 정상 조회됐다.
- 조회 후 재고가 65에서 15로 줄었을 때 20 출고 저장을 시도하면 차단됐고, 실패한 검수 저장은 업무 행을 변경하지 않았다.
- WPF는 통합 정보 누락·가용수량 합계 불일치·식별자 누락·중복을 차단한다. 빈 배열은 정상 재고 0으로 처리한다.
- 재조회 성공 시 실패 상태를 해제한다. 실제 재고 불일치 안내는 유지하면서 기존의 동일 값 저장 경로와 수량 변경 차단 규칙을 보존한다.

검사 근거는 `.tmp/inspection-stock-refactor-20260914/`와 다음 보고서 폴더에 있다.

`C:/Users/jaewon/Documents/Codex/mes-v1.5-db-safety/inspection-stock-refactor-20260914/release-validation/20260914T044214Z-ae892e8a-25532/`

검사에 사용한 기존 전용 PostgreSQL(`127.0.0.1:55439/mes_regression`)은 검사 종료 후 중지했다. 개발 업무 DB를 복원하거나 수정하지 않았다.

## 수동 확인과 남은 범위

실제 사용자의 실행 중인 프로그램은 재시작하지 않았다. 업무 DB에 실적을 저장하는 화면 검사는 수행하지 않았으므로 새 Debug 실행본에서 테스트용 자료로 다음을 확인한다.

1. 검수실적등록을 다시 열어 LOT 번호와 실재고 수량이 기존 두 열에 표시되는지 확인한다.
2. 출고 0으로 저장한 1차 분할검수의 재고가 2차에 보이고, 재고·생산 출고를 직접 입력할 수 있는지 확인한다.
3. 기존 최종실적을 열어 저장된 출고 배분과 재고편입 값이 유지되는지 확인한다.
4. 다른 작업에서 재고가 바뀐 경우 창을 다시 열면 새 수량이 보이는지 확인한다. 저장 시 부족 안내가 나오면 재조회 후 처리한다.

R07 코드·자동 검증은 완료했다. 운영 배포, 실제 운영 부하 측정, 업무 데이터 정정은 수행하지 않았다. 생산현황 중복 갱신(R10), 도면·파일 처리(R09), DB 제약 검토(R08), 문서·저장소 전체 정리(R11)는 이후 별도 범위다.
