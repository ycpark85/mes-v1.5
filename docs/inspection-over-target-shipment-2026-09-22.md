# 검수실적 출고목표 초과 저장 허용 — 2026-09-22

출고목표보다 많이 생산한 물량을 모두 출고할 수 있도록, 검수실적 저장의 목표 초과 제한을 화면과 서버에서 제거했다. 예를 들어 출고목표 100, 생산 양품 120일 때 생산 출고 120으로 저장한다. 목표를 늘리거나 실제 출고를 100으로 줄이지 않는다.

## 적용 범위와 업무 규칙

- 신규·수정·분할·최종검수 모두 출고목표 초과만으로 저장을 거절하지 않는다. 기존 회차가 목표를 이미 넘겼어도 다음 회차 출고를 허용한다.
- 기존재고 출고와 생산 출고의 합계도 목표를 넘을 수 있다. 기존재고는 실제 사용가능량, 생산출고는 판매가능수량의 배분 검증을 따른다.
- 생산출고 + 재고편입 + 판매가능폐기는 정산할 판매가능수량과 일치해야 한다. 출고량을 자동으로 채우거나 잘라내지 않는다.
- 출고목표는 기존 값을 표시하고, 실제 출고는 원장에 기록된 전량을 표시한다. 잔여 출고만 0을 하한으로 표시한다.
- 계획 미달 사유는 이전 변경대로 필수가 아니다. 분할검수 사유·다음 검수일, 처리수량 0·음수 차단, 재고 부족·다른 발주 예약 보호, 발행 성적서·COA 보호, 동시 수정 검증은 유지한다.
- 발주 완료는 기존대로 모든 유효 LOT 완료와 출고목표 충족 여부로 판단한다. 초과 출고했더라도 분할검수가 남아 있으면 해당 LOT를 최종완료로 바꾸지 않는다.
- 별도 출고확정 메뉴의 목표 검증은 이번 검수실적 요청 범위에 포함하지 않았다. 운영 서버, 업무 DB, 스키마와 의존성은 변경하지 않았다.

## 변경 파일

| 파일 | 변경 이유 |
|---|---|
| `backend/app/services/inspection_inventory_service.py` | 검수 저장 시 남은 출고목표 비교와 그 비교에만 쓰던 조회·import 제거 |
| `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Services/InspectionResultFormPolicy.cs` | 목표 초과 필수 검증과 전용 검증 문맥 필드 제거 |
| `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/ViewModels/InspectionResultWindowViewModel.cs` | 제거한 검증 문맥 전달 정리. 목표·실제 출고·잔여량 표시 유지 |
| `backend/tests/test_inspection_result_service.py` | 전량 초과 출고, 증가 수정·동일값 재저장, 분할·후속 최종회차, 기존재고 합산 및 조회 검증 |
| `frontend-wpf/tests/InspectionRegression/Program.cs` | 목표 초과 요청 허용과 기존 배분·재고 부족 차단 검증 |
| `docs/project-operations.md` | 현재 검수 출고 규칙과 잔여 출고 계산 설명 갱신 |
| `docs/inspection-manual-checklist-2026-09-14.md` | 실제 개발 화면에서 확인할 초과 출고 사례 반영 |
| `docs/inspection-shortage-reason-removal-2026-09-22.md` | 같은 날 이전 작업의 출고 제한 설명에 후속 변경 안내 |
| `docs/inspection-over-target-shipment-2026-09-22.md` | 이번 변경 범위·검증·남은 확인 기록 |

기존 미커밋 개발 변경을 유지하고 위 항목만 수정했다.

## 검증 결과

수정 전에 새 백엔드·WPF 검사가 기존 출고목표 제한으로 실패하는 것을 확인했다.

- 백엔드 관련 64개 테스트 중 **58개 통과, PostgreSQL 전용 6개 건너뜀**. 검수 저장·조회, 수량 배분, 재고 정정과 기존 보호 규칙을 합성 SQLite 자료로 검사했다.
- 목표 100에서 양품 120 전량 출고 → 양품·출고 130으로 수정 → 동일값 재저장을 검증했다. 목표와 LOT 계획을 유지하고, 출고 합계 130·재고 0으로 반영하며 재저장에 따른 원장·출고 중복이 없음을 확인했다.
- 목표 100에서 분할 회차 120 출고 후 다음 최종회차에 생산 20 + 기존재고 10을 추가 출고했다. 누적 출고 150, 기존재고 65 → 55, 잔여 출고 0, 분할 시 발주 진행 유지·최종 시 완료를 확인했다.
- WPF `InspectionRegression`: **83개 검사 통과**. 목표 초과 신규·수정·분할 요청이 추가 경고 없이 전달되고, 생산 배분 초과와 기존재고 부족은 차단됨을 확인했다.
- WPF 개발용 Debug 전체 빌드: **오류 0, 경고 0**.

백엔드 실행 모듈: `tests.test_inspection_result_service`, `tests.test_inspection_result_query`, `tests.test_inspection_quantity_policy`, `tests.test_inspection_shared_quantity_cases`, `tests.test_inspection_inventory_policy`, `tests.test_inspection_corrections`.

## 미실행 검증·남은 위험·수동 확인

- 전용 PostgreSQL을 연결하지 않아 실제 DB 동시성·읽기 전용 세션·스키마 이력 검증 6개는 건너뛰었다. 이번 변경은 DB 구조와 잠금 순서를 바꾸지 않는다.
- 실제 업무 DB 저장, 실행 화면 수동 확인, 운영 배포는 하지 않았다. 자동 검사는 합성 DB와 가짜 API를 사용한다.
- 이전 화면 또는 백엔드를 계속 실행하면 기존 제한이 남는다. 최신 개발 실행본과 변경된 백엔드로 재실행한 뒤 개발 검증용 LOT에서 전량 초과 출고 저장·재조회, 증가 수정, 재고 차감을 확인한다.
- 운영 반영은 별도 배포 작업이며, 현재 작업 폴더의 다른 미커밋 변경까지 함께 운영 적용한 상태가 아니다.
