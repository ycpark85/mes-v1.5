# 무지 품목 관리 — 2026-10-19

> 2026-10-20 후속 변경: 발주 품명 스냅샷은 일반·인쇄 품목까지 확대했다. 체크 시 무지의 공통 MES 기준 품명도 변경할 수 있으며 과거 발주는 보호한다. 아래 최초 구현 이력보다 [현재 품명 정책](order-product-name-snapshots-2026-10-20.md)을 우선한다.

## 적용 범위 확정

### 2026-10-20 GitHub 반영 전 확인

- 무지 등록·거래처 연결·수주 매칭, 업무 코드/MES 코드 표시, 품목관리 검색 및 화면 배치 변경을 함께 반영한다. 관련 소스·테스트·운영 문서와 예시 화면을 포함한다.
- 최종 작업본의 백엔드 전체 테스트: `.venv/Scripts/python.exe -m pytest -q --disable-warnings --maxfail=1 --tb=short` → **439 passed, 11 skipped, 124 subtests passed**. PostgreSQL 전용 환경과 Windows 심볼릭 링크 조건부 검사는 기본 실행에서 건너뛰었다.
- WPF의 마지막 확인 결과는 아래 필터 변경의 빌드 성공·30개 검사 통과 기록을 따른다. GitHub 반영을 위해 업무 서버·DB 또는 실행 중인 WPF를 변경하지 않는다. 운영 배포/전체 릴리스 게이트는 별도 절차다.

### 품목관리 관리방식 검색 추가

품목관리 상단에 `관리방식: 전체 / 기존 방식 / 무지 별도관리` 선택을 추가했다. 신규 메뉴 없이 기존 품목 목록에서 무지 관리 대상만 확인하고, 품목을 선택한 다음 `거래처 연결`을 눌러 연결 업체와 해제 이력을 확인한다.

| 선택 | 조회 조건 |
|---|---|
| 전체 (기본값) | 관리방식 제한 없음. 선택한 사용여부·검색어는 적용 |
| 기존 방식 | `is_unprinted_managed=false`. 별도관리로 설정하지 않은 기존 무지도 포함 |
| 무지 별도관리 | `is_unprinted_managed=true`. `MES-U` 신규 코드와 기존 코드를 유지한 전환 품목 모두 포함 |

- 사용 방법: 관리방식을 선택한 후 `조회`를 누른다. 검색어·사용여부는 동시에 적용되고 조회 시 1페이지부터 시작한다. 다음/이전 페이지에도 같은 조건이 전달되며 건수는 필터에 맞는 전체 품목 수다.
- `초기화`는 관리방식 `전체`, 사용여부 `사용`, 검색어 빈 값으로 되돌린다. 기존 초기화 동작처럼 목록은 `조회`로 갱신한다. `신규`는 검색 조건을 유지한다.
- API 계약: `GET /products`에 선택적 불리언 쿼리 `is_unprinted_managed`를 추가했다. 생략하면 기존 목록 계약을 유지하며, `true`/`false`는 관리방식만 제한한다. `q`, `partner_q`, `is_active`, `page`, `size`와 함께 사용할 수 있고 잘못된 불리언은 422로 거절한다. 같은 필터를 count와 목록에 적용한 뒤 페이지를 나눈다.
- 기존 코드·도면·연결·수주·재고 데이터 및 DB 스키마 변경은 없다. 별도 마이그레이션 없이 서버를 먼저 반영하고 WPF를 같은 변경본으로 빌드·실행한다. 구버전 서버는 새 조건을 무시할 수 있으므로 두 구성요소의 버전을 맞춘다. 필터만 되돌릴 경우 이전 서버/WPF 소스로 복귀하면 되며 데이터 복원은 필요하지 않다.

**검증 결과**

- 서버: `.venv/Scripts/python.exe -m pytest tests/test_product_query.py tests/test_unprinted_product_api.py tests/test_unprinted_product_management.py -q --disable-warnings --maxfail=1 --tb=short` (backend에서 실행) → **23 passed, 12 subtests passed**. 세 관리방식과 사용여부 조합, 기존 코드 전환, 연결된 ERP 코드/품명/거래처 검색, 페이지와 건수, 잘못된 입력, 기존 무지 등록·매칭 규칙을 확인했다.
- WPF: `UnprintedProductRegression` **30개 검사 통과**. 관리방식별 요청, 검색어 인코딩, 미사용·빈 목록, 102건의 무지 조회와 페이지 이동, 재검색 1페이지, 초기화/신규, 거래처 연결·이력·수주 검증 흐름을 확인했다. 실제 WPF 프로젝트를 포함한 별도 출력 경로 빌드는 경고/오류 0개다.
- 실제 WPF 뷰를 1100×560, 1280×720, 1440×900으로 렌더링했다. 바인딩 오류 0건이며 작은/큰 화면에서 검색 조건과 상단 편집 버튼이 잘리지 않는지 직접 확인했다. 화면은 합성 데이터다. [작은 화면](../output/product-management-filter/product-1100x560.png), [큰 화면](../output/product-management-filter/product-1440x900.png).
- 미실행: 전체 서버 회귀·PostgreSQL 전용 릴리스 검사·실제 업무 서버를 연결한 조작·운영 배포. 이번 변경은 읽기 필터이고 관련 회귀/메모리 DB 통합 검사를 수행했으며, 실행 중인 사용자 앱과 업무 데이터는 변경하지 않았다.
- 수동 확인: 새 서버와 새 WPF 실행 → `무지 별도관리` 선택 후 조회 → 기존 코드로 전환한 품목도 포함되는지 확인 → 품목 선택 후 `거래처 연결`에서 업체/해제 이력 확인 → `기존 방식`, `전체`, 초기화 후 조회를 확인한다.

