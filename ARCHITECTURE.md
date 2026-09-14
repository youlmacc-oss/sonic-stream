# Architecture Specification: SonicStream

## 0. 스택과 디렉터리

| Layer | 실제 스택 | 경로 |
| :--- | :--- | :--- |
| Frontend | Next.js **16.3.5** App Router, React 19.2, TypeScript, Tailwind CSS **v4** (`@import "tailwindcss"`), Framer Motion, lucide-react | `frontend/` |
| Backend | FastAPI + Uvicorn, yt-dlp, FFmpeg 6.x / LAME, sse-starlette | `backend/` (신규 생성) |
| Ephemeral Disk | `Path(tempfile.gettempdir()) / f"sonic_{job_id}"` | POSIX 관례: `/tmp/sonic_{job_id}` |

프론트 개발 서버는 `http://localhost:3000`, 백엔드는 `http://localhost:8000`이다. 브라우저는 백엔드를 **직접** 호출한다. 프론트에서 Next.js rewrite로 감싸지 않는 것이 기본이다.

권장 백엔드 레이아웃:

```text
backend/
  main.py              # FastAPI app, CORS, routers, lifespan GC sweep
  requirements.txt     # fastapi, uvicorn, yt-dlp, sse-starlette
  app/
    models.py          # Pydantic: InspectRequest, DownloadRequest, error payloads
    jobs.py            # In-memory JobStore + asyncio/thread worker
    ytdlp_engine.py    # inspect + download opts + progress_hook
    sse.py             # EventSourceResponse / 200ms ticker
    gc.py              # immediate + 10-minute sweep
```

Windows 로컬 개발을 1급 환경으로 취급한다. `/tmp`를 문자열로 하드코딩하지 말고 항상 `tempfile.gettempdir()`을 사용한다.

---

## 1. 시스템 구조도 (System Architecture Diagram)

```mermaid
flowchart TD
    subgraph Client ["Frontend (Next.js 16 App Router)"]
        UI["Page & Morphing Button UI"]
        ES["EventSource (SSE Consumer)"]
    end

    subgraph Server ["Backend (FastAPI Engine)"]
        API["FastAPI REST Router"]
        TaskManager["Background Job Manager"]
        ProgressBroadcaster["In-Memory SSE Event Queue"]
    end

    subgraph CoreEngine ["Media Processing Pipeline"]
        YTDL["yt-dlp Core"]
        FFMPEG["FFmpeg 6.x / LAME Muxer"]
        Disk[("Ephemeral Storage (sonic_{job_id})")]
    end

    UI -->|1. POST /api/inspect| API
    API -->|Quick Parse| YTDL
    API -->>|Return Meta JSON| UI

    UI -->|2. POST /api/download| API
    API -->|Spawn Job| TaskManager
    API -->>|Return job_id| UI

    ES -->|3. GET /api/progress/{job_id}| ProgressBroadcaster
    TaskManager -->|4. Stream Fetch & Hook| YTDL
    YTDL -->|Progress Tick| ProgressBroadcaster
    ProgressBroadcaster -->>|SSE Event Stream| ES

    YTDL -->|Raw Chunks| Disk
    TaskManager -->|5. Merge / ID3 Injection| FFMPEG
    FFMPEG -->|Final Media File| Disk

    ProgressBroadcaster -->>|6. Event: complete| ES
    ES -->|7. GET /api/fetch/{job_id}| API
    API -->|FileResponse Stream| UI
    API -.->|Trigger Cleanup| Disk
```

### 1.1 요청 수명주기

1. 사용자가 URL을 입력하거나 클립보드 붙여넣기를 한다.
2. 프론트가 600ms 디바운스 후 `POST /api/inspect`로 메타만 가져온다. 다운로드는 시작하지 않는다.
3. 사용자가 포맷/품질을 고르고 모핑 버튼을 누른다.
4. `POST /api/download`가 `job_id`를 반환한다 (`202`).
5. 프론트가 `GET /api/progress/{job_id}` EventSource를 연다.
6. 워커가 yt-dlp → FFmpeg/ID3 → `complete` 순으로 진행한다.
7. 프론트가 `GET /api/fetch/{job_id}`를 hidden anchor로 받아 저장한다.
8. 서버가 파일을 스트리밍한 뒤 즉시 GC를 예약하고, 최대 10분이면 강제 삭제한다.

