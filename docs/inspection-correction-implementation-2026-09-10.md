# 검수 오류 수정 결과 및 운영 적용 절차

2026-09-10 / 로컬 구현·합성 자료 검증 / 운영 미적용

2026-09-11 출고 입력 규칙 변경: 사용자 결정에 따라 출고 자동배분 체크박스·출고량 자동 계산·처리계획의 재고 출고량 자동 채우기를 삭제했다. 신규 회차는 재고 출고와 생산 출고를 0으로 시작하고, 기존 실적 수정은 저장된 출고량을 유지한다. 출고수량은 직접 입력하고, 남은 판매가능수량의 재고편입 계산과 저장 검증은 유지한다. LOT 계획 미달 규칙과 DB 구조는 이번 변경 대상이 아니다.

원인 확인 후 적용 판단: 본 개발 수정 전체는 미업데이트 WPF 장애의 긴급 해결에 필요한 최소 범위가 아니다. 독립 결함 수정과 사용자 확정 업무 규칙이 함께 포함되어 있다. 현재1.0.0.40과 새 서버의 호환성, 기존 자료에 대한 강화된 저장 제한을 포함해 [수정 범위 재평가](inspection-change-reassessment-2026-09-11.md)를 먼저 확인한다. 전체 수정본의 운영 적용을 승인하거나 실행한 상태는 아니다.

후속 현장 확인: 사용자가 분할검수 오류의 원인이 미업데이트 WPF 사용이었다고 확인했다. 아래 구버전 요청 차단은 이 문제의 재발 방지에 해당한다. 재고 표시·자동배분·이월 정산 등의 별도 수정과 구분하며, 이번 현장 확인으로 운영 배포나 DB 정정을 추가 실행하지 않았다. [운영 버전 분석과 확정 근거](operating-version-analysis-2026-09-11.md).

후속 작업에서 9월9일 운영 백업을 개발 DB에 복원하고 실제 자료로 검증했다. [운영 백업 개발 복원·검증 결과](production-backup-rehearsal-2026-09-10.md)를 함께 참조한다. 아래 최초 구현 검증과 후속 운영자료 검증의 범위를 구분한다.

## 수정한 동작

| 업무 | 변경 내용 |
|---|---|
| 재고 표시 | 자기 예약·다른 예약·실재고·사용가능량을 구분한다. 요약과 LOT 목록은 같은 기준을 사용한다. 같은 LOT의 이전 회차 재고도 표시한다. |
| 재고 불일치 | 전체/LOT 합계 차이, 과다 예약, LOT 미연결 예약을 숨기지 않고 설명한다. 해당 재고를 바꾸는 저장을 제한한다. |
| 신규 검수 | 재고·생산 출고수량은 0에서 시작하며 사용자가 직접 입력한다. 처리계획의 예약재고는 조회·출고 검증에 사용하되 출고량을 자동으로 채우지 않는다. |
| 직접 배분 | 양품·불량출고·폐기 변경이나 분할검수 전환으로 입력한 출고량이 바뀌지 않는다. 남은 판매가능수량은 재고편입으로 자동 계산하고 불가능한 배분은 저장을 막는다. |
| 다음 회차 재고 사용 | 1차에서 출고하지 않은 판매가능수량은 재고로 편입된다. 2차에서는 해당 LOT 잔량을 보고 재고 출고수량을 입력한다. 이번 양품에는 새 검수분만 입력한다. LOT 차감은 기존 예약·선입선출 규칙을 유지한다. |
| 기존 실적 | 저장된 출고 배분과 이월량을 그대로 불러온다. 동일값·메모 수정은 기존 수불을 재생성하지 않는다. |
| 이월 정산 | 원실적마다 정산한 실적과 수량을 저장한다. 기존 결과는 원래 귀속된 이월만 유지하고 중복 정산하지 않는다. |
| 실제 수량 수정 | 원장을 삭제하지 않고 증가·감소 차이를 추가한다. 출고 LOT 배정은 변경하지 않은 부분을 보존한다. 변경 전후·작업자 이력을 남긴다. |
| LOT 초과/미달 | 계획 초과를 허용한다. 계획 미달 최종 종료는 별도 미달 사유를 요구하며 가짜 미검수량을 만들지 않는다. 처리량0의 신규 종료는 허용하지 않는다. |
| 재고비축 | 확정 계획의 출고목표0을 검수·출고·발주 목록·완료 판단에 적용한다. 기존재고 출고 없이 생산량을 재고편입한다. |
| 완료 상태 | 생산 LOT 미완료이면 출고목표 충족만으로 발주를 완료하지 않는다. 정상 완료 후 출고 감액으로 부족해지면 CLOSED로 되돌린다. 명시한 부족종결은 유지한다. |
| 재발 방지 | 예약·검수·출고·수동조정은 같은 상품 잠금을 사용한다. 예약된 재고를 수동감소할 수 없고, 취소·부족종결은 미사용 예약을 해제한다. 별도 출고확정에도 남은 출고목표와 LOT 검증을 적용한다. |
| 발행 자료 | 성적서/COA가 발행된 건은 일반 검수 화면에서 수량을 바꾸지 못하게 보호한다. 메모 수정은 가능하다. 발행자료 정정 절차·권한은 별도 업무정책 대상이다. |
| 구버전 | 저장 요청의 수량규칙 버전2와 기존 실적 수정 버전을 확인한다. 구버전 저장은 데이터 변경 전에 업데이트 안내로 거절한다. |

