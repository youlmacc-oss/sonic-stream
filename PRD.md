# SonicStream Product Requirements Document

이 문서는 **현재 워킹 트리에 구현된 제품**의 사용자 관점 정본이다. 구조·API는 `ARCHITECTURE.md`, 화면·문구·창은 `UI_SPEC.md`, 복원·설치·시험은 `YOUTUBE_OPS.md`를 본다.

문서와 코드가 어긋나면 **코드를 고치지 말고 먼저 이 4종 문서를 코드에 맞춘다.**

---

## 0. 문서 기준

| 항목 | 값 |
| :--- | :--- |
| 문서 갱신 | 2026-09-18 (KST). 공개 사이트에서도 개발 PC일 때만 메인 화면 버튼 |
| Git HEAD | `3130887ccb4f71ff90b793fe738bf4ec90608acd` (2026-09-16) |
| 워킹 트리 | HEAD + 미커밋 수정 + 미추적 소스 포함. 마지막 커밋만 기준이 아님 |
| 소스 지문 | `source_fingerprint` = `024cf05c6fd84184085e3007658c393e1da44b8371864c355ec50af7c11e3ccc` |
| 복원 부록 | 파일 117, TAR SHA-256 `32a792361973c6b8d7d74cde2d7db7b0872af43c6cb10548079a9a722c639923` |
| 비밀 | `OPENAI_API_KEY`, 쿠키, `.env` 실값, 사용자 다운로드, 브라우저 프로필은 문서·부록에 넣지 않음 |

---

## 1. 기본설계 — 설치 파일은 소스와 항상 같다

SonicStream의 배포 단위는 **웹 서버가 아니라 Windows 설치 ZIP**이다.

| 규칙 | 내용 |
| :--- | :--- |
| 파생물 | `dist/SonicStream-Windows.zip` 은 그 순간 워크트리의 프론트·백엔드·패키징·안내문을 다시 빌드한 결과다. 예전 ZIP을 재사용하지 않는다. |
| 필수 트리거 | 화면, API, 엔진, 패키징 bat/ps1, 사용설명서 중 하나라도 바꾸면 배포 전에 `다른PC에설치하기.bat`을 다시 실행한다. |
| 지문 | 패키저는 `source_fingerprint`를 `BUILD.json`과 `dist/last-package.json`에 남긴다. |
| 개발 ≠ 배포 | `시작하기.bat`은 개발용(포트 8000/3000)이다. 설치본을 갱신하지 않는다. |
| 사이트 ≠ 엔진 | Vercel/공개 URL은 설치 안내·ZIP 랜딩이다. 그 서버에서 YouTube를 받지 않는다. |
| 공개 업로드 | `SONICSTREAM_UPLOAD_RELEASE=1` 이고 `gh`가 있을 때만 GitHub Release `windows`에 올린다. 로컬 ZIP 성공과 업로드 성공을 섞지 않는다. |
| 비밀 | 실키·쿠키는 Git·ZIP·릴리스 노트·복원 부록에 넣지 않는다. |

구현: `scripts/package-windows.ps1`, `scripts/package-fingerprint.ps1`, `다른PC에설치하기.bat`.

---

## 2. 제품 정의

SonicStream은 **Windows PC 전용** YouTube/미디어 다운로더다.

- 엔진: 이 PC의 FastAPI + yt-dlp + FFmpeg.
- 화면: Next.js 정적 UI를 Edge/Chrome `--app=` 창으로 연다. 개발 시에는 Next dev.
- 저장: 사용자가 고른 로컬 폴더. 기본은 **`다운로드\SonicStream`**.
- 기록: 브라우저 `localStorage` `sonicstream.history.v1` **그리고** 이 PC `data/history.json` (최대 30). 서버 공용 DB 없음.
- AI: 각 PC의 `OPENAI_API_KEY`로 `gpt-4o-mini` 검색 대화. 키가 저장되어 있으면(`ready` 또는 `configured`) 메인에서 AI 창을 연다. 없으면 일반 검색만.
- 웹 배포본: 접속 즉시 설치 안내. ZIP을 받아 이 PC에 설치해야 받는다.