**이번 필터 변경 파일 (9개)**

- `backend/app/api/v1/products.py`: 선택적 관리방식 조회 계약.
- `backend/app/services/product_query.py`: 조회와 전체 건수에 공통 필터 적용.
- `backend/tests/test_product_query.py`: 관리방식·사용여부·검색·페이지 DB 통합 검사.
- `backend/tests/test_unprinted_product_api.py`: API 계약 및 입력 검증.
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/Views/ProductPage.xaml`: 상단 검색 조건과 배치.
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/ViewModels/ProductPageViewModel.cs`: 선택값, 요청 쿼리, 초기화.
- `frontend-wpf/tests/UnprintedProductRegression/Program.cs`: 화면 흐름과 요청·응답 회귀 검사.
- `docs/project-operations.md`: 운영 규칙 누적.
- `docs/unprinted-product-management-2026-10-19.md`: 사용 방법·검증·반영 및 수동 확인 절차.

### 품목코드 노출 기준 변경 계획 및 적용 결과

- 발주리스트부터 LOT, 생산일보, 외주 작업, 검수지시·일정·실적의 조회 응답에서 `product_code`는 수주 당시 `source_erp_product_code`를 우선 표시한다. 원본이 없는 기존 수주·인쇄 품목은 기존 코드를 표시한다. `mes_product_code`를 별도로 제공하여 내부 식별 코드를 구분한다.
- 등록·수정 요청의 `product_id`, 도면 연결, 재고 계산은 유지한다. 품목 마스터의 저장 코드와 생산 스냅샷의 기존 저장 의미를 바꾸지 않으며, DB 마이그레이션은 추가하지 않는다.
- 해당 업무 화면의 품목 검색은 업무 코드와 MES 코드 모두 지원한다. 검수실적등록 창에는 두 코드를 명시한다. 기존 API 클라이언트도 업무 조회의 `product_code`에는 업무 코드를 받게 되므로 새 코드 의미와 MES 보조 필드를 함께 문서화한다.
- 변경 전 실패 테스트로 수주→LOT 및 검수 조회·검색을 확인하고, 변경 후 관련 서버 회귀 검사와 실제 WPF 화면 렌더링을 검증한다.

적용 결과: 발주리스트·상세, LOT 생성·조회·이력, 생산일보, 외주 작업지시·묶음 목록/상세·발주 묶음 카드·보현 작업/출하, 검수지시·일정·실적 목록/등록 창, 출하 목록에 반영했다. 업무 코드와 MES 코드를 함께 검색하며, 묶음은 포함된 코드들을 중복 없이 표시한다. 수주 당시 원본이 없는 기존 자료는 기존 코드 그대로이며, 표시를 위해 기존 데이터나 현재 연결을 재작성하지 않는다. 품목 마스터처럼 거래처/수주가 정해지지 않은 기준정보의 저장 코드는 유지한다.

| 예시 | 품목코드 (기본 표시) | MES 코드 (별도 표시) | 도면/재고 연결 |
|---|---|---|---|
| A 기존 품목 | MUJI-100 | MUJI-100 | 기존 품목 유지 |
| B 같은 코드·다른 도면 | MUJI-100 | MES-U000001 | B용 새 품목 유지 |
| A/B 같은 제품을 공유하는 별도 예시 | MUJI-100 | MES-U000001 | 두 업체 모두 같은 품목 |

**이번 표시 변경 검증**

- 백엔드 전체: `backend/.venv/Scripts/python.exe -m pytest -q --disable-warnings --maxfail=1` → **436 passed, 11 skipped, 112 subtests passed**. 업무 코드/내부 코드 분리, 기존 인쇄 코드, 공유 코드·서로 다른 품목, LOT·외주·검수·출하 조회/검색, 기존 생산 스냅샷 무재작성 검증 11개를 추가했다.
- WPF 무지 등록 회귀 **18개**, 수주 회귀 **30개**, 검수 회귀 **83개** 통과. 실제 업무 WPF 프로젝트를 포함한 빌드 성공. 새 의존성 없음.
- 실제 WPF 뷰 8장 렌더링과 바인딩 오류 0건. 새 발주 목록·검수실적등록·출하 이미지 직접 확인. 출하 목록의 수주별 묶음 행에서도 MES 코드가 유지되는지 검증했다. 예시 API는 메모리 데이터만 쓰며 네트워크/업무 DB에 등록하지 않는다. [발주리스트](../output/product-code-display/06-orders-registered.png), [검수실적등록](../output/product-code-display/07-inspection-result.png), [출하](../output/product-code-display/08-shipments.png).
- `git diff --check` 통과. 문서와 DB 구조도를 검토했으며 추가 스키마 변경은 없다.
- 미실행: PostgreSQL 전용 격리 검사 등 11개 환경 조건부 테스트는 기본 실행에서 건너뛰었다. 이번에는 표시 조회 변경이므로 DB 마이그레이션/복원 재연습 및 실제 업무 DB에 새 수주·검수실적을 등록하는 검사는 하지 않았다. NuGet 취약성 피드 조회는 네트워크 제한으로 NU1900 경고가 났으며, 빌드와 테스트 자체는 성공했다. 전체 운영 릴리스 게이트/배포는 수행하지 않았다.
- 남은 확인: 서버와 WPF를 같은 변경본으로 실행해야 새 MES 코드 보조 필드가 보인다. 새 빌드 실행 후 실제 거래처 연결 수주 1건을 품목코드로 조회하여 발주→LOT→외주→검수에서 같은 업무 코드와 올바른 MES 코드·도면이 이어지는지 확인한다. 이전 서버/클라이언트가 혼용되면 표기와 필드가 서로 다를 수 있다.