계획 확정·검수 저장 시 실제 출고완료와 재고 차감이 일어나는 시점은 유지했다.

## 삭제한 구규칙과 구현

- 자기 예약을 빼고 현재 생산 LOT 전체를 제외하던 검수 LOT 조회 구현.
- 조회에서만 `입고−이번 양품` 차이로 이월을 추측하던 `inferred_legacy_carry_qty` 계산.
- 저장에서 회차 순서 없이 PARTIAL_DONE 미정산만 다시 모으던 별도 함수.
- 기존 입출고 원장·출고행을 전부 삭제하고 재생성하던 검수 수정 구현 및 전용 보조 함수.
- 양품이 바뀌어도 생산출고를 늘리지 않고 수동 입력을 강제로 잘라내던 화면 계산.
- 폐기를0으로 초기화하고 가용재고를 무조건 우선 출고하던 `ApplyAutoShipmentPreview`.
- LOT 계획 미달 최종검수를 무조건 거절하던 화면·서버 조건.
- 검수·별도 출고 완료에서 거래처 이름으로 목표를 다시 계산하던 중복 구현.

과거 수량을 추론하는 처리는 일반 조회·저장에서 제거했다. DB 변환 스크립트에는 명확한 과거 정산 연결만 복원하는 일회성 절차를 둔다. 이 변환은 실적 수량·재고·출고량을 바꾸지 않는다.

## DB 변경 및 API 계약

마이그레이션: `5a6b7c8d9e0f`, 이전 버전 `4f5a6b7c8d9e`.

- `inspection_result.shortage_reason`: 별도 최종 미달 사유.
- `inspection_result.settlement_owner_id`: 해당 물량을 정산한 실적의 ID. 자기 회차 정산은 자기 자신을 참조한다.
- `inspection_result.settled_sellable_qty`: 원실적에서 정산한 판매가능수량. 소유자 수정 시에도 다른 원실적의 수량을 보존한다.
- 소유자 FK, 소유자 조회 인덱스, 소유자·수량·정산시각의 짝 검증을 추가한다.
- `inspection_result_revision`: 실적 수정 전후, 출고 배정, 작업자, 생성시각. 운영 이력을 지우는 롤백을 막는다.
- 검수 저장은 `quantity_rule_version=2`를 요구한다. 기존 결과는 `expected_updated_at` 필수다.
- 조회에 미달 사유, 실재고, 예약 구분, `stock_error`, `settlement_error`를 추가한다.
- 기존 응답명 `prior_unsettled_sellable_qty`는 신규에서는 미정산 앞 회차, 기존 결과에서는 그 결과가 이미 맡은 이월량을 의미한다. 2026-09-11 사용자 요청으로 출고/재고 처리 제목 옆의 ‘이월 미정산/이번 정산 이월’ 표시는 삭제했다. 과거 수량 보존을 위한 API 필드와 계산은 유지하며 이 표시 삭제로 DB를 변경하지 않는다.

수정 원장은 기존 타입에 부호 있는 변경분을 추가한다. 예를 들어 입고 취소분은 음수 INSPECTION_IN, 출고 취소분은 양수 SHIP_OUT이다. 잔액·입고·출고 누계는 원본과 정정분의 합으로 계산해야 하며, 원본 행을 삭제하거나 양수 행만 집계하면 안 된다.