---

## 2. API 엔드포인트 명세서

공통 규칙:

- JSON 요청/응답, UTF-8.
- 에러 바디: `{ "code": "INVALID_URL", "message": "유효한 동영상 링크를 입력해 주세요." }`
- 프론트 UI 상태명은 `format` (`'video' | 'audio'`)이지만, **HTTP 바디 필드명은 `type`** 이다. `DownloadButton`은 `{ url, type: format, quality }`로 POST한다.

### `POST /api/inspect`

Request Body:

```json
{ "url": "https://www.youtube.com/watch?v=..." }
```

Response `200`:

```json
{
  "title": "Starlight (Official Audio)",
  "author": "Muse",
  "duration": "04:00",
  "thumbnail": "https://i.ytimg.com/vi/.../maxresdefault.jpg"
}
```

구현 메모:

- `YoutubeDL({ "quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": True })`.
- `extract_flat`만으로 썸네일/길이가 비면 동일 URL에 대해 가벼운 `extract_info(download=False)` 한 번으로 보강한다. 스트림은 받지 않는다.
- `duration`은 초(int/float) → `MM:SS` 또는 `HH:MM:SS`.
- `author`는 `uploader` 또는 `channel` 또는 `artist`.
- 썸네일은 `thumbnails` 배열에서 가장 큰 width, 없으면 `thumbnail`.
- 라이브(`is_live` / `live_status=is_live`)면 `400` + `LIVE_STREAM`.

### `POST /api/download`

Request Body:

```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "type": "video",
  "quality": "1080p"
}
```

허용 값:

- `type`: `"video"` | `"audio"`
- `quality` (video): `"1080p"` | `"4k"`
- `quality` (audio): `"320k"` | `"flac"`

잘못된 조합(예: video + `320k`)은 `400` + `INVALID_URL`이 아니라 명시적 `PROCESS_FAILED` 또는 `422` validation error.

Response `202 Accepted`:

```json
{
  "job_id": "8f3b610c-f3e1-4c3e-9081-0df8e7b39a7b"
}
```

워커는 스레드 또는 `asyncio.to_thread`로 yt-dlp를 돌린다. yt-dlp는 동기 블로킹이므로 이벤트 루프를 막지 말 것.

### `GET /api/progress/{job_id}` (Server-Sent Events)

Headers:

- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`
- `Connection: keep-alive`
- `X-Accel-Buffering: no`

구현: `sse-starlette`의 `EventSourceResponse` 또는 동등한 raw generator. **0.2초 주기**로 최신 스냅샷을 밀어 보낸다.

#### Event: `progress`

```json
{
  "status": "downloading",
  "percent": 54.2,
  "speed": "6.4 MB/s",
  "eta": 8
}
```

- `percent`: 0~100 float, 소수 1자리.
- `speed`: 사람이 읽는 문자열. 바이트/초를 `KB/s` 또는 `MB/s`로 포맷.
- `eta`: 초 단위 int. 모르면 `null`.

#### Event: `processing`

```json
{
  "status": "processing",
  "detail": "최고 음질 변환 및 앨범 아트 임베딩 중..."
}
```

비디오 기본 카피: `"FFmpeg 패키징 및 태그 주입 중..."`  
오디오 기본 카피: `"최고 음질 변환 및 앨범 아트 임베딩 중..."`

processing 동안 게이지는 클라이언트에서 **95%로 고정**한다. 서버가 percent를 보내더라도 클라이언트는 95로 clamp 해도 된다.

#### Event: `complete`

```json
{
  "status": "done",
  "download_url": "http://localhost:8000/api/fetch/8f3b610c-f3e1-4c3e-9081-0df8e7b39a7b"
}
```

`download_url`은 절대 URL 또는 `/api/fetch/{job_id}` 상대 경로 모두 허용. 프론트는 상대 경로면 `http://localhost:8000`을 prefix 한다.

#### Event: `error`

```json
{
  "status": "error",
  "code": "GEO_RESTRICTED",
  "message": "이 영상은 지역 제한으로 받을 수 없습니다."
}
```

없는 `job_id`는 연결 직후 `error` + `JOB_NOT_FOUND`를 보내고 스트림을 닫는다.