화면 재현: 저장소 루트에서 `dotnet run --project frontend-wpf/tests/UnprintedProductRegression --no-restore -p:UseSharedCompilation=false -- --walkthrough output/product-code-display`.

- 현재까지의 품목과 데이터는 정상이다. 이번 기능은 **앞으로 ERP 코드를 공유하는 무지 품목을 관리하기 위한 기능**이다.
- 기존 품목·인쇄 품목·도면·수주·재고는 그대로 사용한다. 도입 전에 기존 품목을 일괄 전환하거나 도면·목형·재고를 재점검할 필요가 없다. 과거 데이터 정리나 재고 분리는 하지 않는다.
- 앞으로 공유 대상 무지 품목을 등록할 때, 같은 제품·도면이면 거래처들을 같은 MES 품목에 연결하고 다른 도면이면 각각의 MES 품목에 연결한다. 이후 수주는 거래처+ERP 코드로 자동 매칭한다.
- 기존 무지 품목이 나중에 코드 공유 대상이 되는 경우에만 아래의 선택적 설정 절차를 사용한다. 기존 품목 전체에 필요한 도입 절차가 아니다.

## 구현 전 변경 계획

- 기존 품목코드, 도면, 수주, LOT, 재고 데이터는 변경하지 않는다. 기존 품목은 `is_unprinted_managed=false`로 기존 동작을 유지한다.
- 신규 무지 별도관리 품목은 서버에서 내부코드를 발급한다. 기존 품목을 명시적으로 무지 별도관리로 전환할 때에도 기존 코드와 참조를 유지한다.
- `product.product_code` 및 `product.drawing_id` UNIQUE 제약을 유지한다. 같은 제품/도면을 쓰는 여러 거래처는 같은 `product_id`에 연결한다.
- 거래처별 ERP 코드·품명 연결을 추가한다. 활성 상태의 `(partner_id, erp_product_code)`는 하나의 MES 품목만 가리킨다. 사용 중지한 연결도 보관하며 다른 거래처의 연결로 추측하지 않는다.
- 수주에는 원본 ERP 코드·품명·규격을 선택적으로 보관한다. 기존 수주는 원본이 없으므로 현재 품목 조회 방식으로 표시한다. 무지 연결 수주의 품명 차이는 공통 마스터 변경으로 처리하지 않는다.
- 서버 API 계약, 연결 관리 화면, 수주 검증 결과의 내부코드/도면 표시를 함께 변경한다. 기존 인쇄 품목 등록 및 업로드 방식은 유지한다.

## DB 적용 및 복구 계획

1. 품목 관리 구분, 내부코드 발급용 카운터, 거래처 연결 테이블, 수주 원본 정보 컬럼을 추가한다. 기존 레코드의 식별자·수량·도면을 재작성하지 않는다.
2. 짧은 DDL 잠금 제한을 사용하고, 먼저 격리된 PostgreSQL에서 기존 데이터 보존·동시 발급·연결 중복 차단·Alembic 정합성을 검증한다.
3. 운영 적용 시 백업 후 쓰기를 중지하고 마이그레이션 → API → WPF 순서로 배포한다. 구버전 클라이언트의 무지 수주 안전성도 서버에서 검증한다.
4. 신규 기능을 사용하기 전에는 역마이그레이션할 수 있다. 무지 등록/연결/원본 수주 이력이 생긴 뒤에는 이를 삭제하는 downgrade를 차단하고 전진 수정 또는 백업 복구 계획을 사용한다.
5. 실제 업무 DB 마이그레이션과 운영 배포는 이번 개발 검증에서 수행하지 않는다. 기존 재고 분리는 요청 범위에 없으며 도입 절차에도 포함하지 않는다.

## 검증 계획

- A/B 업체가 코드와 품명이 달라도 같은 MES 품목에 연결되는 경우 및 C 업체가 같은 ERP 코드로 다른 도면에 연결되는 경우.
- 거래처별 미연결, 비활성 연결/품목, 중복 연결, 도면 중복, 이름 덮어쓰기 차단, 기존 인쇄 업로드 호환.
- 발급 동시성, 저장 직전 재검증, 수주 원본 보존 및 품목/재고 식별자 유지.
- WPF 등록/조회/연결 관리/업로드 표시와 기존 회귀 검사.

## 구현 및 검증 결과

### 적용한 업무 흐름