## 기존 데이터 변환 기준

1. 당회 판매가능량−폐기와 검수입고 원장합이 일치하는 정산 완료 실적은 자기 정산으로 연결한다.
2. 추가 이월은 동일 LOT의 앞 회차, PARTIAL_DONE, 동일 정산시각·작업자, 원실적 자체 수불 없음, 이월합과 소유자 입고 차이 일치를 모두 확인한다.
3. 한 원실적의 소유자가 여러 개로 해석되거나 수량·시각 근거가 불충분하면 연결하지 않는다. 조회에 점검 필요를 표시하고 기존 결과 수정을 막는다.
4. 같은 변환을 다시 실행해도 연결과 수량이 중복되지 않는다.

전달받은 운영 보고서의 일정612는 원실적19,500+20,000을 정산실적50,000에 연결해 입고89,500을 보존하는 조건에 해당한다. 실제 적용 직전 데이터가 같은지는 다시 확인해야 한다.

## 운영 적용 순서

1. 영향 업무의 쓰기를 멈추고 오류 PC 실행 경로·버전을 확인한다. 현재 DB 백업과 독립 복구 검증을 준비한다.
2. `backend/scripts/inspection_correction_preflight.sql`을 읽기 전용으로 실행해 전체/LOT 차이, 과다 예약, 종료 발주의 미사용 예약, LOT 미연결 조정, 출고 원장 불일치를 대조한다.
3. 수주818의540,000 예약과 수동 차감은 실제 고객 출고 여부를 확인해 별도 정정한다. 일반 출고확정을 다시 눌러 추가 차감하지 않는다. 수주844의65,000 예약은 분리해 보존한다.
4. 상품1160의 전체32,000/LOT82,000 차이는 실물·LOT별 증빙으로 별도 정리한다. 이 코드나 마이그레이션은 어느 쪽이 맞는지 추정해 숫자를 바꾸지 않는다.
5. 검증한 버전의 DB 마이그레이션, 서버, 내부 WPF를 호환 묶음으로 적용한다. 구버전 PC의 저장 요청은 차단된다.
6. `backend/scripts/inspection_correction_postflight.sql`로 미복원 정산과 잘못된 연결을 조회한다. `alembic current --check-heads`, `alembic check`로 스키마를 확인한다.
7. 오류 PC에서593의 재고 표시·출고 직접 입력·분할 저장, 1차 무출고 재고편입 후 2차 재고 출고,612의 동일값 저장·수정, LOT 초과/미달, 순수 재고비축을 확인한다. 실제 수량 변경 시험은 합의된 검증 대상에서만 수행한다.
8. 잔액·LOT·원장·출고·완료 상태를 대조한 뒤 쓰기를 재개한다.

운영 데이터 정정은 여기서 실행하지 않았다. 증빙 없이540,000 예약이나50,000 차이를 일괄 보정하는 스크립트도 만들지 않았다.

## 롤백

- 새 데이터가 생기기 전에는 호환된 이전 코드와 스키마 복구 절차를 적용할 수 있다.
- 새 수정 이력 또는 미달 사유가 있으면 마이그레이션 downgrade가 오류로 중단한다. 업무 이력을 조용히 삭제하지 않는다.
- 쓰기 재개 뒤 과거 DB 전체 복원은 새 정상 거래를 잃을 수 있다. 영향 기능을 멈추고 거래별 정정 또는 수정 배포로 대응한다.

## 검증과 한계

수정 전 재현 테스트로 자기 예약 누락, 이월 재저장 오류, 동일값 저장의 수불 삭제를 확인했다. 수정 후 자동 검증은 별도 합성 자료를 사용한다.

