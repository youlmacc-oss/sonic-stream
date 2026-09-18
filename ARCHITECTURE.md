# SonicStream Architecture

현재 워킹 트리의 구현 구조다. 제품 약속은 `PRD.md`, 화면은 `UI_SPEC.md`, 절차는 `YOUTUBE_OPS.md`.

설치 ZIP은 이 구조의 스냅샷이다. 소스 변경 후 ZIP을 다시 만들지 않으면 다른 PC는 이전 구조로 동작한다 (`PRD.md` §1).

문서 기준: `PRD.md` §0과 같다. Git HEAD `3130887ccb4f71ff90b793fe738bf4ec90608acd` + 미커밋/미추적 소스.

---

## 1. 한 장 요약

```text
[개발 PC]
  시작하기.bat
    → backend/.venv python -m uvicorn main:app --host 127.0.0.1 --port 8000
    → frontend  npm run dev -- --hostname 127.0.0.1 --port 3000
    → 브라우저 http://127.0.0.1:3000  (rewrites /api → 8000)

[패키지 빌드 PC]  ← 프로그램이 바뀔 때마다
  다른PC에설치하기.bat
    → SONICSTREAM_STATIC=1  next build  → frontend/out
    → embed Python 3.11.9 + pip + requirements (openai 포함)
    → python*._pth 에 `..\..\backend` (내장 Python이 앱을 찾음)
    → Node 22.19.0 node.exe
    → FFmpeg essentials
    → backend + ui/ + packaging/windows/*
    → BUILD.json (source_fingerprint) + FILES.json (파일별 SHA-256)
    → dist/SonicStream-Windows.zip
    → %USERPROFILE%\Downloads\SonicStream\SonicStream-Windows.zip
    → SONICSTREAM_UPLOAD_RELEASE=1 이고 gh 있을 때만 release tag `windows`

[설치 PC]
  설치하기.bat → %LOCALAPPDATA%\SonicStream
  실행하기.bat → run-desktop.ps1
       내장 python uvicorn :8011
       SONICSTREAM_UI_DIR=...\ui
       Edge/Chrome --app=http://127.0.0.1:8011/  (작업 영역 박스)

[공개 사이트]
  Vercel 등 frontend only → 설치 안내 + GitHub Release ZIP
  YouTube 다운로드 없음
```

---

## 2. 저장소 레이아웃

```text
sonic-stream/
  PRD.md / ARCHITECTURE.md / UI_SPEC.md / YOUTUBE_OPS.md
  시작하기.bat                 개발 실행. ZIP을 갱신하지 않음
  다른PC에설치하기.bat         현재 소스 → 설치 ZIP
  backend/
    main.py                    FastAPI 앱
    error_logger.py
    models.py                  레거시/보조. 런타임 계약은 app.models
    requirements.txt
    .env.example               OPENAI_API_KEY=  (실키 금지)
    .env                       gitignore. 이 PC만. 부록 제외
    app/
      models.py                Pydantic 계약
      ytdlp_engine.py          inspect/download/search, YTSEARCH_LIMIT=12
      ai_search.py             OpenAI + ytsearch, RESULT_LIMIT=12, MAX_PROMPT=400
      transcript.py            자막/자동자막 json3/vtt
      classify.py              에러 코드 → 한국어
      desktop.py               작업 영역, 창 열기/포커스, Edge --app
      installer.py             ZIP 위치/서빙
      local_runtime.py         저장, probe, promote, 열기 권한
      file_registry.py         data/file-registry.json (400)
      history_store.py         data/history.json (30)
      env_file.py              .env 읽기/쓰기 (키 로그 금지)
      ui_static.py             패키지 UI /ai /help /install
      quality.py               포맷 선택
      jobs.py / gc.py / sse.py
      youtube_auth.py          선택 쿠키
      pot.py / runtime.py / policy.py / routes.py
      errors.py
  frontend/src/
    app/page.tsx               메인 3열
    app/ai/                    SonicStream AI
    app/help/                  SonicStream 도움말
    app/install/               SonicStream 설치
    lib/workArea.ts            작업 영역 맞춤
    lib/searchWindow.ts        창 열기, 검색/AI/대본, 다운로드 ACK
    lib/apiStatus.ts           hasSavedOpenaiKey
    components/...
  scripts/
    start-local.ps1
    package-windows.ps1
    package-fingerprint.ps1
    export-restore-bundle.ps1
    restore-from-md.ps1
  packaging/windows/           ZIP에 그대로 들어감
  dist/                        gitignore. 빌드 산출. 부록 제외
```

