# 검수·재고 점검 후 수정 완료 기록

작업일: 2026-09-18. 사용자가 승인한 점검 후 수정 범위다. 개발 소스와 기본 Debug 실행 파일을 빌드했다. 업무 DB의 데이터·스키마 변경, 운영 배포는 수행하지 않았다.

## 수정 결과

| 순서 | 문제 | 변경한 동작 |
|---|---|---|
| R1 | 기존 불량 메모가 불량유형 기본 메모로 덮어써짐 | 기존 검수 조회에서는 저장된 메모를 유지한다. 빈 메모도 기본값으로 채우지 않는다. 새로운 불량유형을 선택할 때만 기본 메모를 적용한다. |
| R2 | 이력 조회 후 LOT 수량과 상단·하단 합계가 서로 다른 시점 | 이력, 해당 품목의 LOT 목록, 검색조건 전체 합계, 품목 총재고를 같은 서버 읽기 시점으로 함께 갱신한다. 수정일시도 같이 반영한다. |
| R3 | LOT 조회 중 사용자가 바꾼 선택이 이전 LOT로 돌아감 | 응답 도착 시점의 선택을 유지한다. 사용자가 선택을 해제했다면 다시 선택하지 않는다. |
| R4 | 다른 품목을 선택한 뒤 이전 품목의 안내문·경고가 다시 나타남 | 이전 조회가 중첩된 이력 조회를 기다리는 동안 화면 소유권을 잃으면, 이전 데이터와 안내문을 더 이상 반영하지 않는다. |
| 정리 1 | 화면·저장에 쓰이지 않는 클라이언트 FIFO 미리보기 계산 | 계산 함수, 호출, 전용 합계 속성을 삭제했다. 실제 출고를 처리하는 서버 FIFO는 유지한다. |
| 정리 2 | 구 재고조정 경로에서 사유 없이 증감 가능 | 신규·기존 경로 모두 사유를 필수로 통일하고 공백 및 1,000자 초과를 거부한다. 서버 서비스도 변경 전 사유를 확인한다. |
| 문서 | 생산 즉시 출고분을 원장에 기록하지 않는다는 설명 | 실제 코드와 일치하도록 생산 입고와 출고를 각각 기록하며, 화면의 재고편입은 잔여수량이라는 설명으로 정정했다. |

R1과 R2는 수정 전 실패하는 회귀검증을 먼저 확인했다. R3·R4에는 응답 완료 순서를 직접 조절하는 재현 검증을 추가했다.

## 재고 조회 계약과 화면 상태

`GET /inventories/movements`에 선택적 조회 항목을 추가했다.

| 항목 | 의미 |
|---|---|
| `stock_page` | 지정하면 이력과 함께 LOT 목록을 반환한다. 1 이상이며 `product_inventory_lot_id`가 필요하다. |
| `stock_size` | LOT 페이지 크기. 기본 50, 최대 200이다. |
| `stock_q` | LOT 번호 검색조건이다. 이력의 기간·구분 검색과 독립적이다. |
| `stock_include_zero` | LOT 재고 0 포함 여부다. 기본 false다. |
| 응답 `stock_snapshot` | 기존 LOT 목록과 같은 계약이다. LOT 행·해당 검색조건의 전체 합계·품목 총재고·수정일시·정합성 경고를 담는다. |

- 동일한 `REPEATABLE READ, READ ONLY` 트랜잭션 안에서 이력과 재고 요약을 조회한다. 이력 조회 후 다른 거래가 재고를 변경해도 한 응답 안에서는 시점이 섞이지 않는다.
- LOT 조회 합계는 현재 50행의 합산이 아니다. 서버가 검색조건에 맞는 전체 LOT의 합계를 반환한다.
- 재고 소진으로 마지막 페이지가 사라지면 서버가 유효한 마지막 페이지로 보정한다. 선택 LOT가 해당 목록에서 빠지면 오른쪽 이력도 닫아 잘못된 연결을 남기지 않는다.
- 이력 재조회는 왼쪽 목록에 실제로 적용된 LOT 검색조건을 사용한다. 입력만 하고 아직 조회하지 않은 검색어·0 포함 체크를 임의 적용하지 않는다.
- 신규 LOT 조회는 진행 중인 이전 이력 조회도 무효화한다. 다른 품목·LOT뿐 아니라 같은 LOT에 대해 늦게 도착한 이전 응답도 새 조회를 덮어쓰지 못한다.
- 새 WPF는 `stock_snapshot`이 없는 서버 응답이나 이력·LOT 수량이 서로 충돌하는 응답을 부분 반영하지 않고 서버 버전 확인 안내를 표시한다. 기존 호출자가 `stock_page`를 보내지 않으면 기존 조회 계약을 유지한다.
- 품목 연속 선택의 250ms 대기, 명시적인 LOT 상세보기, 페이지 조회는 유지했다. 이력 조회 한 번에 합계를 함께 가져오므로 별도 합계 조회 요청을 추가하지 않는다. DB 내부에는 LOT·합계 조회가 추가되며, 실제 운영 부하는 별도 확인 대상이다.