- 전체 백엔드: **341개 통과, 4개 건너뜀, 하위 검증 15개 통과**. 건너뛴 항목 중 PostgreSQL 전용 3개는 아래 별도 실행에서 통과했다. 기존 백업 스크립트의 심볼릭 링크 검증 1개는 테스트 사용자 권한으로 생성할 수 없어 미실행이다.
- PostgreSQL: **19개 통과**. 실제 스키마 upgrade/downgrade, 모델과 스키마 일치, 이월 19,500+20,000의 귀속 복원, 동일값 보존, 수량 증감, 수정 이력, 발행자료 보호, 트랜잭션 롤백, 동시 실적 수정·예약의 단일 성공, 구방식 미완료 출고의 중복 정산 차단을 검증했다.
- WPF 화면 로직: **12개 검증 통과**. 사진의 양품432,000과 기존재고65,000이 출고497,000으로 요청에 반영됨, 수동 배분 보존, 음수 배분 차단, 미달 사유, 이월39,500 유지, 재고비축, 조회 실패 차단을 확인했다.
- WPF 빌드: 내부 프로그램 Debug 및 내부·외주 전체 솔루션 Release **경고0 / 오류0**. 수정 화면을 합성 자료로 창 표시 없이 렌더링해 수량·미달 사유·재고 목록의 배치를 확인했다. 실제 오류 PC의 해상도·배율 검증을 대신하지는 않는다.
- 수정한 추적 파일의 `git diff --check` 통과. 삭제 대상인 이월 추론·옛 자동배분·별도 미정산 조회 함수가 실행 소스에서 제거되었음을 확인했다.
- PostgreSQL 검증은 전용 로컬 포트55439의 임시 스키마에서 수행했다. 운영 DB 연결·운영자료 복원은 없으며, 검증 후 전용 인스턴스는 종료했다.
- 실제 오류 PC 실행 버전,593의 실패 요청 원문,540,000의 출고 증빙,상품1160의 실물재고는 이번 구현으로 확인된 사실이 아니다.
- 운영 배포, 운영 수량 정정, 실제 PC 화면 조작·납품 검증은 미실행이다.

## 변경 파일 범위

- 백엔드: 검수 저장/조회/수량정책, FIFO 표시, 처리계획·출고·취소·수동조정·완료 규칙, DTO/API, 실적 모델과 수정 이력 모델.
- 신규 공통 서비스: `inspection_settlement_service.py`, `inspection_stock_service.py`, `inventory_lock_service.py`, `order_fulfillment_policy.py`.
- DB: 소유자 연결·미달 사유·수정 이력 마이그레이션, 읽기 전용 적용 전후 점검 SQL.
- WPF: 검수 실적 ViewModel·DTO·XAML, 의존성 추가 없는 화면 로직 검증 프로젝트.
- 테스트와 문서: 검수/재고 회귀 테스트, 본 문서, 운영구조·DB 구조와 도식.

기존 사용자 변경인 배포 스크립트와 ClickOnce 게시 설정은 수정하지 않았다. 개발용 임시 스크립트와 테스트 DB는 배포 산출물에 포함하지 않는다.

### 상세 파일 목록

아래 경로는 저장소 루트 기준이다. 기존 분석 문서와 사용자 선행 변경은 이번 수정 목록에 포함하지 않는다.

| 구분 | 변경 파일 |
|---|---|
| API·스키마 | `backend/app/api/v1/inspection_results.py`, `backend/app/schemas/inspection_result.py`, `backend/app/schemas/inspection_schedule.py` |
| 모델 | `backend/app/models/__init__.py`, `backend/app/models/inspection_result.py`, `backend/app/models/inspection_result_revision.py`(신규) |
| 검수 | `backend/app/services/inspection_quantity_policy.py`, `inspection_result_query.py`, `inspection_result_service.py`, `inspection_schedule_query.py`, `inspection_schedule_service.py` |
| 신규 공통 서비스 | `backend/app/services/inspection_settlement_service.py`, `inspection_stock_service.py`, `inventory_lock_service.py`, `order_fulfillment_policy.py` |
| 연관 업무 서비스 | `backend/app/services/inventory_fifo_service.py`, `order_line_cancel_service.py`, `order_line_list_query.py`, `order_line_plan_service.py`, `order_line_short_close_service.py`, `order_line_update_service.py`, `product_inventory_adjustment_service.py`, `shipment_confirm_service.py` |
| DB 변환·점검 | `backend/migrations/versions/5a6b7c8d9e0f_preserve_inspection_settlement_ownership.py`, `backend/scripts/inspection_correction_preflight.sql`, `backend/scripts/inspection_correction_postflight.sql`(모두 신규) |
| 백엔드 검증 | `backend/tests/test_inspection_corrections.py`(신규), `test_inspection_result_service.py`, `test_inspection_result_query.py`, `test_inspection_schedule_query.py`, `test_product_inventory_query.py` |
| 화면 | `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Dtos/InspectionResultDtos.cs`, `ViewModels/InspectionResultWindowViewModel.cs`, `Views/InspectionResultWindow.xaml` |
| 화면 검증 | `frontend-wpf/tests/InspectionRegression/InspectionRegression.csproj`, `frontend-wpf/tests/InspectionRegression/Program.cs`(신규) |
| 운영 문서 | 본 문서(신규), `docs/project-operations.md`, `docs/database-architecture.md`, `docs/database-schema.svg` |