프론트 주요 파일:

| 파일 | 역할 |
| :--- | :--- |
| `PreviewPane.tsx` | URL, 돋보기 일반검색, AI 검색 가드, 미리보기 |
| `DownloadButton.tsx` | Inspect 연동 CTA, SSE, 완료 계약 |
| `HistoryPanel.tsx` | localStorage + PC 이력 hydrate |
| `DesktopSettings.tsx` | 폴더, API 키, 자동시작, 종료 |
| `ApiStatus.tsx` | 8초 폴. 엔진 / OpenAI 점 |
| `HelpGuide.tsx` | 도움말 본문 |
| `InstallNeeded.tsx` / `InstallGuideWindow.tsx` | 배포 설치 안내 |
| `WatchPlayer.tsx` | youtube-nocookie + IFrame API 음량/시크 |
| `TranscriptPanel.tsx` | 대본 있음/없음/실패 |
| `AiResultCard.tsx` | 바로보기 / 1080p / MP3 |
| `MoreOnYoutube.tsx` | 「유튜브에서 더 찾기」 새 탭 |
| `LocalFileActions.tsx` | 파일/폴더 열기, 경로 복사 |
| `WindowControls.tsx` | 최소화 / 전체 / 조절창 |
| `workArea.ts` | avail* + 자동숨김 48px |

---

## 3. 런타임 프로세스

### 3.1 개발

- `SONICSTREAM_LOCATION=local`
- `ALLOWED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:8000,http://localhost:8000`
- `YOUTUBE_ALLOW_DIRECT=true`
- `NEXT_PUBLIC_API_URL` 비움 → 상대 `/api`, Next rewrites → 8000
- `SONICSTREAM_STATIC`를 개발 셸에 남기지 않는다 (남으면 rewrite가 깨짐)

### 3.2 패키지 데스크톱

`run-desktop.ps1`:

- 포트 **8011 고정**. 다른 프로그램이 쓰면 실패. 개발 :8000을 재사용하지 않음
- 이미 우리 엔진이면 창만 연다
- `runtime/python/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8011`
- `--app=` + `--user-data-dir=<설치폴더>/profile`
- `Get-DesktopWindowBox 1280 800` → `--window-size` / `--window-position` (작업 영역, pad 16, chrome 48, 자동숨김이면 높이 −48)
- `.env` 로드: 설치 루트 `.env` 다음 `backend/.env` (**항상 덮어씀**)
- `SONICSTREAM_HOME` = 설치 루트

중복 실행: 같은 `SONICSTREAM_HOME`의 엔진이 :8011에 있으면 창만. 다른 앱이 :8011이면 실패.

### 3.3 정적 UI

`ui_static.py` + `main.py`: `GET /` `/ai` `/help` `/install`, `/_next/static/*`. API는 같은 오리진.

`SONICSTREAM_STATIC=1` → `next.config.ts` `output: "export"`. 패키지 UI는 루프백이라 `local` 3열. 공개 호스트는 `public` 설치 안내.

### 3.4 환경 변수 로드 순서

Python `env_file.load_dotenv_files` (기존 `os.environ`은 덮지 않음):

1. `$SONICSTREAM_HOME/.env`
2. `backend/.env`
3. 레포 루트 `.env` (다를 때)

허용 기록 키: `OPENAI_API_KEY`, `OPENAI_MODEL`.