대상: 30대 중반 전후. 큰 글씨·큰 버튼. 광고/저품질 칩 없음.

---

## 3. 한다 / 하지 않는다

### 한다

- URL 붙여넣기 → Inspect → 포맷 선택 → 이 PC 폴더에 저장.
- 비디오: `best` / `720p` / `1080p` / `4k` MP4. 가능하면 별도 영상+오디오를 FFmpeg mux. 원본 화면비 유지.
- 오디오: 320k MP3(ID3+커버), FLAC.
- 세로·쇼츠는 화면 분류. 다운로드 `format`은 영상 또는 오디오.
- 왼쪽: 일반 검색(돋보기, 12건) + AI 검색.
- AI 전용 창: 왼쪽 대화 / 오른쪽 결과 12건 + 바로보기 + 대본 + 음량.
- 도움말 창, 설치 안내 창.
- 메인 창이 뒤에 있으면 `open_main`으로 앞으로.
- 창은 Windows **작업 영역**(작업표시줄 위) 안에 연다. 자동 숨김이어도 하단 48px를 비운다. 정본: `UI_SPEC.md` §2.
- SSE 진행, 완료 후 파일/폴더 열기, 경로 복사.
- 글자 크기 토글, API 연결 상태.
- 받은 파일 등록부(`file-registry.json`)로 예전 저장 폴더의 파일도 열 수 있다.

### 하지 않는다

- 메인을 여러 페이지로 쪼개 라우팅하지 않는다. `/ai` `/help` `/install`만 별도 창.
- 메인에 광고/트래커/저품질 칩을 넣지 않는다. 설치·AI 키 안내는 오버레이일 수 있다.
- Vercel/Render를 YouTube 다운로드 백엔드로 쓰지 않는다. Render에서 된다고 주장하지 않는다.
- 쿠키를 첫 사용 조건으로 요구하지 않는다.
- 설치 ZIP에 `.env` 실키를 넣지 않는다.
- 모든 영상이 항상 받아진다고 약속하지 않는다.
- 요약·장면 썸네일은 아직 제품 밖이다. 가짜 버튼을 넣지 않는다.

---

## 4. 실행 모드

| 모드 | 누가 쓰나 | 포트 | UI | 설치 안내 |
| :--- | :--- | :--- | :--- | :--- |
| 개발 (`시작하기.bat`) | 이 레포가 있는 PC | API `127.0.0.1:8000`, Next `127.0.0.1:3000` | `npm run dev` | 루프백이라 자동 안내 없음. `?install=1`만 미리보기 |
| 패키지/데스크톱 | ZIP으로 설치한 PC | 엔진+정적 UI **고정 `127.0.0.1:8011`**. 점유 시 실패. 개발 :8000을 재사용하지 않음 | `SONICSTREAM_STATIC=1`로 빌드한 `frontend/out` | 루프백이라 자동 안내 없음 |
| 배포 사이트 | 공개 URL | 공개 호스트. 다운로드 API 없음 | Next 호스팅 | **첫 페인트부터** 설치 안내. ZIP만 |

판별:

- `isLoopbackHost` → 설치 안내 자동 오픈 금지.
- `isDeployedSite`이고 정적 데스크톱이 아니면 설치 안내.
- 첫 페인트는 `boot`(서버·하이드레이션 동일). 클라이언트 snapshot이 공개 호스트 또는 `?install=1`이면 `public` 설치 안내, 루프백이면 `local` 3열.
- 공개 셸에서는 이력 패널·로컬 설정·창 조절·로컬 API를 마운트하지 않는다. 설치 파일 링크는 백엔드 없이 동작한다.
- 루프백 API(`/api/local/*`)는 Host가 loopback일 때만.

---

## 5. 핵심 사용 흐름

### 5.1 메인 — URL로 받기

1. 주소 붙여넣기 또는 일반/AI 검색에서 URL 선택.
2. 600ms 디바운스 후 `POST /api/inspect`.
3. 카드에 제목/채널/길이/썸네일.
4. 영상 | 세로·쇼츠 | 오디오, 화질 선택.
5. `POST /api/download` → `job_id` → `GET /api/progress/{job_id}` SSE.
6. 로컬이면 지정 폴더에 저장. **완료 UI는 `delivery=local_file`이고 `saved_path`가 있으며 `verified=true`일 때** 「저장됨」. 검증 실패는 완료로 치지 않는다.