## 삭제·유지 판단

삭제한 것은 `AllocateStockLotsByFifo`, `InspectionResultFormPolicy.AllocateFifo`, `StockLotTotalQty`, `StockLotAllocatedQty` 및 해당 호출이다. 화면에 노출되지 않는 미리보기 계산을 더 이상 수행하지 않는다.

구 품목 단위 재고조정 API는 외부 호출 여부를 확정할 수 없어 사유 검증을 통일한 상태로 유지한다. 새 화면은 선택 LOT 전용 경로를 계속 사용한다. 서버의 출고 FIFO, 기존 재고 원장, 과거 검수 정산 소유권 처리, 저장 이력의 출고 수량 응답은 실제 사용 중이므로 보존했다.

이미 잘못 저장된 불량 메모나 과거 재고 자료를 추정해서 복원하지 않았다. 이번 변경은 재발 방지를 위한 코드 수정이다.

## 변경 파일

| 파일 | 변경 이유 |
|---|---|
| [InspectionResultWindowViewModel.cs](C:/Users/jaewon/Documents/Codex/mes-v1.5/frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/ViewModels/InspectionResultWindowViewModel.cs) | 저장 메모 보존, 미사용 FIFO 호출·속성 삭제 |
| [InspectionResultFormPolicy.cs](C:/Users/jaewon/Documents/Codex/mes-v1.5/frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Services/InspectionResultFormPolicy.cs) | 미사용 FIFO 미리보기 함수 삭제 |
| [InventoryPageViewModel.cs](C:/Users/jaewon/Documents/Codex/mes-v1.5/frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Inventories/ViewModels/InventoryPageViewModel.cs) | 일괄 재고 갱신, 선택 보존, 이전 응답 차단 |
| [InventoryMovementListDto.cs](C:/Users/jaewon/Documents/Codex/mes-v1.5/frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Inventories/Dtos/InventoryMovementListDto.cs) | 이력의 재고 스냅샷 응답 매핑 |
| [inventories.py](C:/Users/jaewon/Documents/Codex/mes-v1.5/backend/app/api/v1/inventories.py) | 스냅샷 조회 입력 계약 |
| [inventory.py](C:/Users/jaewon/Documents/Codex/mes-v1.5/backend/app/schemas/inventory.py) | 스냅샷 응답 계약, 조정 사유 제약 공유 |
| [product_inventory_query.py](C:/Users/jaewon/Documents/Codex/mes-v1.5/backend/app/services/product_inventory_query.py) | 이력과 같은 트랜잭션에서 LOT 목록·합계 조회, 페이지 보정 |
| [product_inventory_adjustment_service.py](C:/Users/jaewon/Documents/Codex/mes-v1.5/backend/app/services/product_inventory_adjustment_service.py) | 구 경로를 포함해 사유 없는 조정을 변경 전에 거부 |
| [InspectionRegression/Program.cs](C:/Users/jaewon/Documents/Codex/mes-v1.5/frontend-wpf/tests/InspectionRegression/Program.cs) | 저장 메모·빈 메모 검증, 폐기한 미리보기 검증 정리 |
| [InventoryRegression/Program.cs](C:/Users/jaewon/Documents/Codex/mes-v1.5/frontend-wpf/tests/InventoryRegression/Program.cs) | 합계·필터·선택·중첩 응답·구 서버·화면 검증 |
| [test_product_inventory_query.py](C:/Users/jaewon/Documents/Codex/mes-v1.5/backend/tests/test_product_inventory_query.py) | 스냅샷 합계·페이지·필터·경고·사유 검증 |
| [test_inventory_lot_flows.py](C:/Users/jaewon/Documents/Codex/mes-v1.5/backend/tests/test_inventory_lot_flows.py) | HTTP 입력 계약 및 실제 PostgreSQL 동시 변경 검증 |
| [project-operations.md](C:/Users/jaewon/Documents/Codex/mes-v1.5/docs/project-operations.md), [inventory-lot-tabs-2026-09-18.md](C:/Users/jaewon/Documents/Codex/mes-v1.5/docs/inventory-lot-tabs-2026-09-18.md), [수정 전 점검 기록](C:/Users/jaewon/Documents/Codex/mes-v1.5/docs/inspection-inventory-change-review-2026-09-18.md), 본 문서 | 현재 동작·원장 설명·해결 상태·검증 결과 기록 |