| 변수 | 기본 | 의미 |
| :--- | :--- | :--- |
| `OPENAI_API_KEY` | 비움 | 있으면 AI 가능 |
| `OPENAI_MODEL` | `gpt-4o-mini` | |
| `SONICSTREAM_LOCATION` | `local` | 로컬 저장 |
| `SONICSTREAM_HOME` | 설치 루트 | data/ 위치 |
| `SONICSTREAM_SAVE_DIR` | 없음 | 있으면 저장 폴더 우선 |
| `SONICSTREAM_SETTINGS` | `%LOCALAPPDATA%\SonicStream\settings.json` | 폴더/자동시작 |
| `SONICSTREAM_UI_DIR` | 설치본 `ui` | |
| `SONICSTREAM_FFMPEG_DIR` | 설치본 `runtime/ffmpeg` | |
| `SONICSTREAM_STATIC` | 패키지 빌드만 `1` | |
| `SONICSTREAM_UPLOAD_RELEASE` | 비움 | `1`일 때만 gh 업로드 |
| `NEXT_PUBLIC_API_URL` | 비움 | |
| `NEXT_PUBLIC_INSTALLER_URL` | GitHub windows ZIP | |
| `ALLOWED_ORIGINS` | 모드별 | CORS |
| `YOUTUBE_ALLOW_DIRECT` | `true` | |
| `ADMIN_TOKEN` / `DEBUG_BACKLOG_TOKEN` | 비움 | 없으면 `/api/debug/*` 404 |

---

## 4. HTTP API

베이스: 개발 `http://127.0.0.1:8000`, 패키지 `http://127.0.0.1:8011`.

권한:

- **공개**: Host 제한 없음 (사이트가 호출해도 엔진이 없으면 실패)
- **trusted**: `is_local()`이면 루프백 Host/Origin
- **local+loopback**: `require_local_desktop`. 아니면 403/404
- **admin**: `X-Admin-Token` = `ADMIN_TOKEN` 또는 `DEBUG_BACKLOG_TOKEN`. 미설정 404, 불일치 401

| Method | Path | 권한 | 역할 |
| :--- | :--- | :--- | :--- |
| GET | `/health` | 공개 | `{status, service, commit}` |
| GET | `/version` | 공개 | 버전, yt-dlp |
| GET | `/api/status` | 공개 | engine/search/openai. **FFmpeg 없음**. 주기 폴은 유료 API를 부르지 않음. openai: `ready`/`configured`/`no_key`/`no_sdk`/`key_error`/`quota_error`/`network_error`/`down` |
| GET | `/api/runtime` | 공개 | location, save_dir, **ffmpeg**, home, openai, installer |
| POST | `/api/inspect` | 공개 | 메타 |
| POST | `/api/download` | trusted + **local만** | 202 `{job_id}`. 서버 모드면 `LOCAL_ONLY` |
| GET | `/api/progress/{job_id}` | 공개 | SSE |
| GET | `/api/fetch/{job_id}` | 공개 | 브라우저 전송(데스크톱 기본은 로컬 저장) |
| GET | `/api/jobs/{job_id}` | 공개 | 상태. `verified`, `saved_path`, `delivery` |
| POST | `/api/jobs/{job_id}/cancel` | trusted | 취소 |
| POST | `/api/search` | 공개 | `{query, limit}`. 엔진 상한 12 |
| POST | `/api/ai-search` | local+loopback | `{prompt, history[]}`. 키 없으면 `AI_UNAVAILABLE` |
| POST | `/api/transcript` | 공개 | `{url}` |
| GET/POST | `/api/local/settings` | local | 폴더, autostart, openai_api_key |
| POST | `/api/local/pick-folder` | local | 폴더 대화상자. 취소 `{ok:false, cancelled:true}` |
| POST | `/api/local/open` | local | `{path, action: file\|folder\|stat}` |
| POST | `/api/local/window` | local | `open_main` \| `minimize` \| `maximize` \| `restore` |
| GET/POST | `/api/local/history` | local | `{items}` 최대 30 |
| POST | `/api/local/shutdown` | local | 약 0.4초 후 프로세스 종료 |
| GET | `/api/desktop/installer` | 조건 | ZIP 또는 307 |
| GET | `/api/desktop/installer/info` | 공개 | URL/용량 |
| GET | `/api/desktop/setup` | 공개 | `SonicStream-설치.bat` |
| GET | `/ai` `/help` `/install` | 정적 | 별도 창 |
| GET | `/api/debug/*` | admin | backlog, events, bundle, status. 비밀 마스킹 |