1. **인쇄**: 기존처럼 품목코드·도면을 등록한다. 무지 옵션은 기본 해제 상태다. 기존 품목은 자동 전환하지 않는다.
2. **신규 무지**: 품목관리 → 신규 → `무지 별도관리` 선택 → 공통 품명·도면·라우팅·규격 입력 → 저장한다. 서버가 `MES-U000001` 형태로 내부코드를 발급하며 저장한 품목이 선택된다.
3. **거래처 연결**: 저장된 품목의 `거래처 연결`을 연다. 고객 거래처, ERP 코드, 해당 거래처의 품명·규격을 등록한다. 같은 제품/도면이면 A·B를 동일 품목에 연결한다. 다른 도면을 쓰는 C는 별도 품목을 만든 뒤 연결한다.
4. **수주**: 기존 수주 엑셀을 불러와 검증한다. 거래처·ERP 코드로 연결하고 검증 표에 거래처, MES 내부코드, 도면번호를 표시한다. 무지의 품명 차이는 정상이며 마스터 품명 변경 체크는 허용하지 않는다. 등록할 때 검증 당시 품목/연결 ID와 현재 연결을 비교한다.
5. **연결 수정**: 연결 목록에서 기존 연결을 해제하고 올바른 품목에서 다시 추가한다. 기존 수주를 새 도면으로 자동 이동하지 않는다. 이미 검증해 둔 엑셀은 재검증해야 한다. 목록은 해제 이력 포함 20건씩 조회한다.

| 거래처 | ERP 코드 | 거래처 품명 | MES 품목 | 도면 |
|---|---|---|---|---|
| A | MUJI-100 | A용 상자 | MES-U000001 | D-001 |
| B | MUJI-100 | B용 포장재 | MES-U000001 | D-001 |
| C | MUJI-100 | A용 상자 | MES-U000002 | D-002 |

A·B의 품명은 달라도 같은 품목·재고를 사용한다. C의 품명은 A와 같아도 도면이 다르므로 별도 품목·재고를 사용한다. 품명이나 규격만으로 동일 제품을 추정하지 않는다.

### 기존 무지 품목이 앞으로 코드 공유 대상이 될 때만 사용하는 선택 절차

현재 등록된 품목은 설정을 바꾸지 않고 계속 사용한다. 나중에 기존 무지 품목의 ERP 코드를 다른 거래처도 사용하게 되는 경우에만 그 품목에 공유 관리 설정을 추가한다. 기존 ERP 코드가 일반 품목코드로 등록되어 있으면 신규 연결이 그 품목을 가로채지 못하도록 차단하므로, 해당 품목에서 `수정 → 무지 별도관리 → 저장`을 선택한다. 확인창을 거치며, 기존 품목 ID·코드·도면·재고·수주 참조는 그대로 유지한다. 이후 기존 사용 거래처와 추가 거래처를 연결한다. 같은 제품·도면이면 해당 품목에 함께 연결하고, 다른 도면의 거래처는 새 내부코드 품목에 연결한다. 무지로 전환한 품목은 일반 방식으로 되돌리거나 다른 도면으로 교체할 수 없다.

이 선택 절차를 사용하는 경우에만, 설정 변경과 거래처 연결 사이에 해당 코드의 새 수주 등록이 차단된다. 해당 품목의 수주 등록을 잠시 멈춘 동안 기존 사용 거래처를 포함한 연결까지 마친다. 과거 수주·재고 수정은 필요하지 않다. 이 절차를 사용하지 않는 기존 품목은 기존 등록 방식으로 계속 처리한다.

### A·B 같은 코드·다른 품명·같은 도면의 화면 예시

수정된 실제 WPF 화면과 ViewModel을 사용하며, API 응답은 네트워크에 연결하지 않는 메모리 예시 데이터로 구성했다. 운영 등록 결과나 실제 엑셀 파일을 읽은 결과가 아니다. 예시 파일명은 업로드 화면 설명용이다.

| 단계 | 입력·결과 | 화면 |
|---|---|---|
| 신규 품목 입력 | 무지 별도관리 선택, 공통 무지 상자, 도면 D-002, 제품사양 100×200, 라우팅 무지 도무송 | [입력](../output/unprinted-walkthrough/01-product-input.png) |
| 품목 저장 | MES-U000001 발급, 거래처 연결 버튼 활성화 | [저장 후](../output/unprinted-walkthrough/02-product-saved.png) |
| 거래처 추가 | A업체 연결 후 B업체를 선택해 같은 MUJI-100, B용 포장재 입력 | [B업체 입력](../output/unprinted-walkthrough/03-add-partner-b.png) |
| 연결 완료 | A업체 / MUJI-100 / A용 무지 상자, B업체 / MUJI-100 / B용 포장재가 한 품목에 연결됨 | [두 업체 연결](../output/unprinted-walkthrough/04-partners-linked.png) |
| 수주 검증 | A 1,000개, B 2,000개 모두 MES-U000001 / D-002, 정상 2건 | [수주 검증](../output/unprinted-walkthrough/05-orders-validated.png) |
| 수주 등록 후 조회 | 두 수주의 MES 코드·ERP 코드는 같고 거래처와 품명은 각각 유지됨 | [수주 목록](../output/unprinted-walkthrough/06-orders-registered.png) |

