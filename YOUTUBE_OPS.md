# YouTube 다운로드 운영 가이드

이 문서는 모든 환경에서 성공한다고 주장하지 않습니다. 서버에서 고칠 수 있는 문제와, 다른 네트워크 출구가 필요한 문제를 나눕니다.

## 확인된 버전 조합

로컬 Windows에서 확인한 조합:

| 구성 | 버전 / 상태 |
| :--- | :--- |
| Python | 프로젝트 venv (backend/.venv) |
| yt-dlp | 2026.08.30.232658 (nightly, 로컬 검증) |
| yt-dlp-ejs | 설치됨 (`yt-dlp[default]`) |
| curl_cffi | 0.16.3 |
| FFmpeg | 로컬 WinGet Gyan 빌드 |
| JS runtime | Node 있음, Deno 없음 |
| bgutil-ytdlp-pot-provider | 1.3.1 (플러그인, HTTP 공급자 별도) |

배포 이미지 기본값은 `requirements.txt`의 안정 트랙(`yt-dlp[default]>=2026.8.24`)입니다. 컨테이너에는 Deno를 넣습니다. 로컬 Windows는 Node를 사용합니다.

### 업그레이드

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -U --pre "yt-dlp[default]"
.\.venv\Scripts\python.exe -c "import yt_dlp; print(yt_dlp.version.__version__)"
```

Docker 빌드에서 nightly가 필요할 때만:

```text
YTDLP_TRACK=nightly
```

### 롤백

1. `git checkout`으로 이전 커밋의 `backend/app`, `requirements.txt`, `Dockerfile`을 되돌립니다.
2. 이미지 재배포 후 `/health`만 확인합니다. YouTube 시험 요청을 health에 넣지 않습니다.
3. nightly가 원인으로 보이면 `YTDLP_TRACK=stable`로 다시 빌드합니다.

## 원인 분류

| 코드 | 의미 | 서버만으로 복구? |
| :--- | :--- | :--- |
| `RATE_LIMITED` | 429 / Too Many Requests | 대기·상한 후 재시도. IP 차단이 확정된 것은 아님 |
| `BOT_CHECK` | 자동 요청 확인 요구 | 쿠키 또는 다른 경로. IP 차단과 동일하지 않음 |
| `LOGIN_REQUIRED` | 로그인 필요 | 유효한 쿠키가 있을 때만 재시도 |
| `COOKIE_INVALID` | 쿠키 형식/거절 | 쿠키 갱신. 파일 존재만으로 유효하지 않음 |
| `POT_MISSING` / `POT_FAILED` | 토큰 공급 문제 | 공급자 가동. IP 차단 해제가 아님 |
| `JS_RUNTIME` | Deno/Node/EJS 없음 | 런타임 설치 |
| `EXTRACT_FAILED` | 플레이어 정보 추출 실패 | 클라이언트/런타임 점검. 원인 불명일 수 있음 |
| `STREAM_FORBIDDEN` | 미디어 서버 403 | 같은 경로에서 재추출 또는 경로 전환 |
| `STREAM_EXPIRED` | 서명 URL 만료 | 같은 경로에서 재추출. 옛 URL 재사용 금지 |
| `PROXY_AUTH` | 407 | 설정 오류. 같은 경로 반복 금지 |
| `PROXY_CONNECT` | 프록시 연결 실패 | 해당 경로 휴식 |
| `NETWORK_ERROR` / `TIMEOUT` | DNS/TLS/연결 | 제한 재시도. IPv4/IPv6는 비교 진단만 |
| `GEO_RESTRICTED` / `NOT_FOUND` / `AGE_RESTRICTED` | 접근 제한 | 같은 조건 반복 금지 |
| `FFMPEG_FAILED` | 변환 실패 | YouTube 추출부터 다시 시작하지 않음 |
| `UNKNOWN` | 증거 부족 | 원인 불명으로 남김 |

`inspect` oEmbed 성공은 미리보기입니다. 다운로드 가능 판정이 아닙니다. oEmbed 404만으로 삭제 영상이라고 단정하지 않습니다.

## 환경 변수 (비밀값 없는 예시)

```env
ALLOWED_ORIGINS=http://localhost:3000
ENVIRONMENT=development
YOUTUBE_COOKIE_MODE=anonymous_first
YOUTUBE_COOKIES_FILE=C:\secrets\youtube_cookies.txt
YOUTUBE_ALLOW_DIRECT=true
YOUTUBE_ROUTES=home
YOUTUBE_ROUTE_home=http://127.0.0.1:8888
YOUTUBE_IMPERSONATE=chrome
YOUTUBE_POT_BASE_URL=http://127.0.0.1:4416
YOUTUBE_IP_MODE=ipv4
MAX_CONCURRENT_DOWNLOADS=1
MAX_DOWNLOAD_QUEUE=8
JOB_TIMEOUT_SECONDS=720
ADMIN_TOKEN=change-me
```

프록시 비밀번호, 쿠키, PO Token 원문은 로그에 남기지 않습니다. 경로는 별칭으로만 기록합니다.

## 경로별 필요 조건

### 기본 경로

- 인증서 검증을 켭니다. `nocheckcertificate`를 기본 해결책으로 쓰지 않습니다.
- yt-dlp 기본 클라이언트를 먼저 씁니다. 다음 후보는 현재 버전에서 확인된 `web_safari`, POT가 준비되면 `mweb`입니다.
- `YOUTUBE_COOKIE_MODE=anonymous_first`이면 공개 영상에 로그인 쿠키를 먼저 붙이지 않습니다.

### 쿠키

- `YOUTUBE_COOKIES` 또는 `YOUTUBE_COOKIES_FILE`은 Netscape 형식이어야 합니다.
- 파일 존재는 로그인 유효성이 아닙니다. health/has_cookies는 공유 파일을 다시 쓰지 않습니다.
- 갱신 시점: 새 쿠키를 환경/시크릿에 넣은 뒤 프로세스를 재시작하면 적용됩니다. 파일 경로는 다음 다운로드부터 읽습니다.
- 일반 사용자에게 쿠키 설정을 요구하지 마십시오.

### PO Token (bgutil)

1. 별도 HTTP 공급자를 띄웁니다. 예: 공식 이미지 또는 Node/Deno 서버, 기본 `http://127.0.0.1:4416`.
2. `pip install bgutil-ytdlp-pot-provider==1.3.1` (이미 requirements에 포함).
3. `YOUTUBE_POT_BASE_URL`을 공급자 주소로 설정합니다. yt-dlp 플러그인이 영상별로 토큰을 받습니다. 고정 토큰을 넣지 마십시오.
4. 공급자가 없거나 응답하지 않으면 `mweb`을 강제하지 않고 `web_safari`/기본 경로로 제한 fallback합니다.
5. 성공은 IP 차단 해제가 아닙니다.