루프백이 아닌 Host로 `/api/local/*` 또는 `open_main` URL을 열면 거부. 테스트: `desktop._safe_loopback_app_url`.

OpenAI 상태:

- `no_key`: 키 없음
- `configured`: 키는 저장됨. 상태 폴은 검증 호출을 하지 않음
- `ready`: 검증 성공(저장하고 연결)
- 프론트 `hasSavedOpenaiKey` = `ready` \| `configured`

---

## 5. 백엔드 모듈

| 모듈 | 책임 |
| :--- | :--- |
| `ytdlp_engine` | URL 검증, extract, format, `search_ytsearch` 상한 12, sanitize |
| `ai_search` | 키/모델, 프롬프트 400자, 키워드 2, `connection_status` |
| `transcript` | subtitles/automatic_captions, json3/vtt |
| `desktop` | 작업 영역, `--app`, EnumWindows, ForceFront |
| `local_runtime` | 저장 경로, `unique_dest`, probe, promote, 열기 |
| `file_registry` | 경로 등록 400, 예전 폴더 허용 |
| `history_store` | history.json 30 |
| `installer` | 레포 `dist/` 또는 설치본 옆 ZIP |
| `env_file` | dotenv. 로그에 키 금지 |
| `gc` / `jobs` | `sonic_{job_id}`, 10분 TTL |
| `youtube_auth` | 쿠키 경로가 있을 때만 |
| `classify` | 코드→한국어 |

다운로드 파이프라인:

1. job, temp dir
2. yt-dlp 포맷
3. SSE (약 200ms)
4. FFmpeg mux 또는 오디오 + ID3
5. `evaluate_saved_media` — 빈 파일 `PROCESS_FAILED`, ffprobe 없음 `VERIFY_UNAVAILABLE`, 스트림 불량 `VERIFY_FAILED`
6. local이면 promote + registry + complete(`verified=true`)
7. GC

검색: `normalize_search_query` → `search_ytsearch(limit=12)`. AI는 OpenAI JSON 후 키워드별 검색을 12건으로 자름.

`USER_MESSAGES` 전체 키: `INVALID_URL`, `UNSUPPORTED_URL`, `FORMAT_UNAVAILABLE`, `ROUTE_CONFIG`, `ROUTE_COOL`, `NOT_FOUND`, `GEO_RESTRICTED`, `RATE_LIMITED`, `BOT_CHECK`, `LOGIN_REQUIRED`, `COOKIE_INVALID`, `POT_MISSING`, `POT_FAILED`, `JS_RUNTIME`, `EXTRACT_FAILED`, `STREAM_FORBIDDEN`, `STREAM_EXPIRED`, `PROXY_AUTH`, `PROXY_CONNECT`, `NETWORK_ERROR`, `TIMEOUT`, `LIVE_STREAM`, `AGE_RESTRICTED`, `JOB_NOT_FOUND`, `PROCESS_FAILED`, `FFMPEG_FAILED`, `UNKNOWN`, `NOT_READY`, `BUSY`, `AI_UNAVAILABLE`, `AI_FAILED`, `VERIFY_FAILED`, `VERIFY_UNAVAILABLE`, `CANCELLED`, `FORBIDDEN`, `LOCAL_ONLY`.

문구 정본은 코드. 자주 쓰는 항목은 `PRD.md` §8.

---

## 6. 프론트 데이터 흐름