예시 재현을 위해 `frontend-wpf/tests/UnprintedProductRegression/Program.cs`에 실행 옵션을 추가하고 `SharedCodeWalkthrough.cs`를 추가했다. 업무용 화면·서버·DB 처리에는 변경이 없다. 예시의 품목 1건→연결 2건→수주 2건 흐름, 등록 요청의 연결 식별자, 업체별 품명 유지 및 화면 6장의 바인딩 오류 없음을 확인했다. 기존 무지 화면 회귀 검사 19건도 재실행하여 통과했다. 이미지 6장을 직접 확인했으며, 예시 데이터만 추가했으므로 백엔드 전체 테스트나 실제 업무 DB 등록은 재실행하지 않았다. NuGet 외부 피드의 취약성 조회 경고는 앞선 환경과 동일하다. 실제 업무 적용 시 입력하는 거래처·ERP 코드·도면 선택과 등록 결과는 별도로 확인해야 한다.

저장소 루트에서 재현:

```powershell
dotnet run --project frontend-wpf/tests/UnprintedProductRegression --no-restore -- --walkthrough output/unprinted-walkthrough
```

### 저장·조회 및 API 계약

- `POST /products`: 기존 요청은 동일하게 처리. `is_unprinted_managed=true`이면 `product_code`는 생략 또는 빈 문자열이며 서버가 발급한다. 도면 중복이면 새 품목 생성 대신 기존 품목의 거래처 연결을 안내한다.
- `PATCH /products/{id}`: `is_unprinted_managed=true`로 기존 품목의 명시적 전환. 일반 요청에서 필드를 생략하면 기존 모드를 유지한다.
- `GET /products/{id}/partner-mappings?page=1&size=20`: 활성 연결 기본 조회. `include_inactive=true`이면 해제 이력 포함. 품목 조회 권한을 따른다.
- `POST /products/{id}/partner-mappings`: `partner_id`, `erp_product_code`, `customer_product_name`, 선택 `customer_product_spec`. 서버가 코드 공백/대소문자를 정규화한다. 등록자와 시각을 저장한다.
- `DELETE /products/{id}/partner-mappings/{mapping_id}`: 해당 품목에 속한 연결만 사용 중지. 반복 호출은 기존 해제 이력을 변경하지 않는다. 등록/해제는 `PRODUCTS.WRITE` 권한 필요.
- 기존 수주 벌크 검증 응답에 `mes_product_code`, `drawing_no`, `mapping_id`, `is_unprinted_managed`를 추가했다. 등록의 `row_choices`는 `expected_product_id`, `expected_mapping_id`를 함께 전송한다. 구버전 클라이언트는 기존 인쇄 수주를 계속 등록할 수 있지만 무지 연결 수주는 재검증/클라이언트 업데이트가 필요하다.
- 신규 무지 수주의 ERP 코드·품명·규격은 `order_line.source_*`에 저장한다. 엑셀 수주는 엑셀에 적힌 당시 값을, 직접 입력 수주는 연결에 등록된 값을 사용한다. 기존 수주는 null 상태를 유지한다.
- 수주 목록·상세·생산일보는 수주 당시 품명을 우선 표시한다. 재고·공통 품목 조회는 공통 마스터를 유지한다. 외주/검사/출하 문서 전체의 품명 표시 체계를 변경하는 작업은 이번 범위에 포함하지 않는다.
- 직접 입력 수주에서 선택 거래처/무지 품목의 활성 연결이 없거나 여러 ERP 코드로 연결되어 있으면 등록을 막는다. 여러 ERP 코드인 경우 엑셀 등록으로 정확한 코드를 지정한다. 등록한 무지 수주의 거래처/품목 변경은 차단하며 필요하면 취소 후 다시 등록한다.

### DB 무결성과 동시성

- 활성 거래처+ERP 코드의 유일성은 PostgreSQL 부분 UNIQUE 인덱스로 보장한다. 파트너/품목 FK는 RESTRICT다.
- 서버 내부코드는 단일 카운터의 원자적 증가로 발급하며 트랜잭션 롤백에 포함된다. 기존 코드와 충돌하면 다음 번호를 사용한다.
- 일반 품목 등록과 무지 연결 등록 사이의 ERP 코드 충돌은 같은 코드에 대한 트랜잭션 잠금으로 직렬화한다. 일반 품목 엑셀 등록에도 같은 검증을 적용한다.
- 수주 저장은 연결을 잠그고 품목 상태를 다시 확인한다. 진행 중 연결 해제를 기다리게 하며, 미리 검증한 연결이 바뀌었으면 재검증을 요청한다.
- 수주 ERP 원본은 DB CHECK로 코드와 품명이 함께 있거나 모두 비어 있도록 제한한다. 품목-도면 UNIQUE는 유지한다.

### 실행한 검증