### `GET /api/fetch/{job_id}`

최종 가공된 미디어 파일을 `FileResponse`로 스트리밍한다.

- `Content-Disposition: attachment; filename="Starlight (Official Audio).mp3"; filename*=UTF-8''...`
- `media_type`: mp4=`video/mp4`, mp3=`audio/mpeg`, flac=`audio/flac`
- 전송이 끝나거나 클라이언트가 연결을 끊으면 **즉시** 해당 `sonic_{job_id}` 디렉터리 삭제를 스케줄한다.
- 파일이 아직 준비되지 않았으면 `409` + `PROCESS_FAILED`가 아니라 `404`/`409`와 `JOB_NOT_FOUND` 또는 명시적 `NOT_READY` 메시지를 반환한다. 프론트는 complete 이후에만 fetch 하므로 정상 플로우에서는 발생하지 않아야 한다.

---

## 3. 핵심 다운로드 및 인코딩 파라미터

작업 출력 템플릿:

```python
outtmpl = str(job_dir / "%(title)s.%(ext)s")
```

공통 옵션:

```python
common = {
    "nocheckcertificate": True,
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "progress_hooks": [make_progress_hook(job_id)],
    "outtmpl": outtmpl,
}
```

라이브 스트림은 다운로드를 시작하지 않고 `LIVE_STREAM`으로 실패시킨다.

### 3.1 비디오 (1080p / 4K)

```python
ydl_opts = {
    "format": (
        "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        if quality == "1080p"
        else "bestvideo[height<=2160]+bestaudio/best"
    ),
    "merge_output_format": "mp4",
    "postprocessors": [
        {
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        },
        {"key": "FFmpegMetadata"},
    ],
    "postprocessor_args": {
        "ffmpeg": ["-movflags", "+faststart"],
    },
    "outtmpl": f"{job_dir}/%(title)s.%(ext)s",
}
```

- 비디오+오디오를 분리 수집한 뒤 MP4로 mux한다.
- `movflags +faststart`로 moov atom을 앞으로 옮겨 브라우저 재생/다운로드 호환을 확보한다.
- 가능하면 재인코딩 없이 copy, 컨테이너만 맞춘다. `FFmpegVideoConvertor`가 재인코딩을 강제하면 `FFmpegMerger`/`merge_output_format=mp4`를 우선하고 convertor는 fallback으로 둔다.

### 3.2 오디오 (320k MP3 + ID3 커버 아트 주입)

```python
ydl_opts = {
    "format": "bestaudio/best",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        },
        {"key": "FFmpegMetadata"},
        {"key": "EmbedThumbnail"},
    ],
    "writethumbnail": True,
    "outtmpl": f"{job_dir}/%(title)s.%(ext)s",
}
```

필수 동작:

1. 최상위 오디오 스트림 추출.
2. LAME/FFmpeg로 **320kbps CBR** MP3 변환.
3. 원본 썸네일 이미지를 받아 ID3 v2.3/v2.4 `APIC` 커버로 바이너리 주입 (`EmbedThumbnail`).
4. 제목/아티스트/채널을 `FFmpegMetadata`로 기록.

`EmbedThumbnail`이 webp를 거부하면 썸네일을 jpg로 변환하는 전처리(`FFmpegThumbnailsConvertor`, `format=jpg`)를 postprocessor 앞에 넣는다.

### 3.3 오디오 (FLAC 무손실)

```python
ydl_opts = {
    "format": "bestaudio/best",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "flac",
        },
        {"key": "FFmpegMetadata"},
        {"key": "EmbedThumbnail"},
    ],
    "writethumbnail": True,
    "outtmpl": f"{job_dir}/%(title)s.%(ext)s",
}
```

FLAC에도 커버/메타를 가능한 한 주입한다. 원본이 이미 FLAC이면 재인코딩 손실을 만들지 않도록 `preferredquality`를 강제하지 않는다.

---

## 4. 진행률 훅과 인메모리 Job Store

```python
jobs: dict[str, Job]  # process-local, 재시작 시 유실 허용 (ephemeral 제품)

class Job:
    id: str
    status: Literal["queued", "downloading", "processing", "done", "error"]
    percent: float
    speed: str
    eta: int | None
    detail: str
    download_url: str | None
    file_path: Path | None
    filename: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
```