```text
page.tsx
  shell = useSyncExternalStore(appShell) → boot | public | local
  boot: 준비 화면(서버와 첫 페인트 동일)
  public: InstallNeeded만. HistoryPanel/WindowControls/로컬 API 없음
  web: `?devpc=1` 화면 선택. 배포 API(`NEXT_PUBLIC_API_URL`). `/api/local/*` 없음
  local: 루프백 3열. 같은 오리진 로컬 API. 배포 API 주소를 쓰지 않음
  local: 3열 + keepCurrentWindowAboveTaskbar + runtime/inspect
  History: HistorySnapshotCache. 같은 raw면 같은 배열 참조.
           getServerHistorySnapshot = EMPTY_HISTORY
           변경 시에만 persist/notify. 읽기만으로는 저장하지 않음

PreviewPane
  돋보기/Enter → POST /api/search → 왼쪽 12건
  AI 검색 → hasSavedOpenaiKey ? openAiChatWindow : 인페이지 안내

DownloadButton
  POST /api/download → EventSource /api/progress
  complete + verified → history + LocalFileActions
  AI 요청은 BroadcastChannel sonicstream.search.v1 + postMessage
  ACK 4초

ai/page.tsx
  keepCurrentWindowAboveTaskbar()
  POST /api/ai-search
  WatchPlayer / TranscriptPanel
  메인 열기 → open_main
```

`getApiBase()`: 정적/같은 오리진이면 `""`. 개발은 rewrite. `NEXT_PUBLIC_API_URL`은 예외만.

설치 URL 기본:

`https://github.com/youlmacc-oss/sonic-stream/releases/download/windows/SonicStream-Windows.zip`

`NEXT_PUBLIC_INSTALLER_URL`로 덮을 수 있다. 프론트 값을 바꾸면 정적 빌드와 ZIP을 다시 만든다.

---

## 7. 데이터 파일

| 경로 | 스키마 요지 | 상한 |
| :--- | :--- | :--- |
| `data/history.json` | `{items:[{id,url,...}]}` | 30, id 중복 제거 |
| `data/file-registry.json` | `{files:[{path, job_id?, bytes?}]}` | 400, 경로 앞쪽 최신 |
| `settings.json` | `save_dir`, autostart | 1파일 |
| `localStorage` 위 키 | `PRD.md` §6.6 | |

이관: 브라우저 이력을 `POST /api/local/history`로 PC에 씀. HistoryPanel 마운트 시 GET으로 hydrate.

설치/제거 (`install-desktop.ps1` / `uninstall-desktop.ps1`):

- 설치 위치: `%LOCALAPPDATA%\SonicStream`. 받은 영상은 보통 설치 폴더 밖(`다운로드\SonicStream`).
- 설치·업데이트 시 보존: `data`, `profile`, `.env`, `runtime.pid`.
- 제거 시 보존: `data`, `profile`, `.env`. 바로가기는 지운다. 받은 영상 폴더는 건드리지 않는다.

---

## 8. 패키지 ZIP 레이아웃

```text
SonicStream-Windows/
  BUILD.json
  설치하기.bat / 실행하기.bat / 종료하기.bat / 제거하기.bat
  run-desktop.ps1 / install-desktop.ps1 / uninstall-desktop.ps1
  사용설명서.txt / 설치안내.txt / 먼저읽어주세요.txt
  backend/main.py, error_logger.py, requirements.txt, app/*.py
  ui/                        frontend/out
  runtime/python/            3.11.9 embed + site-packages
  runtime/node/node.exe      22.19.0
  runtime/ffmpeg/ffmpeg.exe
```

`.env`, `.venv`, `node_modules`는 ZIP에 없다.

패키저 (`scripts/package-windows.ps1`):

- 프론트는 `package-lock.json` + `npm ci`만. 실패 시 기존 `node_modules`로 계속하지 않는다.
- 최종 ZIP은 `dist/SonicStream-Windows.next.zip`을 검사한 뒤에 교체한다. 기존 `dist/SonicStream-Windows.zip`은 검사 전에 지우지 않는다. 교체 실패 시 이전 파일을 남긴다.
- 스테이지에 `BUILD.json`과 파일별 해시 `FILES.json`을 남긴다.

고정 버전:

| 구성 | 버전 |
| :--- | :--- |
| Embeddable Python | 3.11.9 amd64 |
| Node (패키지) | 22.19.0 win-x64 |
| FastAPI | 0.141.1 |
| uvicorn | 0.53.0 |
| pydantic | 2.13.5 |
| yt-dlp | `yt-dlp[default]>=2026.8.19` |
| openai | `>=1.54.0,<2` |
| curl_cffi | 0.16.3 |
| bgutil-ytdlp-pot-provider | 1.3.1 |
| Next | 16.3.5 |
| React | 19.2.8 |
| Tailwind | v4 |

개발 Python은 3.11+면 된다. 패키지 재현은 **3.11.9 embed**.

---

## 9. 창·작업 영역·보안 경계

정본 픽셀·사용자 동작: `UI_SPEC.md` §2.

구현:

| 위치 | 하는 일 |
| :--- | :--- |
| `frontend/src/lib/workArea.ts` | `OPEN_PAD=16`, `TASKBAR_FALLBACK=48`. `readWorkArea`는 `screen.avail*`. availHeight가 화면 높이와 같으면 −48. `fitWindowInWorkArea` prefer 80,40. `keepCurrentWindowAboveTaskbar`는 즉시 + 80ms clamp |
| `searchWindow.ts` | 도움말 560×640, 설치 640×760, 메인 1280×800, AI 1220×840. 연 뒤 0/50ms resize, 200ms clamp. 이름 `sonicstream-help`/`install`/`main`/`ai` |
| `page.tsx` / `ai/page.tsx` | 마운트 시 clamp. 도움말·설치 페이지는 마운트 clamp 없음 |
| `WindowControls.tsx` | 전체=`fillWorkArea`, 조절창=`fitWindowInWorkArea(1280,800)` 후 API |
| `desktop.py` | `WINDOW_PAD=16`, `WINDOW_CHROME_H=48`, `TASKBAR_FALLBACK=48`, `MAIN_WINDOW_W/H=1280×800`. `work_area_rect` = `SPI_GETWORKAREA` + 자동숨김 −48. 새 앱 창은 chrome 48을 더 뺌. restore는 `SetWindowPos` + `SWP_SHOWWINDOW(0x0040)` |
| `run-desktop.ps1` | 같은 박스 |

`open_or_focus_main_window` ForceFront:

1. 최소화면 restore(9), 아니면 show(5)
2. AttachThreadInput + Alt keybd_event
3. BringWindowToTop / SetForegroundWindow
4. `SetWindowPos` HWND_TOPMOST (−1), flags 3 (`SWP_NOMOVE\|NOSIZE`)
5. 바로 HWND_NOTOPMOST (−2)
6. SetForegroundWindow

**항상 위 고정이 아니다.** 포커스용 순간 TOPMOST만 쓴다.

없는 처리: 세션 간 창 위치 저장, 디스플레이 변경 리스너, 모니터 지정, DPI 전용 로직, 화면 밖 지속 감시.

보안:

- 로컬 API는 loopback Host + http/https
- `open_main` URL도 loopback만
- 원격 사이트는 ZIP만
- 창 제목: 메인 `SonicStream`, AI `SonicStream AI`, 도움말 `SonicStream 도움말`, 설치 `SonicStream 설치`
- EnumWindows: 정확 `SonicStream` 또는 `endswith "| SonicStream"`

---

## 10. 테스트

unittest (`pytest` 없음).

| 파일 | 범위 |
| :--- | :--- |
| `test_ops_fixes.py` | 분류, env, UI 경로, 저장 폴더 차단, **`fit_window_in_area`**, 루프백 URL, 검색/조회수, AI 계획, installer, 창 action 거부 |
| `test_completion_and_files.py` | 검증, 등록부 예전 폴더 열기, 이력, transcript, cancel |
| `test_recovery.py` | 재시도, SSE, 품질, timeout이 done을 덮지 않음 |
| `test_eventlog.py` | 로그, 마스킹, admin 404/401 |

프론트 `workArea.ts`, 실제 `window.open`, DPI, 다중 모니터, 작업표시줄 자동 숨김 UI는 자동 시험 없음.

코드 변경 후: 해당 테스트 → `시작하기.bat` → 배포할 설치본이 필요하면 `다른PC에설치하기.bat`. 공개 업로드는 `SONICSTREAM_UPLOAD_RELEASE=1`일 때만.

복원 검증: `scripts/restore-from-md.ps1`은 부록 영역(`RESTORE_BEGIN`~`END`) 안의 매니페스트·TAR만 본다. 표식 없음·파싱 실패·누락·해시 불일치는 throw. `-VerifyOnly`는 재추출 없이 대조.