- 전체 백엔드 회귀: **426 passed, 10 skipped, 112 subtests passed**. 이 최종 실행에는 새로운 PostgreSQL 검증, 무지 서비스 16건 및 API 계약 2건이 포함된다. 결과 로그: `output/unprinted-tests/backend-validation.txt`.
- 무지 API 계약/조회/등록/해제/권한 거부 테스트 2건 통과. 추가 HTTP 라이브러리 없이 ASGI 요청으로 확인했다.
- 격리 PostgreSQL 17: 전체 이전 마이그레이션부터 구성 → 기존 인쇄 품목/수주/재고를 입력 → 새 마이그레이션 → 모든 기존 컬럼 값과 타임스탬프 보존 비교 → 사용 전 downgrade/upgrade → 사용 후 downgrade 차단 확인.
- `alembic check` 업그레이드 직후와 동시성 검증 후 모두 통과. 카운터 동시 발급 4건의 서로 다른 코드, 동일 거래처/코드 동시 연결 2건 중 1건만 성공, 수주 매칭 잠금 중 연결 해제 차단을 확인했다.
- WPF 빌드 성공. 신규 `UnprintedProductRegression` **19개 검사 통과**, 기존 `OrderLineRegression` **30개 검사 통과**. 실제 컨트롤의 렌더링/바인딩 오류 없음. 실패 입력 보존, 중복 저장 방지, 전환 취소, 서버 발급 번호 선택, 연결 페이지 이동, 등록 요청의 연결 ID 전송을 확인했다.
- 화면 검증 결과: `output/unprinted-tests/product-registration.png`, `partner-mappings.png`, `order-auto-match.png`. 예시 데이터를 사용해 실제 WPF 컨트롤을 렌더링한 이미지다.
- 코드 형식 검증: `git diff --check`.

적용 범위 확정 후에는 품목 화면 안내와 이 문서, `project-operations.md`, `database-architecture.md`를 수정했다. 기존 품목 전체의 전환·재고 확인을 도입 조건으로 오해하지 않도록 바로잡았으며, 서버 처리와 DB 구조는 바꾸지 않았다. WPF 무지 회귀 검사 19건과 `git diff --check`를 다시 실행하여 통과했다. 서버 로직 변경이 없어 백엔드 전체 검증은 재실행하지 않았으며, 위 426건 결과는 앞선 구현 검증 결과다. 운영 배포는 여전히 수행하지 않았다. 배포 후 처음 등록하는 공유 대상의 거래처·ERP 코드·도면 선택과 수주 매칭을 확인한다.

검증 재실행:

```powershell
# backend에서 실행. 기본은 SQLite/메모리 테스트이며 전용 PG 테스트는 명시적으로 활성화한다.
.venv/Scripts/python.exe -m pytest -q
# 전용 로컬 DB만 허용: host=127.0.0.1, port=55440, user/database=mes_unprinted_test
$env:MES_UNPRINTED_TEST_DATABASE_URL = 'postgresql+psycopg://mes_unprinted_test@127.0.0.1:55440/mes_unprinted_test'
.venv/Scripts/python.exe -m pytest tests/test_unprinted_postgres.py -q
# 저장소 루트에서 실행
dotnet run --project frontend-wpf/tests/UnprintedProductRegression -- output/unprinted-tests
dotnet run --project frontend-wpf/tests/OrderLineRegression --no-restore
```

### 미실행 검증·남은 위험·수동 확인

- 아래의 초기 개발 검증 범위 이후, 로컬 개발 DB에는 다음 절차로 마이그레이션을 적용했다. 별도 운영 서버 배포는 여전히 수행하지 않았다.
- 전체 실행에서 건너뛴 10건은 기존 검사/재고/작업큐용 별도 PostgreSQL 환경을 요구하는 9건과 Windows 심볼릭 링크 권한을 요구하는 1건이다. 이번 무지 관리용 PostgreSQL 검증은 별도 DB에서 실제 실행했다.
- NuGet 취약성 조회는 외부 피드 접속 실패로 `NU1900` 경고가 남았다. 기존 패키지로 빌드/실행은 성공했으며 새 런타임 의존성을 추가하지 않았다. 배포 환경에서 취약성 조회를 재확인한다.
- 실제 업무/운영 DB 마이그레이션, 실제 거래처 연결 작성, 운영 클라이언트 배포는 수행하지 않았다. 격리된 테스트 환경에서 검증했다.
- 앞으로 등록하는 공유 대상의 거래처가 같은 제품·도면을 사용하면 같은 품목에 연결하여 재고도 함께 관리한다. 도면이 다르면 별도 품목으로 관리한다. 기존 재고를 이동하거나 나눌 필요는 없다.
- 연결할 때 해당 거래처가 사용할 품목·도면을 선택한다. 이는 새 연결의 입력 내용이며 기존 품목 전체를 재점검하는 절차가 아니다. 한 업체에만 적용하는 도면 변경은 새 도면/품목으로 분리하며, 공유 도면의 개정은 연결된 모든 거래처에 영향을 줄 수 있다.
- 배포 후 권한별 신규 품목 등록/연결/해제, A·B 같은 도면 및 C 다른 도면의 수주 자동 매칭, 기존 인쇄 등록/수주, 조회 화면의 업무 품명 표시를 수동 확인한다. 기존 품목의 일괄 전환이나 거래처 연결 입력은 도입 조건이 아니다.

### 로컬 테스트 중 품목 조회 오류 조치 — 2026-10-19

