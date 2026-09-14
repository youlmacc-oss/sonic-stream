# Cursor Composer Agent Prompts

아래 프롬프트들을 Cursor의 **Composer (Agent 모드, `Ctrl + I` 또는 `Cmd + I`)**에 단계별로 입력하여 구현을 완성한다.

에이전트는 코드를 짜기 전에 반드시 `PRD.md`, `ARCHITECTURE.md`, `UI_SPEC.md`를 읽고, 이 세 문서를 추측보다 우선한다.

**와이어 프로토콜 주의:** UI prop 이름은 `format`이지만 `POST /api/download` JSON 필드명은 `type`이다. 바디는 `{ url, type, quality }`이다.

**현재 레포 팩트:**

- 프론트는 `frontend/` (Next.js 16.3.5, React 19, Tailwind v4, Framer Motion).
- `page.tsx` Inspect는 Unsplash 더미, `DownloadButton.tsx`는 setInterval 목업.
- `backend/`는 아직 없다. Phase 1에서 생성한다.
- `globals.css`에 `animate-shimmer`가 없다. Phase 2에서 `UI_SPEC.md` 토큰을 넣는다.
- 임시 디렉터리는 `/tmp` 하드코딩이 아니라 `tempfile.gettempdir() / sonic_{job_id}` (Windows 호환).

---

### [Phase 1: 백엔드 다운로드 및 SSE 스트리밍 완성]

```text
Read PRD.md and ARCHITECTURE.md.
Look at /backend/main.py (create backend/ if it does not exist).

Implement the full production-ready download and streaming pipeline:
1. Update POST /api/inspect to reliably return video title, author, duration, and thumbnail using yt-dlp.
   - Validate URL. Reject live streams with code LIVE_STREAM.
   - Use skip_download / extract_flat first; fall back to extract_info(download=False) if metadata is thin.
   - Normalize duration to MM:SS or HH:MM:SS. Prefer highest-resolution thumbnail.
   - Return the exact JSON contract in ARCHITECTURE.md. Errors use { code, message }.
2. Implement POST /api/download that accepts { url, type, quality }, generates a unique job_id (uuid4), and starts a background thread/async task.
   - type: "video" | "audio"
   - quality: "1080p" | "4k" | "320k" | "flac"
   - Respond 202 { job_id }. Do not block the event loop on yt-dlp.
3. In the background task, run yt-dlp with the exact format/postprocessor settings specified in ARCHITECTURE.md:
   - For Video: merge 1080p/4K with best audio into MP4 container, movflags +faststart.
   - For Audio 320k: extract 320k MP3 using FFmpegExtractAudio, embed thumbnail using EmbedThumbnail, inject ID3 metadata via FFmpegMetadata, writethumbnail=True. Convert webp thumbs to jpg if needed.
   - For Audio flac: FFmpegExtractAudio preferredcodec=flac + metadata + EmbedThumbnail.
   - Write into tempfile.gettempdir()/sonic_{job_id}/ (never hardcode POSIX-only /tmp on Windows).
   - Attach a yt-dlp progress_hook that publishes { percent, speed, eta, status } to an in-memory queue/dict keyed by job_id.
   - When yt-dlp finishes download and postprocessors start, set status=processing.
4. Implement GET /api/progress/{job_id} using sse-starlette or raw EventSourceResponse (text/event-stream) to broadcast real-time metrics every 0.2s.
   - Event progress: { status, percent, speed, eta }
   - Event processing: { status, detail }
   - When complete, emit event: 'complete' with download_url: '/api/fetch/{job_id}' (or absolute localhost:8000 URL).
   - On failure emit event: 'error' with { status, code, message } from the PRD error table (429, geo, deleted, live, etc.).
5. Implement GET /api/fetch/{job_id} to serve the processed file via FileResponse with proper filename attachment headers (filename + filename*), correct media_type, and schedule temporary file deletion immediately after send. Also sweep sonic_* dirs older than 10 minutes on startup and via a TTL.
6. Add CORS for http://localhost:3000 and http://127.0.0.1:3000.
Ensure all necessary python packages (fastapi, uvicorn, yt-dlp, sse-starlette) are in backend/requirements.txt.
Do not implement the frontend in this phase.
```

---

### [Phase 2: 프론트엔드 모핑 버튼과 SSE 엔드투엔드 연결]

