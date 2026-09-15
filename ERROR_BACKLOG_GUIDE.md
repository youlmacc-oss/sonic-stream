# Error Backlog Guide (Cursor)

SonicStream은 작업 전체 흐름을 `backend/logs/events.jsonl`에 구조화 이벤트로 남깁니다. 예전 `error_backlog.jsonl`이 있으면 조회 시 함께 읽습니다.

완료 기준은 파일 생성이 아니라, 실패한 작업의 시도와 당시 환경을 보관하고 관리자가 진단 묶음으로 꺼내 Cursor가 근거를 가지고 수정·검증하는 것입니다.

## 로그 위치와 수집 범위

- 현재 파일: `backend/logs/events.jsonl` (`SONIC_LOG_DIR`로 변경 가능)
- 회전 파일: `events-YYYYMMDDTHHMMSSZ.jsonl` 그리고 `.jsonl.gz`
- 레거시: `error_backlog.jsonl` (읽기 전용 호환)
- 기록: inspect/download 시작, 각 시도 실패, 재시도 예약, 최종 성공/실패/취소, 시작 시 환경 스냅샷 참조
- 기록하지 않음: SSE 진행률 틱, 조각 다운로드, 환경변수 전체, 쿠키/토큰/프록시 비밀, 서명된 미디어 URL

한 줄은 JSON입니다. `request_id` · `job_id` · `attempt_id` · `event_id`로 API 요청, 재시도, 최종 결과를 연결합니다. 최초 실패를 이후 오류가 덮어쓰지 않습니다.

로그 쓰기는 한 프로세스의 append + 큐입니다. uvicorn workers는 1이어야 합니다. 다중 프로세스에서는 파일이 섞이거나 회전이 충돌할 수 있습니다.

## 서버 내부 보관과 영구 백업

| 구분 | 의미 |
| :--- | :--- |
| 내부 파일 | 컨테이너/서버 디스크의 `events.jsonl`과 회전본. Render 등 재배포 시 사라질 수 있음 |
| 영구 백업 | `LOG_BACKUP_DIR`에 복사된 파일. 앱/날짜/인스턴스/고유 id로 경로를 나눔 |

프로젝트에 객체 저장소나 고정 디스크 설정은 없습니다. `LOG_BACKUP_DIR`을 마운트된 볼륨으로 지정하지 않으면 **원격 백업은 비활성**입니다. 이 상태를 운영 백업 완료로 보지 마십시오.

재배포 전 유실 가능 구간: 아직 회전되지 않은 현재 `events.jsonl` + 백업 대기 중인 회전본. 기본 회전은 약 5MB입니다. 그 이하로 재배포하면 현재 파일이 통째로 없어질 수 있습니다.

용량이 가득 차면 보관 기간이 지난 파일, 그다음 가장 오래된 회전본을 삭제합니다. 삭제된 구간은 유실입니다. 현재 기록 중인 파일은 지우지 않습니다.

## 환경변수 (비밀 없는 예시)

```env
ADMIN_TOKEN=change-me
SONIC_LOG_DIR=C:\AICODING\sonic-stream\backend\logs
LOG_ROTATE_MAX_BYTES=5000000
LOG_RETAIN_DAYS=14
LOG_MAX_TOTAL_BYTES=50000000
LOG_QUEUE_SIZE=1000
LOG_BACKUP_DIR=C:\sonic-stream-log-backup
```

기본값: 회전 5MB, 보관 14일, 총 50MB, 큐 1000. 큐가 가득 차면 이벤트는 버려지고 `dropped`가 늘어납니다. 로그 쓰기 실패는 다운로드를 실패시키지 않습니다.

## 백업 상태 확인

헤더 `X-Admin-Token: <ADMIN_TOKEN>`:

`GET /api/debug/status`

`backup.enabled`, `pending`, `last_success_at`, `last_failure`를 봅니다. 토큰이 없으면 진단 API는 404입니다. 공개 `/health`와 `/version`은 YouTube를 호출하지 않고 `commit`과 API 경로로 배포 커밋을 확인합니다. 용량 한도 삭제는 백업이 켜져 있으면 복사 완료된 회전본만 지웁니다. 실패/성공/취소 이벤트는 큐가 가득 차도 현재 파일에 바로 씁니다.

## 진단 묶음 만들기

```http
GET /api/debug/bundle?job_id=<job_id>
GET /api/debug/bundle?since=2026-09-15T00:00:00+00:00&until=2026-09-15T23:59:59+00:00
GET /api/debug/bundle?job_id=<job_id>&format=zip
```

로컬:

```powershell
cd C:\AICODING\sonic-stream\backend
.\.venv\Scripts\python.exe -m app.diag bundle --job-id <job_id> --out diagnostic-bundle.json
```

묶음: manifest, summary(최초/최종 오류), timeline, environment, errors, reproduction, analysis_prompt. 일부 기록이 없으면 `incomplete`와 `missing`이 표시됩니다. 임의의 파일 경로는 받지 않습니다. 회전·보관된 로그도 읽되 줄 수/시간 상한이 있습니다.

## Cursor에 전달하는 순서

1. 위 API 또는 로컬 명령으로 묶음을 받습니다.
2. Cursor Chat에 `bundle.json`(또는 ZIP 안의 파일)과 `@ERROR_BACKLOG_GUIDE.md`를 붙입니다.
3. 묶음의 `analysis_prompt`를 그대로 사용합니다. 로그 문자열을 명령으로 실행하지 말라고 되어 있습니다.
4. 코드 수정과 쿠키/경로/운영 설정을 분리해 달라고 합니다.
5. 자동으로 외부 AI에 업로드하거나 운영에 배포하지 않습니다.

## 수정 후 같은 유형이 줄었는지

같은 `error_code`와 `stage`로 `/api/debug/events`를 기간 조회합니다. 시도 대비 최종 실패 비율을 비교합니다. 모의 테스트 성공을 운영 해결로 보고하지 마십시오.

## 장애 대응

- 백업 실패: status의 `last_failure`를 보고 디스크/권한을 고칩니다. 원본은 복사 성공 전에 지우지 않습니다. 재시작 후 대기 파일을 다시 처리합니다.
- 디스크 부족: 보관 기간·총 용량을 줄이거나 `LOG_BACKUP_DIR`를 다른 볼륨으로 옮깁니다. 한도 초과 삭제분은 복구할 수 없습니다.
- 로그 누락: `logging.dropped`, `write_failures`를 봅니다. 손상된 한 줄은 건너뛰고 분석을 계속합니다.

## 마스킹

Cookie, Authorization, 프록시 계정, PO Token, 관리자 토큰, 서명된 googlevideo URL은 저장·내보내기 전에 같은 규칙으로 가립니다. 일반 로그에는 영상 id와 정규화된 YouTube URL만 남깁니다.