### 5.2 일반 검색

- 검색창 **맨 오른쪽 돋보기**(또는 Enter).
- `POST /api/search`. 결과는 **메인 왼쪽 패널에 12건**. AI 창을 열지 않는다.
- 카드 클릭 → URL 세팅 → Inspect.

### 5.3 AI 검색

- 메인 「AI 검색」은 `GET /api/status`의 `openai`가 **`ready` 또는 `configured`** 일 때 `/ai` 창을 연다 (`hasSavedOpenaiKey`). 상태 폴은 유료 OpenAI 호출을 하지 않는다.
- 검색어가 비어 있어도 키가 있으면 창을 연다 (`/ai`, q 없음).
- 키가 없으면 **메인 안 안내**만 띄운다. 확인하면 안내만 닫고 메인 유지. 버튼 경로로는 `/ai`를 열지 않는다.
- 주소창으로 `/ai`에 직접 들어가면 프론트 가드가 없다. 키 없이 `POST /api/ai-search`하면 `AI_UNAVAILABLE`.
- 창: 왼쪽 채팅(복사/재전송), 오른쪽 결과 12건, 바로보기, 조회수, 대본, 음량.
- `POST /api/ai-search`. 모델 기본 `gpt-4o-mini`. 프롬프트 400자. 키워드 최대 2. 결과 상한 `YTSEARCH_LIMIT = 12`.
- AI 창의 1080p/MP3는 메인에 다운로드를 요청하고 4초 안 ACK를 기다린다. 실패 문구: 「메인 창이 받기를 시작하지 못했습니다. 메인 화면을 연 뒤 다시 눌러 주세요.」

### 5.4 대본

- 바로보기 **대본** → `POST /api/transcript`.
- 자막/자동자막(json3/vtt). 줄이 없으면 「이 영상은 대본이 없습니다.」
- 요청 자체가 실패하면 「대본을 가져오지 못했습니다.」(또는 서버 메시지)
- 줄 클릭 시 플레이어 시크.
- 영상을 바꾸면 대본 상태를 그 URL 기준으로 다시 읽는다.
- 로드맵: 대본 → 요약 → 장면. 요약·장면은 제품 밖.

### 5.5 바로보기 음량

- 기본 **80**. 키 `sonicstream.watchVolume.v1`.
- **0을 저장하면** 다음에도 0(음소거로 시작).
- 음소거 해제 시: 현재 값이 0보다 크면 그 값, 아니면 마지막으로 들린 값, 그것도 없으면 **80**.

### 5.6 설치 (다른 사용자)

1. 공개 사이트 → 설치 안내(동의).
2. 「동의하고 설치하기」는 `SonicStream-설치.bat`을 받고, 「설치 파일만 받기」는 ZIP.
3. ZIP: GitHub Release `windows`의 `SonicStream-Windows.zip` 또는 로컬 `/api/desktop/installer`.
4. `설치하기.bat` → `%LOCALAPPDATA%\SonicStream`.
5. `실행하기.bat` → 엔진+UI. 아이콘을 다시 누르면 기존 메인 창을 앞으로.

### 5.7 메인 창 재오픈

AI/도움말에서 메인 열기: `opener.focus()` 후 항상 `POST /api/local/window` `{ action: "open_main" }`.

백엔드: 제목이 정확 `SonicStream` 이거나 `| SonicStream`으로 끝나는 창만. AI 제목 `SonicStream AI`, 도움말 `SonicStream 도움말`, 설치 `SonicStream 설치`는 메인이 아니다.

---

## 6. 기능 계약

### 6.1 Inspect

- `POST /api/inspect` `{ url }`
- 응답: title, author, duration, thumbnail, width/height, preview_only, duration_known.
- 실패 코드는 `ARCHITECTURE.md` §4, 사용자 문구는 아래 표와 `classify.USER_MESSAGES`.

### 6.2 Download + SSE