배포에서 공급자를 같은 서비스에 넣기 어렵다면, 운영자 네트워크의 워커에서만 POT를 켜십시오.

### 대체 네트워크 경로

- `YOUTUBE_PROXY` 또는 `YOUTUBE_ROUTES` + `YOUTUBE_ROUTE_<alias>`.
- 한 시도 안에서는 쿠키·토큰·네트워크 경로를 유지합니다. 경로를 바꾸면 추출부터 다시 합니다.
- 407은 그 경로를 길게 쉬게 하고 반복하지 않습니다.
- 요청마다 무작위 IP를 바꾸지 않습니다. 차단마다 모든 경로를 연쇄 호출하지 않습니다.
- `YOUTUBE_ALLOW_DIRECT=false`이면 직접 연결을 쓰지 않습니다.
- 대체 경로 실제 값이 없으면 코드 경로만 검증된 상태입니다.

## 모든 경로가 실패할 때

사용자에게는 분류된 안내만 보입니다. 작업은 `error`로 한 번 확정됩니다. 같은 조건의 삭제/비공개/407은 반복하지 않습니다.

서버 경로로 계속 실패하면 운영자 소유의 별도 다운로드 워커(집 회선, 주거용 프록시)를 붙이는 것이 다음 단계입니다. 공유 저장소나 시스템 재작성은 다중 인스턴스 필요가 확인될 때 결정합니다. 지금 JobStore는 프로세스 메모리입니다.

## Windows 로컬 실행

```powershell
cd C:\AICODING\sonic-stream\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

다른 터미널:

```powershell
cd C:\AICODING\sonic-stream\frontend
npm install
npm run dev
```

프론트는 `NEXT_PUBLIC_API_URL=http://localhost:8000`을 사용합니다.

모의 테스트:

```powershell
cd C:\AICODING\sonic-stream\backend
.\.venv\Scripts\python.exe -m unittest tests.test_recovery -v
```

## 배포 적용 순서

1. 현재 이미지를 기록해 롤백 지점을 남깁니다.
2. 환경 변수를 넣습니다. 비밀은 Render/호스트 시크릿만 사용합니다.
3. `workers=1`을 유지합니다. 인메모리 JobStore는 프로세스 간 공유되지 않습니다.
4. 배포 후 `GET /health` → `{"status":"ok"}`만 확인합니다.
5. `ADMIN_TOKEN`을 설정한 뒤 `GET /api/debug/status`, `/api/debug/backlog`, `/api/debug/bundle?job_id=`를 `X-Admin-Token`으로 조회합니다. 토큰이 없으면 진단 API는 404입니다. 재배포 후에도 로그를 남기려면 `LOG_BACKUP_DIR`를 영구 볼륨으로 지정합니다. 설정이 없으면 원격 백업은 비활성입니다.
6. 공개 테스트 영상 한 건만으로 로컬과 배포를 비교합니다. 한 번에 변수 하나만 바꿉니다 (런타임, 쿠키, 경로, POT).
7. YouTube 시험 요청을 health나 반복 스크립트에 넣지 않습니다.

## 로컬 vs 배포 비교 절차

같은 공개 영상 URL을 사용합니다.

1. 로컬과 배포의 yt-dlp, ejs, JS runtime, FFmpeg, 쿠키 모드를 `/api/debug/status`로 맞춥니다.
2. 둘 다 쿠키/프록시/POT 없이 한 번 받습니다.
3. 배포만 실패하면 네트워크 경로 가능성이 큽니다. 로컬만 실패하면 런타임/버전을 먼저 봅니다.
4. 그다음 쿠키, POT, 프록시를 하나씩만 켭니다.

운영 로그에 접근할 수 없으면 배포 원인은 미확인으로 남깁니다.

## 인메모리 한계

`JobStore`와 다운로드 제한기는 프로세스 메모리입니다. 다중 워커/다중 인스턴스에서는 진행 상태와 중복 억제가 공유되지 않습니다. 현재는 uvicorn workers=1로 맞춥니다.