```text
Read UI_SPEC.md, PRD.md, and ARCHITECTURE.md.
Look at /frontend/src/components/DownloadButton.tsx, /frontend/src/components/MediaCard.tsx, /frontend/src/app/page.tsx, /frontend/src/app/globals.css, and /frontend/src/app/layout.tsx.

Wire up the actual backend download flow and finish the visual spec:
1. In page.tsx, remove the Unsplash/dummy mediaInfo simulation.
   - Debounce URL input by 600ms, then POST http://localhost:8000/api/inspect { url }.
   - On success show MediaCard with real title/author/duration/thumbnail.
   - Abort in-flight inspect when the URL changes. Clear the card when the input is empty or inspect fails.
   - Keep clipboard paste via navigator.clipboard.readText().
2. In DownloadButton.tsx, replace the mock interval timer with real network calls. Add missing statuses: processing, error.
   - On click: POST to http://localhost:8000/api/download with { url, type: format, quality } (wire field is type, not format).
   - Receive job_id, switch status to 'downloading' (inspecting is allowed only as a brief pre-job state), and open an EventSource connection to http://localhost:8000/api/progress/{job_id}.
   - On 'progress' event: update progress percentage, speed (MB/s), and ETA smoothly from the payload. No hardcoded 4.8 MB/s.
   - On 'processing' event: lock the gauge at 95% and set status text to the server detail or the UI_SPEC FFmpeg/ID3 copy.
   - On 'complete' event: trigger automatic browser file download by programmatically clicking a hidden <a> tag targeting data.download_url (prefix http://localhost:8000 if relative), then set status to 'completed'. Return to idle after 3 seconds (not 4).
   - On error: handle gracefully, show rose-400 retry UI, allow retry. Always close EventSource on complete/error/unmount.
3. Apply UI_SPEC.md Tailwind CSS v4 styling:
   - Add @theme tokens, shimmer keyframes, and Obsidian #0B0C10 canvas in globals.css so animate-shimmer actually works.
   - Update layout metadata to SonicStream and apply the dark canvas classes.
   - Ensure button-to-gauge morphing animations run at 60fps without layout shifts (fixed h-14, AnimatePresence on labels only).
   - completed uses emerald-400 glow + checkmark; error uses rose-400.
Do not weaken the quality-only chip set (1080p/4K/320k/FLAC only).
```

---

### [Phase 3: 엔드투엔드 검증 및 엣지 케이스 방어]

```text
Review both /frontend and /backend implementations against PRD.md, ARCHITECTURE.md, and UI_SPEC.md.

1. Confirm CORS handling in backend for localhost:3000 and 127.0.0.1:3000.
2. Verify that long video titles do not break the UI layout (truncate + title tooltip) or filename headers (sanitize + filename*).
3. Test edge cases: invalid URLs, live streams, or geo-restricted videos should return clean error feedback to the user rather than hanging indefinitely. Map platform failures to PRD codes: INVALID_URL, UNSUPPORTED_URL, NOT_FOUND, GEO_RESTRICTED, RATE_LIMITED, LIVE_STREAM, JOB_NOT_FOUND, PROCESS_FAILED, TIMEOUT.
4. Confirm GC: files live under tempfile.gettempdir()/sonic_{job_id}, delete after fetch and after a 10-minute TTL, sweep leftovers on startup.
5. Confirm audio 320k writes ID3/cover via EmbedThumbnail + FFmpegMetadata, and video mux uses MP4 + faststart.
6. Confirm the frontend never POSTs { format } to /api/download — only { url, type, quality }.
7. Remove leftover mock timers, dummy thumbnails, and unused simulation state.
8. Clean up any TypeScript lint warnings and Python typing warnings.

If something is missing versus the three spec docs, implement it. Do not invent low-quality format options, ads, or installer prompts.
```

---

## 다음 단계 진행 방법

1. 위 내용으로 4개의 마크다운 파일(`PRD.md`, `ARCHITECTURE.md`, `UI_SPEC.md`, `PROMPTS.md`)이 프로젝트 루트 `sonic-stream/`에 저장되어 있는지 확인한다.
2. Cursor에서 `Ctrl + I`(Mac: `Cmd + I`)를 눌러 **Composer Agent**를 연다.
3. `PROMPTS.md`의 **[Phase 1]** 프롬프트를 복사해 Composer에 바로 입력하면, Cursor가 백엔드 전체 파이프라인(SSE 스트리밍, FFmpeg 연동, ID3 썸네일 주입, 파일 다운로드, 자동 GC)을 구축한다.
4. Phase 1이 끝나면 **[Phase 2]**로 프론트 모핑 버튼과 Inspect 디바운스를 실제 API에 연결한다.
5. **[Phase 3]**으로 CORS, 긴 제목, 라이브/429/지리적 제한, 린트, 목업 잔존을 닫는다.

Phase를 건너뛰지 않는다. 백엔드 없이 Phase 2를 실행하면 EventSource가 실패한다.
