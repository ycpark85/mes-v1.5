# 발주 품명 스냅샷과 선택적 MES 기준 품명 변경

## 업무 규칙

- 일반/인쇄/무지 모두 엑셀의 품명·규격을 발주 행마다 저장한다. 이름이 같아도 저장하며, 품목·도면·재고의 식별자는 기존 `product_id`를 유지한다.
- `MES 기준 품목명도 변경`은 기본 해제다. 해제하면 발주만 파일 품명으로 저장한다. 체크하면 MES 기준 **품목명만** 추가로 변경한다. 기준 규격은 변경하지 않는다.
- 무지 공유 품목도 명시적으로 체크하면 공통 기준 품목명을 변경할 수 있다. 거래처 연결에 저장된 이름과 다른 발주의 스냅샷은 변경하지 않는다.
- 같은 업로드에서 같은 MES 품목에 서로 다른 기준 품목명 변경을 요청하면 관련 발주 그룹을 모두 차단한다. 주문번호가 달라도 검사한다. 같은 이름에 서로 다른 발주 규격은 충돌이 아니다.
- 이름 차이와 규격 차이를 각각 안내한다. 빈 품명, 품명 200자 초과, 규격 100자 초과는 체크 여부와 관계없이 등록 불가다. 품명과 `[규격]`을 합친 입력은 최대 303자다.
- 수기 등록은 일반 품목의 현재 기준 품명·규격, 무지는 선택한 거래처 연결의 품명·규격을 저장한다.
- 스냅샷이 있는 발주의 품목·거래처 교체는 차단한다. 잘못 연결한 발주는 취소 후 올바른 품목으로 등록한다. 수량·납기 등은 기존 수정 정책을 따른다.

## 기존 발주 보호와 DB 계획

새 컬럼, 인덱스, 마이그레이션은 없다. 기존 `order_line.source_erp_product_code`, `source_product_name`, `source_product_spec`과 CHECK 제약을 활용한다. 물리적 관계가 바뀌지 않아 `database-schema.svg`는 수정하지 않는다.

1. 기준 품목명 변경 시 해당 품목의 쓰기 잠금을 얻는다. 품목관리에서 기준 품명 또는 규격을 직접 수정할 때에도 동일하게 보호한다.
2. 해당 품목의 기존 발주 중 `source_erp_product_code IS NULL`인 행에 변경 직전 코드·품명·규격을 기록한다. 완료·취소·비활성 발주도 포함한다. 이미 저장한 스냅샷은 덮어쓰지 않는다.
3. 기존 발주의 식별자, 거래처, 수량, 상태, 업무 수정 시각은 유지한다. 현재 거래처 연결로 과거 ERP 코드를 추정하지 않는다.
4. 기준 품목명 변경과 신규 발주 등록은 같은 트랜잭션/발주 그룹 savepoint 안에서 수행한다. 등록 실패 시 과거 발주 보존과 기준 품목명 변경도 함께 취소된다.
5. 배포 시 전체 과거 발주를 일괄 갱신하지 않는다. 변경 시점에 해당 품목만 대상으로 한다. 보존 값은 **변경 직전 기준 정보**이며 최초 원본 발주파일을 복원한 값이 아니다.

일반·무지 모두 저장 시 품목을 잠그고 연결을 다시 확인한다. 무지의 연결 ID/품목 ID 재검증도 유지한다. 동시에 들어온 별도 요청은 잠금 순서대로 기준 이름을 변경할 수 있으나 각각의 발주 품명과 과거 스냅샷은 보존된다.

## API와 화면