`progress_hook(d)`:

- `d["status"] == "downloading"`: `percent = downloaded / total * 100`, speed/eta 포맷, job.status=`downloading`.
- `d["status"] == "finished"`: job.status=`processing`, percent=95, detail을 포맷에 맞게 설정.
- 예외: job.status=`error`, SSE `error` emit.

SSE 제너레이터는 `job_id` 키로 최신 Job 스냅샷을 0.2초마다 읽고, 상태 종류에 맞는 event name으로 직렬화한다. `done`/`error` emit 후 짧게 유지하고 스트림을 닫아도 된다.

---

## 5. 가비지 컬렉션

| 트리거 | 동작 |
| :--- | :--- |
| `GET /api/fetch` 응답 종료 (`BackgroundTask`) | 해당 `sonic_{job_id}` 디렉터리 삭제, Job 레코드 제거 가능 |
| Job `done` 후 10분 미fetch | 디렉터리 + 레코드 삭제 |
| Job `error` 후 즉시 또는 수 분 내 | 부분 파일 삭제 |
| App lifespan startup | `sonic_*` 중 mtime > 10분 전부 스윕 |

삭제 실패는 로깅만 하고 요청을 실패시키지 않는다. 다운로드 응답은 이미 나갔거나 나가야 한다.

---

## 6. CORS · 의존성 · 바이너리

FastAPI CORS:

```python
allow_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
allow_credentials = True
allow_methods = ["*"]
allow_headers = ["*"]
```

`requirements.txt` 최소셋:

```text
fastapi
uvicorn[standard]
yt-dlp
sse-starlette
python-multipart
```

호스트에 `ffmpeg`(및 오디오용 LAME 지원)가 PATH에 있어야 한다. 백엔드는 시작 시 `ffmpeg -version`을 확인하거나, 없으면 명확한 로그를 남긴다.

---

## 7. 프론트 연동 계약

| 파일 | 책임 |
| :--- | :--- |
| `frontend/src/app/page.tsx` | URL, format, quality 상태. 클립보드. 600ms 디바운스 Inspect. `MediaCard` 표시 |
| `frontend/src/components/MediaCard.tsx` | title/author/duration/thumbnail 렌더 |
| `frontend/src/components/DownloadButton.tsx` | POST download → EventSource → hidden `<a>` fetch → 상태 머신 |
| `frontend/src/app/globals.css` | Tailwind v4 import + shimmer + 캔버스 토큰 |

상수:

```ts
export const API_BASE = "http://localhost:8000";
```

`DownloadButton` 클릭 시 바디는 반드시:

```ts
{ url, type: format, quality }
```

`format` 필드로 POST하지 않는다. Phase 프롬프트의 구어 표현(`format`)은 UI prop 이름이며 와이어 프로토콜은 `type`이다.

EventSource는 브라우저 네이티브 `EventSource`를 사용한다. `addEventListener("progress" | "processing" | "complete" | "error")`. 언마운트/완료/에러 시 `close()` 필수.

파일 저장:

```ts
const a = document.createElement("a");
a.href = downloadUrl; // API_BASE prefix if relative
a.rel = "noopener";
document.body.appendChild(a);
a.click();
a.remove();
```

---

## 8. 엣지 케이스

- **긴 제목:** UI `truncate` + `title` tooltip. 파일명은 120~180자 클램핑, `<>:"/\|?*` 제거, 헤더는 `filename` ASCII fallback + `filename*`.
- **재생목록 URL:** `noplaylist: True`로 단일 항목만.
- **라이브:** Inspect 또는 Download 진입 즉시 `LIVE_STREAM`.
- **429 / bot check:** `RATE_LIMITED`, UI error 롤백.
- **지리적 제한:** `GEO_RESTRICTED`.
- **삭제/비공개:** `NOT_FOUND`.
- **Job TTL:** 10분 후 progress/fetch는 `JOB_NOT_FOUND`.
- **동시 작업:** 프로세스 메모리 dict로 다중 job 허용. 제품 UI는 버튼당 1 job.

이 문서가 파이프라인·엔드포인트·yt-dlp 옵션·GC의 단일 소스다. 시각 규칙은 `UI_SPEC.md`를 따른다.
