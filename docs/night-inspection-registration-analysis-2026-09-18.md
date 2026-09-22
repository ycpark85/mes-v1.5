# 야간 검수실적 등록 제약 분석

확인일: 2026-09-18, 한국시간 기준. 현재 개발 소스와 개발 설정을 읽고 합성 데이터로 재현했다. 운영 서버의 실행 버전·환경변수·장애 로그는 이번 분석에서 직접 조회하지 않았다. 프로그램 코드·환경설정·업무 DB·시스템 시각을 변경하지 않았다.

## 판단

현재 코드에는 **오후 8시 이후 검수실적 저장을 금지하는 업무 규칙이 없다.** 다만 로그인 후 **12시간이 지나면 인증이 만료되는 설정**이 확인됐다. 오전 8시에 로그인해 계속 사용하는 경우 오후 8시 정각부터 검수실적 저장을 포함한 인증 요청이 거부될 수 있다. 운영 현상의 유력한 원인이지만 운영 로그와 설정 확인 전에는 실제 원인으로 확정할 수 없다.

## 확인한 조건

| 항목 | 확인 결과 | 영향 |
|---|---|---|
| 오후 8시 고정 제한 | 검수 저장·수량 검증·화면 저장 명령에서 발견되지 않음 | 유효한 로그인과 정상 입력이면 일반·분할검수 저장 가능 |
| 로그인 유효시간 | 소스 기본값, 개발 설정, 예제 설정 모두 720분 | 로그인 후 12시간에 만료. 사용 중이어도 기존 토큰의 만료가 연장되지 않음 |
| 만료 응답 | 서버에서 401과 `인증 정보가 올바르지 않습니다.` 반환 | 저장 업무 처리에 도달하기 전에 거부됨 |
| WPF 만료 대응 | 자동 갱신·만료 전 안내·입력 유지 재로그인 흐름을 찾지 못함 | 화면이 열려 있어도 만료된 인증을 계속 사용하며 오류가 반복될 수 있음 |
| 자정 이후 검수 시작 | 스케줄 검수일과 서버의 한국 날짜가 같아야 함 | 전날의 미시작 스케줄은 자정 이후 시작 시 409로 거부 |
| 시작된 검수의 저장 | 저장 경로에는 오늘 날짜 제한이 없음 | 이미 진행 중인 검수는 날짜가 넘어가도 수량·상태 등 조건을 충족하면 저장 가능 |
| 야간 예약 작업 | 저장소 예제 백업 시각은 02:00. 예약 실행기는 online 백업이며 API 중지 코드를 호출하지 않음 | 운영 PC의 실제 예약 시간·다른 작업·부하 여부는 미확인 |

인증 만료는 검수 화면에만 적용되지 않는다. 만료 후 재고 조회 등도 실패할 수 있다. 검수 화면을 새로 열 때 조회가 실패하면 별도로 저장을 막는 보호 조건도 적용돼, 여러 오류가 연이어 발생한 것으로 보일 수 있다.

## 코드 근거

- [config.py:34](C:/Users/jaewon/Documents/Codex/mes-v1.5/backend/app/core/config.py:34): `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` 기본 720분.
- [auth.py:75](C:/Users/jaewon/Documents/Codex/mes-v1.5/backend/app/core/auth.py:75): 로그인 시각에 유효시간을 더해 만료 시각을 고정한다.
- [auth.py:126](C:/Users/jaewon/Documents/Codex/mes-v1.5/backend/app/core/auth.py:126): 현재 시각이 만료 시각 이상이면 인증을 거부한다. 같은 파일의 인증 예외 응답은 일반적인 인증 오류 문구다.
- [ApiClient.cs:313](C:/Users/jaewon/Documents/Codex/mes-v1.5/frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Infrastructure/Api/ApiClient.cs:313): 401 응답을 일반 실패 결과로 전달한다. 인증을 새로 발급받는 동작이 없다.
- [InspectionResultWindowViewModel.cs:674](C:/Users/jaewon/Documents/Codex/mes-v1.5/frontend-wpf/Mes.WpfClean/Mes.Wpf/Mes.Wpf/Modules/InspectionSchedules/ViewModels/InspectionResultWindowViewModel.cs:674): 조회 실패 시 저장 보호 상태로 전환한다. 저장 실패 시에도 서버 오류를 표시하며 재로그인 흐름은 없다.
- [inspection_schedule_service.py:322](C:/Users/jaewon/Documents/Codex/mes-v1.5/backend/app/services/inspection_schedule_service.py:322): 검수 시작은 서버 한국 날짜와 선택 검수일이 일치해야 한다. PostgreSQL에서는 DB의 `CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul'` 날짜를 사용한다.
- [inspection_result_service.py:121](C:/Users/jaewon/Documents/Codex/mes-v1.5/backend/app/services/inspection_result_service.py:121): 저장은 수량·검수 상태·수정 버전 등을 검증하며, 현재 시각은 완료·정산 기록 등에 사용한다. 시간대에 따른 저장 금지는 없다.
- [Set-MesOperationsScheduledTasks.ps1:58](C:/Users/jaewon/Documents/Codex/mes-v1.5/deploy/windows/Set-MesOperationsScheduledTasks.ps1:58), [Invoke-MesScheduledOperation.ps1:23](C:/Users/jaewon/Documents/Codex/mes-v1.5/deploy/windows/Invoke-MesScheduledOperation.ps1:23): 설정된 시각에 online 백업을 실행한다. 운영 등록 상태를 확인한 결과는 아니다.