- 증상: 품목 목록에서 `psycopg.errors.UndefinedColumn: product.is_unprinted_managed`와 HTTP 500 발생.
- 원인: 새 기능 코드가 실행되는 동안 로컬 개발 DB `127.0.0.1:5432/mes_db`는 직전 마이그레이션 `7c8d9e0f1a2b`였다. 무지 관리용 컬럼과 연결 테이블이 아직 없었다.
- 적용 계획: 로컬/비운영 환경과 현재 리비전 확인 → DB·스토리지 백업 → 기존 값 비교용 해시 기록 → 누락된 `8d9e0f1a2b3c` 한 건 적용 → 기존 값 보존·조회·스키마 정합성 확인. 기존 품목 전환이나 데이터 수정은 수행하지 않는다. 마이그레이션은 트랜잭션 DDL과 5초 잠금 제한을 사용한다.
- 백업: `C:\Users\jaewon\Documents\Codex\mes-v1.5-db-safety\unprinted-management-20261019\mes_20261019T045812Z`. DB dump 828,797바이트, 파일 2,432,116,698바이트. 기존 백업 도구의 `pg_restore --list`, 파일 해시 검증 및 적용 직전 dump SHA-256 재검증 통과. 온라인 백업이므로 DB와 파일이 단일 시점의 원자적 스냅샷이라는 의미는 아니다.
- 결과: 로컬 DB 리비전 `8d9e0f1a2b3c`. 버전 관리 테이블을 제외한 기존 52개 테이블의 **모든 기존 컬럼**을 적용 전후 행 해시로 비교하여 변경 없음 확인. 품목 1,119건, 도면 1,356건, 수주 622건, LOT 647건, 품목 재고 560건, 재고 이동 1,446건 유지. 무지 관리 전환 0건, 거래처 연결 0건, 기존 수주 원본 추가 0건이며 발급 카운터는 1에서 시작한다.
- 오류 재검증: 실제 품목 목록 서비스 호출 성공, 사용 중인 품목 총 1,110건 중 첫 페이지 100건 반환. 전체 품목 1,119건과 차이는 사용 여부 필터다. `alembic check`도 추가 변경 없음으로 통과했다.
- 변경 파일: 업무 소스와 마이그레이션 파일은 추가 수정하지 않았다. 이 문서, `docs/project-operations.md`, `docs/database-architecture.md`에 로컬 적용 상태를 반영했다. 비교용 임시 스크립트와 해시 결과는 Git 제외 경로 `.tmp/unprinted-db-fix-20261019/`에 보관한다. DB 구조도는 기존 설계와 같아 수정하지 않았다.
- 이번에 실행하지 않은 검증: 백업의 전체 복원 재연습, 데스크톱 클라이언트를 직접 조작하는 등록 테스트, 백엔드 전체 회귀 재실행. 이번 조치는 이미 검증한 마이그레이션의 적용 누락을 해소한 것이며, 실제 DB 비교·조회와 구조 검증에 집중했다. 별도 운영 서버는 변경하지 않았다.
- 남은 확인: 사용자는 품목 화면을 다시 열거나 `조회`를 눌러 정상 표시를 확인한다. 새 공유 품목의 거래처 연결은 실제 사용하려는 거래처·코드·도면으로 입력한다. 새 기능 사용 이력이 생긴 후에는 데이터를 삭제하는 downgrade가 차단되므로 되돌려야 할 때 전진 수정 또는 별도 복구 계획이 필요하다.

### 변경 파일과 이유

아래는 이번 요청으로 변경/추가한 파일이며, 사용자가 기존에 작성해 둔 검사 매뉴얼과 출력 파일은 수정하지 않았다.


**서버 모델·API·업무 처리: 무지 구분, 코드 발급, 연결 무결성, 수주 매칭/원본 보존**

- `backend/app/api/v1/products.py`
- `backend/app/models/__init__.py`
- `backend/app/models/order_line.py`
- `backend/app/models/partner_product_mapping.py`
- `backend/app/models/product.py`
- `backend/app/schemas/order_line.py`
- `backend/app/schemas/order_line_detail.py`
- `backend/app/schemas/partner_product_mapping.py`
- `backend/app/schemas/product.py`
- `backend/app/services/bulk/order_line_bulk_service.py`
- `backend/app/services/bulk/product_bulk_service.py`
- `backend/app/services/order_line_creation_service.py`
- `backend/app/services/order_line_detail_query.py`
- `backend/app/services/order_line_list_query.py`
- `backend/app/services/order_line_response_builder.py`
- `backend/app/services/order_line_update_service.py`
- `backend/app/services/partner_product_mapping_service.py`
- `backend/app/services/product_query.py`
- `backend/app/services/product_registration_service.py`
- `backend/app/services/production_daily_query.py`

**DB 마이그레이션: 기존 데이터 보존과 안전한 복구**

- `backend/migrations/versions/8d9e0f1a2b3c_unprinted_product_management.py`

**서버 회귀·계약·동시성 검증**

- `backend/tests/test_order_line_services.py`
- `backend/tests/test_product_query.py`
- `backend/tests/test_unprinted_postgres.py`
- `backend/tests/test_unprinted_product_api.py`
- `backend/tests/test_unprinted_product_management.py`

**WPF 화면·요청/응답: 등록, 연결 관리, 수주 표시**

- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLineList/Dtos/OrderLineDetailDto.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLineList/Dtos/OrderLineListItemDto.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLineList/ViewModels/OrderLineDetailPageViewModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLineList/Views/OrderLineDetailPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLineList/Views/OrderLineListPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLines/Dtos/OrderLineBulkImportDtos.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLines/ViewModels/OrderLineBulkImportPageViewModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLines/Views/OrderLineBulkImportPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/Dtos/PartnerProductMappingDto.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/Dtos/ProductCreateRequest.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/Dtos/ProductDto.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/Dtos/ProductEditModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/Dtos/ProductUpdateRequest.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/ViewModels/PartnerProductMappingViewModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/ViewModels/ProductPageViewModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/Views/PartnerProductMappingWindow.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/Views/PartnerProductMappingWindow.xaml.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/Views/ProductPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Products/Views/ProductPage.xaml.cs`

**WPF 동작·화면 검증**

- `frontend-wpf/tests/UnprintedProductRegression/Program.cs`
- `frontend-wpf/tests/UnprintedProductRegression/SharedCodeWalkthrough.cs`
- `frontend-wpf/tests/UnprintedProductRegression/UnprintedProductRegression.csproj`

**운영 절차·DB 구조 문서**

- `docs/database-architecture.md`
- `docs/database-schema.svg`
- `docs/project-operations.md`
- `docs/unprinted-product-management-2026-10-19.md`


### 품목코드 기본 표시 후속 변경 파일

서버 조회/응답은 수주 원본 코드를 기본으로 제공하고 MES 코드를 분리한다. 화면/DTO는 이를 표시하며, 테스트는 코드 공유와 기존 데이터 호환을 검증한다. 아래 목록은 이번 표시 변경에 해당하는 파일이다. 앞선 무지 등록/매칭 기능 파일 목록과는 범위를 구분한다.

- `backend/app/crud/lot.py`
- `backend/app/schemas/inspection_result.py`
- `backend/app/schemas/inspection_schedule.py`
- `backend/app/schemas/lot.py`
- `backend/app/schemas/lot_create_context.py`
- `backend/app/schemas/order_line.py`
- `backend/app/schemas/order_line_detail.py`
- `backend/app/schemas/outsource_work_instruction.py`
- `backend/app/schemas/production_daily.py`
- `backend/app/schemas/shipment.py`
- `backend/app/services/bohyun_outsource_service.py`
- `backend/app/services/inspection_result_query.py`
- `backend/app/services/inspection_work_instruction_query.py`
- `backend/app/services/lot_query.py`
- `backend/app/services/lot_rework_service.py`
- `backend/app/services/lot_trace_query.py`
- `backend/app/services/order_line_detail_query.py`
- `backend/app/services/order_line_display.py`
- `backend/app/services/order_line_list_query.py`
- `backend/app/services/order_line_lot_context_query.py`
- `backend/app/services/order_line_response_builder.py`
- `backend/app/services/outsource_purchase_order_query.py`
- `backend/app/services/outsource_work_instruction_query.py`
- `backend/app/services/production_daily_query.py`
- `backend/app/services/shipment_list_query.py`
- `backend/tests/test_product_code_display.py`
- `docs/database-architecture.md`
- `docs/project-operations.md`
- `docs/unprinted-product-management-2026-10-19.md`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/BohyunOutsourceManagement/Dtos/BohyunOutsourceDtos.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/BohyunOutsourceManagement/Dtos/BohyunOutsourceWorkDoneEditModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/BohyunOutsourceManagement/Views/BohyunOutsourceManagementView.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/BohyunOutsourceManagement/Views/BohyunOutsourceShipmentListView.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/BohyunOutsourceManagement/Views/BohyunOutsourceWorkDoneWindow.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Dtos/InspectionResultDtos.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Dtos/InspectionResultManagementDtos.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Dtos/InspectionScheduleListItemDto.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Dtos/InspectionScheduleManagementEditModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Dtos/InspectionWorkInstructionEditModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Dtos/InspectionWorkInstructionLotListItemDto.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/ViewModels/InspectionResultWindowViewModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Views/InspectionResultManagementView.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Views/InspectionResultWindow.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Views/InspectionScheduleManagementView.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Views/InspectionWorkInstructionPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/LotDetails/Dtos/LotDetailDtos.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/LotDetails/ViewModel/LotDetailWindowViewModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/LotDetails/Views/LotDetailWindow.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Lots/Dtos/LotCreateContextDto.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Lots/Dtos/LotCreateEditModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Lots/Dtos/LotDto.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Lots/Dtos/LotOrderLineLookupDto.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Lots/Dtos/LotProcessDtos.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Lots/Views/LotCreateWindow.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Lots/Views/LotPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLineList/Dtos/OrderLineDetailDto.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLineList/Dtos/OrderLineListItemDto.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLineList/ViewModels/OrderLineDetailPageViewModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLineList/Views/OrderLineDetailPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLineList/Views/OrderLineListPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OrderLines/Views/OrderLineBulkImportPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OutsourceWorkInstructions/Dtos/OutsourcePurchaseOrderDtos.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OutsourceWorkInstructions/Dtos/OutsourceWorkGroupDtos.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OutsourceWorkInstructions/Dtos/OutsourceWorkInstructionDtos.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OutsourceWorkInstructions/Views/OutsourcePurchaseOrderPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OutsourceWorkInstructions/Views/OutsourceWorkGroupListPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/OutsourceWorkInstructions/Views/OutsourceWorkInstructionPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/ProductionDaily/Dtos/ProductionDailyDtos.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/ProductionDaily/Views/ProductionDailyPage.xaml`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Shipments/Dtos/ShipmentDtos.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Shipments/ViewModels/ShipmentPageViewModel.cs`
- `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/Shipments/views/ShipmentPage.xaml`
- `frontend-wpf/tests/UnprintedProductRegression/SharedCodeWalkthrough.cs`