- 기존 `/order-lines/bulk/validate`, `/order-lines/bulk/commit` 및 `apply_product_name_change` 필드 이름을 유지한다. 체크는 기준 **품명만** 변경하는 선택이며, 발주 스냅샷 저장 여부를 결정하지 않는다.
- 기존 수주 쓰기 권한과 서버의 거래처·품목·연결 유효성 검증을 유지한다. 화면만으로 저장 여부를 제한하지 않는다.
- WPF는 발주 품명과 MES 기준 품명을 나란히 보여주고 체크박스를 바로 옆에 배치한다. 검증 결과 텍스트 셀은 읽기 전용이며 체크박스만 선택할 수 있다. 재검증하면 체크는 해제된다.
- 기존 등록 확인창에서 선택한 기준 품명 변경 건수, 공유 품목의 영향, 기준 규격 유지 여부를 안내한다.
- 발주 목록/상세, LOT 등록 문맥/목록/상세/재작업/추적, 생산일보, 외주 작업지시/묶음/발주, 보현 외주 현황, 검수 일정/대상/실적, 출하 목록은 발주 스냅샷 이름을 표시한다. 해당 조회의 이름 검색도 스냅샷을 포함한다.
- 규격이 없는 발주 스냅샷은 이후의 기준 규격으로 채우지 않는다. 새 COA는 발주 품명·규격을 사용하며 이미 생성한 COA는 재작성하지 않는다.
- 품목관리, 품목별 재고 집계 및 원가 계산용 품목 기준은 계속 MES 마스터를 사용한다. 새 품목 생성이나 재고 분리는 없다.

## 정리한 기존 코드

- 무지의 명시적 기준 품명 변경을 일괄 차단하던 분기 제거.
- 이름 변경 체크 시 기준 규격까지 덮어쓰던 코드 제거.
- 무지에만 스냅샷을 저장하던 분기 제거.
- 주문번호별로만 실행하던 충돌 검사 함수를 업로드 전체 검사로 대체.
- 이미 검증·잠금한 품목을 다시 읽고 검사하던 중복 처리 제거.
- WPF의 중복 결과 대입과 불필요해진 조건부 체크 해제 분기 제거.
- 발주 문맥의 이름·규격 조회는 재사용되는 표시 함수로 통일했다. 관계없는 기능의 정리는 하지 않았다.

## 검증과 배포

체크/해제, 일반/무지, 공유 거래처의 다른 발주 및 연결 보존, 충돌, 규격 미변경, 빈 값/길이, 등록 실패 롤백, 완료·비활성 과거 발주 보존, 수기 등록, 신규/기존 COA를 검사한다. 발주→LOT→외주→검수→출하 조회·검색과 기존 생산일보 캐시의 발주 품명 표시도 검사한다.

PostgreSQL 동시 등록은 `127.0.0.1:55440/mes_unprinted_test`의 임시 스키마만 사용한다. 일반/무지의 동시 기준 이름 변경과 과거 발주 보존을 검증한 뒤 테스트 스키마를 제거한다. WPF 회귀 실행으로 기본 체크 해제, 재검증, 취소, 선택값 전송, 안내문 및 실제 화면 렌더링을 확인한다.

운영 서버에는 이번 수정사항을 아직 반영하지 않았다. 기존 DB 버전 `8d9e0f1a2b3c` 위에서 API와 WPF를 함께 배포해야 한다. DB 백업 후 기존 업무를 마무리하고 새 프로그램으로 교체하며, 스냅샷을 지우거나 역마이그레이션하지 않는다.

수동 확인은 실제 발주파일로 체크 해제 1건/체크 1건을 등록해 기준 이름·발주 이름·규격·과거 발주 표시를 비교하고, 동일 발주가 검수·출하까지 같은 이름으로 이어지는지 확인한다. 운영 데이터로 신규 업무를 등록하는 검사 및 서버 부하 검증은 개발 회귀 검사에 포함하지 않는다.

배포 후 문제가 생기면 신규 발주 등록과 기준 품명 수정을 중지하고 이전 API/WPF를 함께 복구한다. 저장한 스냅샷은 삭제하지 않는다. 이전 프로그램은 일부 화면에서 기준 품명을 표시할 수 있으므로 원복 중에는 품명 변경 업무를 재개하지 말고 수정본을 검증한다. 이번 변경에는 DB 역마이그레이션이 없다.

## 최종 검증 기록 — 2026-10-20