| Event | 의미 |
| :--- | :--- |
| `progress` | `status=downloading`, percent, speed, eta |
| `processing` | mux / ID3 |
| `complete` | `status=done`, 로컬 경로. `verified`가 true여야 저장 완료 UI |
| `error` | code, message |

작업 디렉터리: `tempfile.gettempdir()/sonic_{job_id}`. 전송 직후 또는 최대 10분 GC. 시작 시 `sonic_*` 스윕.

중복 파일명: `이름 (2).ext` 형식. 복사 중 `.sspartial` 후 교체.

취소: `POST /api/jobs/{job_id}/cancel`. 완료된 작업은 완료를 덮어쓰지 않는다.

### 6.3 품질

`MediaQuality`: `best` | `720p` | `1080p` | `4k` | `320k` | `flac`.

비디오는 가능하면 별도 최적 영상+오디오 후 FFmpeg. 오디오 320k는 ID3+커버. 화면비는 원본. 세로를 가로로 늘리거나 자르지 않는다.

### 6.4 검색·AI·대본

- 카드: title, author, url, thumbnail, duration, views.
- AI: 프롬프트→키워드(최대 2)→`ytsearch`.
- 대본: language, automatic, lines[{start,text}], text.

### 6.5 로컬 전용 API

루프백 Host만. 목록 정본: `ARCHITECTURE.md` §4.

주요: 설정, 폴더 선택, 파일/폴더 열기, 창, 종료, **이력 GET/POST**, runtime, installer.

### 6.6 클라이언트·PC 상태

| 키 / 파일 | 내용 |
| :--- | :--- |
| `sonicstream.history.v1` | 브라우저 이력. 최대 30. 마운트 전에는 빈 배열(하이드레이션) |
| `sonicstream.activeJobs.v1` | 진행 중 jobId→historyId |
| `{home}/data/history.json` | 같은 30개. `/api/local/history`로 이관 |
| `{home}/data/file-registry.json` | 저장된 파일 경로. 상한 400. 예전 폴더 파일 열기 허용 |
| `sonicstream.textSize.v1` | `'1'`이면 `html.large-type`, `'0'`이면 기본 |
| `sonicstream.watchVolume.v1` | 바로보기 음량 0–100. 기본 80 |

`home`: `SONICSTREAM_HOME` 또는 `%LOCALAPPDATA%\SonicStream`.

### 6.7 파일 열기 권한

현재 저장 폴더 안의 파일이거나 등록부에 있는 경로만 연다. 등록되지 않은 임의 경로는 `FORBIDDEN`.

---

## 7. 창과 작업표시줄 (사용자 관점)

현상: AI/메인 창 하단(입력칸)이 Windows 작업표시줄에 가려질 수 있다. 자동 숨김이 켜져 있으면 사용 가능 높이가 화면 전체처럼 잡혀 창이 밑으로 내려간다.

제품 약속:

- 메인·AI·도움말·설치 창을 **열 때** 작업 영역 안에 맞춘다.
- 메인·AI는 연 뒤에도 넘치면 다시 맞춘다.
- **전체**는 작업 영역만큼. **조절창**은 1280×800(또는 그에 맞게 축소)을 작업 영역 안에.
- 항상 위(TOPMOST)로 고정하지 않는다. 메인을 앞으로 가져올 때만 잠깐 TOPMOST 후 바로 해제한다.

픽셀·함수: `UI_SPEC.md` §2. 구현: `ARCHITECTURE.md` §9.

시험 범위: `YOUTUBE_OPS.md` §5. 배율·다중 모니터·실제 작업표시줄 자동 숨김은 **코드 확인**. 이 문서 갱신 시점에 실제 Windows 작업표시줄 위 재확인은 하지 않음.

---

## 8. 비기능

- 메인 첫 화면은 단일 페이지 3열. 별도 창만 라우트.
- CORS: 개발 3000/8000, 패키지 8011 루프백.
- 파일명: 원본 제목, Windows 금지문자 제거, `filename*`(RFC 5987).
- 에러는 무한 스피너 금지. 버튼 `error` 후 재클릭.
- 쿠키는 선택.
- 로그: 설치본/개발 `backend/logs`. 스냅샷에 비밀 없음.
- `/api/status` 주기 조회는 유료 OpenAI를 부르지 않음.