각 표 행에서 폴더를 생략한 후속 파일은 해당 행의 첫 파일과 같은 폴더 기준이다. 화면 행의 `Dtos`, `ViewModels`, `Views`는 모두 `Modules/InspectionSchedules` 하위다.

## 2026-09-11 출고 자동배분 삭제 검증

변경 이유: 출고 여부와 수량은 작업자가 결정한다. 1차 무출고 검수는 재고로 편입하고, 2차 검수에서 이전 회차 재고와 이번 생산분을 구분하여 직접 출고한다.

이번 변경 파일:

- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/ViewModels/InspectionResultWindowViewModel.cs`: 자동배분 상태·전환·출고량 계산을 삭제하고 신규 출고량을 0으로 초기화. 기존 실적은 저장된 출고량을 유지.
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Views/InspectionResultWindow.xaml`: 출고 자동배분 체크박스 삭제.
- `backend/app/services/inspection_result_query.py`: 신규 실적 응답에 처리계획의 예약량을 출고량으로 미리 채우던 분기와 사용하지 않는 import 삭제.
- `frontend-wpf/tests/InspectionRegression/Program.cs`: 수동 출고·전량 재고편입·회차 전환·기존 실적 유지·초과 출고 차단 검증.
- `backend/tests/test_inspection_corrections.py`: 확정 계획이 있어도 신규 출고량 0인지 검증하고, 이전 회차 재고의 조회부터 다음 회차 출고 수불까지 검증 확장.
- `docs/project-operations.md`, 본 문서: 사용자 확정 규칙과 검증 결과 반영.
- 임시 화면 검증 도구 `.tmp/stock-lot-ui-check-20260911/Program.cs`: 실제 개발 DLL을 렌더링하여 체크박스 삭제와 기존재고 두 열 표시 확인. 배포 대상 제외.

검증 결과:

- 변경 전에 화면과 서버 양쪽에서 출고량 0 초기화 테스트가 실패하는 것을 확인했다. 변경 후 통과했다.
- WPF 회귀 검사 23개 통과. 모의 API를 사용했으며 실제 DB 요청은 없다.
- 검수 조회·저장·수량규칙·재고 목록의 백엔드 테스트 51개 중 48개 통과, PostgreSQL 전용 3개는 전용 연결 설정을 사용하지 않아 건너뛰었다. 실행한 DB 연동 테스트는 메모리 SQLite의 합성 데이터만 사용했다.
- 1차 양품30·출고0 → 재고30, 2차 새 양품50·재고출고30·생산출고50 → 최종재고0을 실제 저장 서비스로 확인했다. 총 입고80·출고80이며 1차 수량을 재입고하거나 이월로 중복 정산하지 않는다.
- 개발 Debug 전체 빌드: 경고0·오류0. 실제 XAML 렌더링에서 자동배분 체크박스가 없고 기존재고 표가 LOT 번호·재고수량 두 열임을 확인했다.
- 실행 소스에서 자동배분 상태·체크박스·예약량 자동 채우기 분기가 제거되었고, 관련 변경 파일의 공백 오류 검사를 통과했다.

실행하지 않은 검증과 남은 확인:

- 운영 배포, 실제 사용자 화면에서의 업무 저장, PostgreSQL 전용 동시성·마이그레이션 테스트는 이번 작업에서 실행하지 않았다. DB 구조와 저장 수불 알고리즘은 변경하지 않았다.
- 개발·운영 업무 DB의 데이터 정정은 실행하지 않았다. 기존 재고·예약 불일치에 대한 저장 차단은 유지된다.
- 수동 확인은 새 Debug 실행본에서 신규 출고량이 0인지, 양품을 입력해도 출고량이 바뀌지 않고 재고편입으로 계산되는지, 기존 실적 수정 시 저장된 출고량이 유지되는지를 확인한다. 이미 실행 중인 이전 실행본은 이 변경을 반영하지 않는다.