## 재현 결과

시스템 시각을 바꾸지 않고 테스트 내부의 시계만 바꿨다. 토큰은 합성 사용자·시험용 서명 키로 생성했고 외부에 출력하지 않았다. DB 검증은 SQLite 메모리에 생성한 합성 자료만 사용했다.

| 시험 조건 | 결과 |
|---|---|
| 08:00 로그인 → 19:59:59 요청 | 인증 허용 |
| 08:00 로그인 → 20:00:00 / 20:00:01 / 23:00 요청 | 401 인증 거부 |
| 09:00 로그인 → 20:30 요청 | 인증 허용. 20시 고정 제한과 구분됨 |
| 20:01 재로그인 → 20:01:01 / 다음 날 02:00 요청 | 인증 허용 |
| 실제 검수 저장 API 경로에 만료 인증 전달 | 401. 저장 서비스·DB 조회·commit 미호출 |
| 같은 API 경로에 새 인증 전달 | 합성 저장 응답 200. 이 HTTP 시험의 저장 서비스는 대체했고 실제 저장은 다음 시험에서 별도로 확인 |
| 19:59:59, 20:00, 21:00, 23:59:59, 다음 날 00:01에 실제 저장 서비스 호출 | 일반검수·분할검수 10가지 모두 저장 및 재고편입 성공 |
| 당일 스케줄을 20:00 / 23:59:59에 시작 | 허용 |
| 같은 전날 스케줄을 다음 날 00:01에 시작 | 409, `오늘 스케줄만 검수를 시작할 수 있습니다.` |

신규 진단 21건과 기존 인증·시간·검수 시작 검증 22건을 합쳐 **43 passed**. 결과는 [results.xml](C:/Users/jaewon/Documents/Codex/mes-v1.5/.tmp/night-registration-analysis-20260918/results.xml), 재현 코드는 [test_night_registration.py](C:/Users/jaewon/Documents/Codex/mes-v1.5/.tmp/night-registration-analysis-20260918/test_night_registration.py)에 보관했다. DB의 PostgreSQL 날짜 표현은 코드와 기존 테스트로 확인했으며 이번 진단에서 PostgreSQL 인스턴스는 시작하지 않았다.

## 운영에서 원인을 확정할 확인 순서

1. 실제 실행 중인 서버의 로그인 유효시간 설정과 WPF·서버 버전을 확인한다. 개발 설정과 같다고 가정하지 않는다.
2. 문제가 난 사용자의 로그인 성공 시각과 오류 시각을 비교한다. 매번 로그인 후 약 12시간인지, 로그인 시각과 무관하게 모든 PC가 20시에 실패하는지 구분한다.
3. 해당 요청 ID로 저장 API의 응답을 확인한다. `401`이면 인증을 먼저 확인하고, `409`와 오늘 스케줄 문구면 검수 시작 날짜를 확인한다. `422`의 수량 오류나 `503/504`·연결 실패는 별도 원인을 조사한다. 401은 계정·권한 변경에 따른 세션 폐기 등에서도 발생할 수 있으므로 401 하나로 만료를 확정하지 않는다.
4. 야간 작업 시작 전 새로 로그인한 상태에서도 같은 문제가 반복되는지 확인한다. 입력 중인 창을 닫아 내용이 없어지는 방식으로 시험하지 않는다.
5. 새 로그인 후에도 로그인 시각과 무관하게 같은 시각에 실패하면 운영 PC의 실제 예약 작업, 절전·서비스 중지 기록, DB 지연과 네트워크 기록을 확인한다.

인증 만료가 확인되면 공통 API 처리에 **만료 안내 → 입력 보존 → 재로그인 → 권한·최신 자료 확인 → 사용자가 저장 재실행** 흐름을 보완하는 것이 적절하다. 자동으로 저장 요청을 재전송하지 않는다. 야간에 자정을 넘겨 미시작 검수를 시작해야 하는 업무가 있다면, 검수 시작 날짜 규칙은 별도 업무 결정이 필요하다.

## 변경 및 미확인 범위

추가한 파일은 본 분석 문서와 별도 진단 코드·결과 파일이다. 운영구조 문서에 분석 링크를 추가했다. 애플리케이션 코드·토큰 유효시간·환경설정·업무 데이터는 변경하지 않았다. 운영 장애의 실제 오류 문구, 로그인 시각, 서버 설정·로그를 받지 못해 현장 원인 확정과 실제 운영 재현은 남아 있다.