사용자 메시지 정본은 `backend/app/classify.py` `USER_MESSAGES`다. 자주 쓰는 항목:

| Code | 사용자 메시지 (ko) |
| :--- | :--- |
| `INVALID_URL` | 유효한 동영상 링크를 입력해 주세요. |
| `UNSUPPORTED_URL` | 이 주소에서는 받을 수 있는 형식을 찾지 못했습니다. |
| `NOT_FOUND` | 영상을 찾을 수 없습니다. |
| `GEO_RESTRICTED` | 이 영상은 지역 제한으로 받을 수 없습니다. |
| `RATE_LIMITED` | 요청이 많아 잠시 대기한 뒤 다시 시도합니다. |
| `LIVE_STREAM` | 라이브 스트림은 지원하지 않습니다. |
| `JOB_NOT_FOUND` | 다운로드 작업을 찾을 수 없습니다. |
| `PROCESS_FAILED` | 변환에 실패했습니다. 다시 시도해 주세요. |
| `TIMEOUT` | 시간이 초과되었습니다. 다시 시도해 주세요. |
| `AI_UNAVAILABLE` | AI 검색을 쓰려면 OpenAI 키를 이 컴퓨터에 넣어 주세요. |
| `AI_FAILED` | AI 검색을 끝내지 못했습니다. 잠시 후 다시 시도해 주세요. |
| `VERIFY_FAILED` | 받은 파일이 손상되었거나 필요한 영상이 없습니다. |
| `VERIFY_UNAVAILABLE` | 파일 검사를 할 수 없어 완료로 저장하지 않았습니다. |
| `CANCELLED` | 받기를 취소했습니다. |
| `LOCAL_ONLY` | 이 프로그램은 이 PC에 설치해서 사용합니다. |
| `FORBIDDEN` | 허용되지 않은 경로입니다. |

전체 코드 목록은 `ARCHITECTURE.md` §5.

---

## 9. 다른 PC 100% 재현 — 정의

1. **소스 복원:** 빈 폴더에 MD 4개만 두고 `YOUTUBE_OPS.md` 복원 부록을 풀면 소스·lockfile·패키징이 매니페스트 해시와 같다. YouTube 미래 성공은 포함하지 않는다.
2. clone이 가능하면 레포를 받아도 된다. 그다음 `YOUTUBE_OPS.md`의 개발 설치로 `시작하기.bat`.
3. 같은 레포에서 `다른PC에설치하기.bat`으로 ZIP을 만들면 `BUILD.json` 지문이 그 소스와 같다. 공개 업로드는 별도 플래그.
4. ZIP을 다른 Windows에 풀어 `설치하기.bat`하면 엔진+UI+FFmpeg+바로가기가 동작한다.
5. OpenAI 키는 그 PC에서만 넣고, 없어도 붙여넣기·일반 검색·다운로드는 된다.
6. 공개 사이트는 설치 안내만 하고, 받는 행위는 설치본에서만 한다.

성공 기준:

1. 유효 URL Inspect → 실데이터 카드.
2. 1080p/4K/320k/FLAC 중 선택 → SSE → 로컬 파일(`verified=true`).
3. 돋보기 12건. AI 창은 키가 `ready` 또는 `configured`일 때.
4. 대본 있음/없음/요청 실패를 구분한다.
5. 배포 URL은 설치 안내. 루프백은 안내 없음.
6. 소스 변경 후 옛 ZIP을 주지 않는다.
7. 메인·AI 창이 작업표시줄 아래로 들어가지 않게 열린다(작업 영역 규칙).

---

## 10. 문서 역할

| 파일 | 역할 |
| :--- | :--- |
| `PRD.md` | 무엇을 만드는지, 성공 기준, 제한 |
| `ARCHITECTURE.md` | 디렉터리, 프로세스, API, 데이터, 보안 경계 |
| `UI_SPEC.md` | 창·패널·토큰·문구·작업표시줄 |
| `YOUTUBE_OPS.md` | 복원, 개발, 시험, 빌드, 설치, 장애 |

같은 숫자를 네 문서에 길게 반복하지 않는다. 값이 하나만 있어야 하면 위 정본을 따른다.