- 백엔드 전체: **464 passed, 13 skipped, 124 subtests passed**. `.tmp/order-name-snapshots-20261020/backend-tests.xml`에 결과를 보관했다.
- 별도 PostgreSQL 일반/무지 동시 등록: **2 passed**. `.tmp/order-name-snapshots-20261020/postgres-snapshot-tests.xml`에 결과를 보관했다. 초기 테스트 구성의 확장 모듈 검색 경로와 필수 데이터 누락을 수정한 뒤 두 경우 모두 통과했다.
- 전체 실행에서 생략된 13개 중 새 동시 등록 2개와 기존 무지 마이그레이션 검사 1개는 전용 DB에서 별도 통과했다. 나머지 9개는 다른 기능 전용 PostgreSQL 환경 설정이 없고, 1개는 Windows 테스트 계정의 심볼릭 링크 생성 권한이 없어 생략했다.
- WPF Release 빌드 성공, 이번 빌드 출력에 오류·경고 없음. 회귀 실행 **35개 통과**, 화면 바인딩 오류 없음. 최종 화면 `.tmp/order-name-snapshots-20261020/screenshots/order-auto-match.png`에서 품명 비교·체크박스 배치를 확인했다.
- `git diff --check` 통과. 새 표시/보존 함수의 불필요한 import가 없음을 확인했다. 새 의존성은 추가하지 않았다.
- 운영 서버 배포·실제 고객 파일로 운영 수주 등록·운영 단말의 전체 업무 흐름·운영 규모 성능 검증은 실행하지 않았다. 개발 데이터로 검증하는 작업 범위이며 운영 데이터에 신규 업무를 만들지 않았다.
- 남은 제약: 과거 원본 이름이 없는 발주는 변경 직전 MES 기준 이름만 보존할 수 있다. 발주 이력이 많은 품목의 최초 이름 변경은 해당 과거 행을 저장하는 동안 시간이 더 걸릴 수 있어 실제 운영 규모에서 확인해야 한다.

## 변경 파일

아래 경로는 저장소 기준이다.

- 기준 품명 변경과 스냅샷 저장:
  `backend/app/api/v1/products.py`,
  `backend/app/schemas/order_line.py`,
  `backend/app/schemas/product.py`,
  `backend/app/services/bulk/order_line_bulk_service.py`,
  `backend/app/services/order_product_snapshot_service.py`,
  `backend/app/services/partner_product_mapping_service.py`,
  `backend/app/services/order_line_update_service.py`.
- 발주·생산·검수·출하 표시 및 검색:
  `backend/app/crud/lot.py`,
  `backend/app/services/order_line_display.py`,
  `backend/app/services/order_line_detail_query.py`,
  `backend/app/services/order_line_lot_context_query.py`,
  `backend/app/services/order_line_response_builder.py`,
  `backend/app/services/lot_query.py`,
  `backend/app/services/lot_rework_service.py`,
  `backend/app/services/lot_trace_query.py`,
  `backend/app/services/bohyun_outsource_service.py`,
  `backend/app/services/outsource_purchase_order_query.py`,
  `backend/app/services/outsource_work_instruction_query.py`,
  `backend/app/services/inspection_result_query.py`,
  `backend/app/services/inspection_work_instruction_query.py`,
  `backend/app/services/production_daily_query.py`,
  `backend/app/services/shipment_list_query.py`,
  `backend/app/services/shipment_coa_service.py`.
- WPF:
  `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLines/Views/OrderLineBulkImportPage.xaml`,
  `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLines/ViewModels/OrderLineBulkImportPageViewModel.cs`.
- 회귀 검사:
  `backend/tests/test_order_product_snapshots.py`,
  `backend/tests/test_order_product_snapshots_postgres.py`,
  `backend/tests/test_order_line_services.py`,
  `backend/tests/test_product_code_display.py`,
  `backend/tests/test_unprinted_product_management.py`,
  `frontend-wpf/tests/UnprintedProductRegression/Program.cs`,
  `frontend-wpf/tests/UnprintedProductRegression/SharedCodeWalkthrough.cs`.
- 운영 문서:
  `docs/project-operations.md`,
  `docs/database-architecture.md`,
  `docs/unprinted-product-management-2026-10-19.md`,
  `docs/order-product-name-snapshots-2026-10-20.md`.