## 검증 결과

| 검증 | 결과 |
|---|---|
| 전체 백엔드 테스트 | **395 passed, 1 skipped, 65 subtests passed** |
| PostgreSQL 필수 회귀검증 게이트 | 통과. 동시 검수 수정·재고 예약, 읽기 스냅샷, 마이그레이션 왕복 포함 |
| 신규 재고 스냅샷 동시 변경 | 통과. 읽기 중 다른 연결에서 재고 500을 차감해도 기존 응답의 모든 수량을 유지하고, 다음 조회에서 모두 500 감소 |
| 검수 WPF | **79 checks passed** |
| 재고 WPF | **58 checks passed**. 실제 컨트롤 렌더링 및 바인딩 오류 0 포함 |
| API WPF | **34 checks passed** |
| WPF 기본 Debug 및 별도 검증 빌드 | 오류 0, 경고 0 |
| 변경 공백 검사 | `git diff --check` 통과 |

재고 화면을 1120·1440 너비로 렌더링했고, 1120 너비의 실제 생성 화면에서 품목 재고·LOT 수량·조회 합계·이력 배치를 확인했다. 합성 데이터로 렌더링했으며 업무 데이터 화면 캡처는 아니다.

전체 백엔드 결과 파일: [backend-tests.xml](C:/Users/jaewon/Documents/Codex/mes-v1.5/.tmp/review-fixes-20260918/backend-tests.xml). 별도 테스트 폴더는 [review-fixes-20260918](C:/Users/jaewon/Documents/Codex/mes-v1.5/.tmp/review-fixes-20260918)이다.

검증은 메모리 DB와 기존 전용 로컬 `127.0.0.1:55439/mes_regression`의 임시 스키마에서 수행했다. 검증용 PostgreSQL은 종료해 작업 전 중지 상태로 돌렸다. 업무 DB의 복원·수량 정리·스키마 적용은 하지 않았다.

## 미실행·남은 위험과 수동 확인

- 백엔드 테스트 1건은 현재 Windows 계정에서 심볼릭 링크 생성이 불가하여 건너뛰었다. 관련 파일 경로 보안 검증의 나머지 항목은 실행됐다.
- 운영 서버에 배포하지 않았으며, 실제 업무 자료의 검수 저장·수정·재고조정을 실행하지 않았다. 실제 데이터 이상 여부와 운영 동시 사용자 부하는 이번 합성 검증으로 확정할 수 없다.
- 배포는 **백엔드 먼저, WPF 다음** 순서다. 새 WPF와 구 서버가 섞이면 이력 조회가 서버 버전 확인 안내로 중단된다. 구 재고조정 호출자도 이제 유효한 사유를 보내야 한다.
- 이미 덮어써진 과거 메모는 원본·백업 확인이 필요하다. 임의 복원하지 않는다.

수동 확인 순서:

1. 새 개발 빌드에서 메모가 있는 기존 검수와 메모가 빈 검수를 각각 열고, 다른 항목만 수정한 뒤에도 메모가 보존되는지 확인한다.
2. 재고 상세보기를 연 뒤 별도 테스트 작업에서 재고를 변경하고 이력을 다시 조회한다. 상단 품목 합계, 왼쪽 조회 합계·LOT 수량, 오른쪽 현재 재고 및 수정일시가 함께 갱신되는지 확인한다.
3. LOT 조회 중 다른 LOT를 선택하거나 선택을 해제한다. 이전 LOT로 돌아가거나 오른쪽 이력이 임의로 다시 열리지 않아야 한다.
4. 상세 이력 조회 중 다른 품목을 선택한다. 이전 품목의 이력·경고가 나타나지 않아야 한다.
5. LOT 검색과 0 포함, 마지막 페이지에서 재고 소진을 확인한다. 선택 LOT가 조회 대상에서 빠지면 상세보기는 닫히고 페이지·합계는 갱신돼야 한다.
6. 재고조정 사유 공백은 저장되지 않고, 유효한 사유로 조정하면 해당 LOT만 변경되는지 확인한다. 예약 물량 보호도 유지돼야 한다.
