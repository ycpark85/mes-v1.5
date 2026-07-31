# MES v1.5 개발 및 배포 기준

## 버전 역할

- `mes-v1.5`는 Git 커밋 `4da47c94d361ec3e2b9eb3785fdacd5f53122f80`을 기능 기준선으로 사용한다.
- 기준선 태그는 `v1.5-baseline-4da47c9`이다.
- `mes-v1`은 이후 통합 기능을 참고하기 위한 코드로 유지한다.
- `mes-v1.2`는 2026-07-30 운영 스냅샷으로 유지한다.
- 세 프로젝트의 Git 저장소, 가상환경, `.env`, 스토리지 디렉터리는 서로 공유하지 않는다.

## 개발 PC 경로

| 구분 | 경로 또는 값 |
|---|---|
| 소스 | `C:\Users\jaewon\Documents\Codex\mes-v1.5` |
| 백엔드 가상환경 | `C:\Users\jaewon\Documents\Codex\mes-v1.5\backend\.venv` |
| 개발 DB | `mes_db` |
| Alembic 기준 | `29d3e4f5a6b7` |
| 파일 스토리지 | `C:\Users\jaewon\Documents\Codex\mes-v1.5-data` |
| DB 안전 백업 | `C:\Users\jaewon\Documents\Codex\mes-v1.5-db-safety` |

`.env`, `.venv`, DB 백업, 도면, 불량 사진, 동판 데이터는 Git에 커밋하지 않는다.

## 개발환경 최초 구성

Python 3.14 계열을 사용한다. 현재 확인된 개발환경 버전은 Python 3.14.6이다.

```powershell
cd C:\Users\jaewon\Documents\Codex\mes-v1.5\backend
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

`.env`에는 실제 DB 접속정보와 충분히 긴 `AUTH_SECRET_KEY`를 입력하고 다음 스토리지 루트를 사용한다.

```text
DRAWING_STORAGE_ROOT=C:\Users\jaewon\Documents\Codex\mes-v1.5-data\drawings
DEFECT_PHOTO_STORAGE_ROOT=C:\Users\jaewon\Documents\Codex\mes-v1.5-data\defect_photos
PLATE_DATA_STORAGE_ROOT=C:\Users\jaewon\Documents\Codex\mes-v1.5-data\plate_data
```

DB 스키마를 임의로 초기화하지 않는다. 먼저 현재 리비전과 코드 head를 확인한다.

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
```

마이그레이션이 필요하면 검증된 DB 백업을 먼저 만들고 적용한다.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## 개발 실행과 검증

백엔드 개발 서버:

```powershell
cd C:\Users\jaewon\Documents\Codex\mes-v1.5\backend
.\Start-DevBackend.ps1
```

기본 주소는 `http://127.0.0.1:8000`이고 헬스체크는 `/api/v1/health`이다.

커밋 전에 최소한 다음을 실행한다.

```powershell
cd C:\Users\jaewon\Documents\Codex\mes-v1.5\backend
.\.venv\Scripts\python.exe -m pytest tests -q

cd ..\frontend-wpf\Mes.WpfClean\Mes.Wpf
dotnet build .\Mes.Wpf.sln -c Debug
dotnet build .\Mes.Wpf.sln -c Release
```

## Git 운용

- 새 원격 저장소는 `https://github.com/ycpark85/mes-v1.5.git`을 사용한다.
- 운영 기준 브랜치는 `main`이다.
- 개발은 `codex/mes-v1.5` 또는 작업별 `codex/*` 브랜치에서 진행한다.
- 테스트가 끝난 커밋만 `main`에 병합한다.
- 운영 PC는 `main`만 fast-forward 방식으로 받아야 한다.
- `mes-v1`, `mes-v1.2`의 remote를 `mes-v1.5` remote로 변경하지 않는다.

원격 저장소가 준비된 뒤 개발 PC에서 한 번만 연결한다.

```powershell
cd C:\Users\jaewon\Documents\Codex\mes-v1.5
git remote add origin https://github.com/ycpark85/mes-v1.5.git
git push -u origin codex/mes-v1.5
git push origin v1.5-baseline-4da47c9
```

## 운영 PC 백엔드 배포

운영 PC의 기본 경로는 `C:\mes`, 포트는 `8000`, 브랜치는 `main`으로 가정한다. 첫 전환 전에는 현재 운영 PC의 `git status`, branch, remote, HEAD를 확인하고 운영 `.env`, `.venv`, 스토리지 및 DB 백업 경로가 Git 외부에서 보존되는지 확인해야 한다.

먼저 변경 계획만 확인한다.

```powershell
cd C:\mes
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\deploy\windows\Update-MesBackend.ps1 `
  -RepositoryRoot C:\mes
```

API를 중지하고 DB 백업 명령이 정상 동작하는지 확인한 뒤 적용한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\deploy\windows\Update-MesBackend.ps1 `
  -RepositoryRoot C:\mes `
  -Apply
```

코드와 DB revision이 다를 때만 사전 검토 후 `-ApplyMigration`을 추가한다. 스크립트는 자동 downgrade나 DB 복원을 실행하지 않는다.

배포 후 기존 방식으로 API를 재실행하고 확인한다.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

## 내부 MES WPF 배포

현재 운영 ClickOnce 버전이 `1.0.0.33`이므로 다음 배포는 `ApplicationRevision 34` 이상을 사용한다. 같은 revision을 재사용하지 않는다.

```powershell
cd C:\Users\jaewon\Documents\Codex\mes-v1.5
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\deploy\windows\Publish-MesWpf.ps1 `
  -ApplicationRevision 34 `
  -OutputRoot C:\mes-v1.5-publish\wpf-1.0.0.34
```

출력 폴더에는 `Application Files`, `Mes.Wpf.application`, `setup.exe`가 생성된다. 운영 공유 폴더를 먼저 별도 백업한 뒤 `/MIR` 없이 복사한다.

```powershell
robocopy C:\mes-v1.5-publish\wpf-1.0.0.34 \\172.30.1.240\mes_wpf /E /R:2 /W:1
```

## 보현 외부업체 WPF 배포

외부업체 앱은 내부 ClickOnce 앱과 별도 산출물이다. 운영 API 주소는 `https://vendor-mes.semiindustry.com/`로 검증된다.

```powershell
cd C:\Users\jaewon\Documents\Codex\mes-v1.5
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\deploy\windows\Publish-MesVendorWpf.ps1 `
  -OutputRoot C:\mes-v1.5-publish\vendor-20260731
```

외부업체에 전달할 때는 산출물 전체를 같은 폴더 구조로 전달하고, 로그인·목록 조회·입고·작업완료·출하 흐름을 수동 확인한다.

## 롤백 원칙

- 백엔드 코드는 문제 커밋을 `git revert`하여 `main`에 반영한 뒤 다시 배포한다.
- DB는 자동 downgrade하지 않는다. 복구가 필요하면 해당 배포 직전의 검증된 백업과 장애 시점 리비전을 기준으로 별도 복구 계획을 승인받는다.
- 내부 WPF는 배포 전 백업한 ClickOnce 루트로 되돌린다.
- `.env`, `.venv`, DB 및 스토리지 파일은 `git pull`이나 WPF 복사 대상으로 취급하지 않는다.
