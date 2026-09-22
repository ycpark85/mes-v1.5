# 최종검수 미달 사유 제거 — 2026-09-22

같은 날 후속 변경으로 검수실적의 출고목표 초과 제한도 제거했다. 아래 최초 변경 당시의 출고목표 제한 유지 설명은 [출고목표 초과 저장 허용](inspection-over-target-shipment-2026-09-22.md)으로 대체한다. 미달 사유 제거와 그 검증 결과는 그대로 유효하다.

사용자 요청에 따라 LOT 계획보다 실제 누적 처리수량이 적어도 미달 사유 없이 최종검수를 저장한다. 작업자의 추가 입력을 없애기 위해 화면 입력란과 화면·서버 필수 검증을 함께 제거했다. 이 기록은 이전 날짜의 문서에 남아 있는 미달 사유 필수 규칙보다 우선한다.

## 변경한 동작

- 신규 최종검수와 기존 최종 실적 수정 모두 LOT 계획 미달만으로 차단하지 않는다.
- 계획수량과의 차이를 불량이나 미검수로 채우지 않는다. 실제 입력한 수량과 원래 LOT 계획을 보존한다.
- 미달 사유 입력란을 제거했다. 기존 사유를 지우지 않도록 선택 API 필드와 과거 이력 표시는 유지하며, WPF에서 기존 실적 수정 시 저장된 사유를 그대로 전달한다. 신규 실적은 `shortage_reason=null`을 전송한다.
- 처리수량 0, 음수, 배분 불일치, 재고 부족, 출고목표 초과, 분할검수의 다음 날짜·사유 누락에 대한 검증은 유지한다.
- 검수 LOT 종료와 발주 완료는 별도로 판단한다. 출고목표를 충족하지 못한 발주를 계획 미달 검수 저장만으로 완료하지 않는다.
- DB 구조·마이그레이션·의존성·운영 배포는 변경하지 않았다.

## 변경 파일

| 파일 | 변경 이유 |
|---|---|
| `backend/app/services/inspection_result_service.py` | LOT 계획 미달 사유 검증과 그 검증에만 사용하던 누적 조회 제거. LOT 존재·잠금·처리수량 검증 유지 |
| `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Services/InspectionResultFormPolicy.cs` | 미달 사유 필수 검증 및 전용 검증 문맥 필드 제거. 빈 사유는 null로 전송 |
| `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/ViewModels/InspectionResultWindowViewModel.cs` | 제거된 계획 비교 검증에 대한 문맥 전달 정리 |
| `frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/Views/InspectionResultWindow.xaml` | 최종검수 미달 사유 입력란 제거 |
| `backend/tests/test_inspection_result_service.py` | 사유 없는 계획 미달 등록·수정, 실제 수량·재고·LOT 계획 보존, 처리수량 0 거절 검사 |
| `frontend-wpf/tests/InspectionRegression/Program.cs` | 사유·추가 경고 없는 저장 요청, 처리수량 0 거절, 과거 사유 보존 검사 |
| `docs/project-operations.md` | 현재 운영 규칙 갱신 |
| `docs/inspection-manual-checklist-2026-09-14.md` | 변경한 업무 규칙에 맞춘 수동 확인 항목 |
| `docs/inspection-shortage-reason-removal-2026-09-22.md` | 이번 변경·검증·적용 범위 기록 |

기존 개발 변경이 있는 작업 폴더에서 위 범위만 수정했다. 이 표는 이번 작업의 변경분이며 기존 미커밋 변경 전체를 나타내지 않는다.

## 자동 검증

- 수정 전 새 테스트가 백엔드의 422 미달 사유 오류 및 WPF 저장 차단으로 각각 실패하는 것을 확인했다.
- 백엔드: `tests.test_inspection_result_service`, `tests.test_inspection_quantity_policy`, `tests.test_inspection_shared_quantity_cases`, `tests.test_inspection_inventory_policy`의 **30개 테스트 통과**. 메모리 SQLite의 합성 자료를 사용했다.
- 계획 80에서 실제 79를 사유 없이 등록하고, 같은 실적을 양품 70·불량 2·미검수 3으로 수정했다. 누적 처리수량 75, 재고 70, LOT 계획 80을 보존하고 빈 사유를 허용함을 확인했다.
- WPF `InspectionRegression`: **80개 검사 통과**. 실제 화면 ViewModel과 가짜 API를 사용해 계획 535,000에서 양품 432,000의 최종 저장 요청이 사유와 추가 경고 없이 전송됨을 확인했다.
- WPF 개발용 Debug 전체 빌드: **오류 0, 경고 0**.

## 미실행 검증·남은 위험·수동 확인

- 실제 업무 DB에 저장하거나 운영 서버에 접속·배포하지 않았다. 업무자료를 변경하지 않는 합성 자료 검증 범위다.
- 실제 PostgreSQL과 실행 중인 프로그램 화면에서 이번 변경을 확인하지 않았다. DB 스키마는 변경하지 않았으며, 자동 검증은 저장 서비스와 WPF 화면 로직·빌드까지 포함한다.
- 실행 중인 이전 WPF 또는 백엔드는 기존 제한을 계속 적용할 수 있다. 최신 개발 실행본으로 재실행하고 개발 백엔드에도 변경 코드가 로드되었는지 확인해야 한다.
- 수동 확인은 독립된 개발 검증용 LOT에서 입력란 제거, 계획 미달 저장·재조회·수정, 실제 수량 및 재고 반영을 확인한다. 이미 입력한 업무자료를 임의로 바꾸어 시험하지 않는다.
