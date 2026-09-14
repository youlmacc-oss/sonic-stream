# PRD: SonicStream (소닉스트림)

## 1. 프로젝트 개요 (Executive Summary)

SonicStream은 복잡하고 불필요한 저화질/저음질 규격을 과감히 배제하고, **1080p FHD / 4K UHD 비디오와 320kbps MP3 / FLAC 무손실 음원**이라는 표준 이상의 고품질 미디어 추출에만 집중하는 상업용 수준의 미니멀 웹 유틸리티 서비스다.

광고, 가짜 다운로드 유도 버튼, 복잡한 포맷 옵션을 완전히 걷어내고, 링크 입력부터 다운로드 완료까지 버튼 내부에서 실시간 진행 상황이 펼쳐지는 **버튼-투-게이지 모핑(Button-to-Gauge Morphing)** 인터랙션을 통해 압도적인 완성도를 제공한다.

제품의 핵심 약속은 세 가지다.

1. **품질만 남긴다.** 240p~720p, 128kbps~192kbps 같은 저품질 선택지는 존재하지 않는다.
2. **대기 화면을 없앤다.** 분석, 전송, FFmpeg 패키징, ID3 커버 주입, 완료까지 모두 단일 버튼 안에서 실시간으로 보인다.
3. **설치 프로그램을 요구하지 않는다.** 브라우저는 SSE로 진행률을 구독하고, 완료 즉시 네이티브 파일 다운로드를 트리거한다.

---

## 2. 타깃 유저 및 핵심 시나리오

- **콘텐츠 크리에이터 & 에디터:** 편집 소스로 사용할 선명한 1080p 60fps 또는 4K 원본급 영상 클립이 즉시 필요한 사용자.
- **오디오 애호가 & 음악 수집가:** 커버 아트 썸네일과 곡 정보(ID3 Tag)가 완벽히 주입된 320kbps 고음질 MP3 또는 무손실 FLAC 소스가 필요한 사용자.

### 2.1 대표 시나리오

| 시나리오 | 사용자 행동 | 기대 결과 |
| :--- | :--- | :--- |
| 원클릭 붙여넣기 | 클립보드 아이콘 클릭 | URL 즉시 반영 → 600ms 디바운스 후 자동 Inspect |
| 고화질 클립 추출 | 비디오 탭 + 1080p 또는 4K 선택 후 다운로드 | MP4 단일 컨테이너, `faststart` 적용, 브라우저 파일 저장 |
| 앨범아트 음원 추출 | 오디오 탭 + 320k 또는 FLAC 선택 후 다운로드 | ID3/Vorbis 메타 + 커버 아트가 주입된 파일 저장 |
| 실패 복구 | 429 / 지리적 제한 / 삭제된 영상 | 명확한 에러 코드와 사유 표시, 버튼이 `error` → 재시도 가능 상태로 롤백 |

---

## 3. 기능 스코프 (Scope Matrix)

| 구분 | In-Scope (핵심 제공 기능) | Out-of-Scope (의도적 배제) |
| :--- | :--- | :--- |
| **비디오** | • 1080p FHD (기본 권장, MP4/H.264)<br>• 4K UHD (2160p, MP4 원본 유지) | 240p, 360p, 480p, 720p 등 저화질 선택지 배제 |
| **오디오** | • MP3 320kbps CBR (최고 음질, ID3 태그 자동 주입)<br>• FLAC (무손실 오디오) | 128kbps, 192kbps 등 압축 손실률이 높은 음질 배제 |
| **UI/UX** | • 원클릭 클립보드 붙여넣기<br>• 비디오 썸네일/재생시간/제목 인스펙트 카드<br>• 인라인 버튼-투-게이지 모핑 프로그레스 바 | 조잡한 팝업 광고, 새 탭 리다이렉트, 배너 광고 전면 배제 |
| **다운로드** | • SSE 기반 실시간 전송 속도 및 진행률(%) 표기<br>• 브라우저 기본 파일 스트림 자동 트리거 | 별도의 설치 프로그램 강제 유도 배제 |

---

## 4. 세부 기능 요구사항 (Functional Requirements)

### 4.1 링크 검증 및 메타데이터 파싱 (Inspect)

- 입력된 URL의 유효성을 정규식으로 검증한다. 최소 조건은 `http(s)` 스킴과 호스트가 존재하는 미디어 URL이다.
- YouTube(`youtube.com`, `youtu.be`), 그리고 `yt-dlp`가 지원하는 동일 계열 링크를 1차 타깃으로 한다.
- `yt-dlp`의 `extract_flat=True` / `skip_download=True` 모드를 활용하여 스트림 다운로드 없이 **800ms 이내**에 제목, 채널명, 재생 시간, 최고해상도 썸네일 URL을 파싱해 클라이언트에 반환한다.
- 프론트엔드는 URL 입력 완료를 **600ms 디바운스**로 감지한 뒤 `POST /api/inspect`를 자동 호출한다. 더미/하드코딩 프리뷰 데이터는 금지한다.
- 재생 시간은 `HH:MM:SS` 또는 `MM:SS` 문자열로 정규화한다. 예: `240`초 → `04:00`.
- 썸네일은 가능한 한 `maxresdefault` / 최고 해상도 URL을 우선한다.

**Inspect 성공 응답 계약**

```json
{
  "title": "Starlight (Official Audio)",
  "author": "Muse",
  "duration": "04:00",
  "thumbnail": "https://i.ytimg.com/vi/.../maxresdefault.jpg"
}
```

### 4.2 다운로드 작업 및 포맷팅 (Process & Muxing)

- **비디오 다운로드:** 비디오 스트림과 최상위 오디오 스트림을 분리 수집한 뒤, `FFmpeg`를 통해 `movflags +faststart` 옵션을 적용한 MP4 단일 컨테이너로 무손실 병합(Muxing)한다.
  - `1080p`: `bestvideo[height<=1080]+bestaudio/best[height<=1080]`
  - `4k`: `bestvideo[height<=2160]+bestaudio/best`
- **오디오 다운로드:** 원본 오디오 스트림을 추출한다.
  - `320k`: `LAME`/`FFmpegExtractAudio`로 320kbps CBR MP3 변환. 동시에 원본 썸네일을 다운로드하여 **ID3 v2.3/v2.4** 규격 커버 아트로 바이너리 주입한다. `FFmpegMetadata` + `EmbedThumbnail` 필수.
  - `flac`: 무손실 FLAC 추출. 가능한 한 커버 아트와 메타데이터를 함께 임베드한다.
- 작업은 즉시 실행하지 않고 `job_id`(UUID4)를 발급한 뒤 백그라운드 잡으로 처리한다. API는 `202 Accepted`와 `job_id`만 반환한다.

### 4.3 실시간 텔레메트리 (SSE Progress Engine)

- `yt-dlp` 내장 `progress_hooks`를 통해 전송률, 다운로드 속도(MB/s), 예상 소요 시간(ETA)을 수집한다.
- Server-Sent Events(SSE) 파이프라인으로 클라이언트에 **0.2초 주기**로 상태를 브로드캐스팅한다.
- 이벤트 종류는 최소 다음 네 가지다.

| Event | 의미 | 필수 페이로드 |
| :--- | :--- | :--- |
| `progress` | 원본 스트림 수신 중 | `status=downloading`, `percent`, `speed`, `eta` |
| `processing` | FFmpeg mux / ID3 주입 중 | `status=processing`, `detail` |
| `complete` | 최종 파일 준비 완료 | `status=done`, `download_url` |
| `error` | 복구 가능한 실패 | `status=error`, `code`, `message` |

- 클라이언트는 `complete`를 수신하면 hidden `<a download>`를 프로그래밍 방식으로 클릭하여 브라우저 기본 저장을 트리거한다.

### 4.4 버튼-투-게이지 모핑 (Button-to-Gauge Morphing)

다운로드 CTA는 페이지를 떠나지 않는다. 버튼 자체가 상태 머신이며, 레이아웃 시프트 없이 내부 HUD만 교체된다.

| 상태 | 사용자에게 보이는 것 |
| :--- | :--- |
| `idle` | 포맷/품질이 반영된 CTA + 예상 용량 |
| `inspecting` | 스피너 + 스트림 분석 카피 |
| `downloading` | 시안-인디고-자홍 그라디언트 게이지 + `%` / `MB/s` / `ETA` |
| `processing` | 게이지 95% 고정 + 펄스 + FFmpeg/ID3 카피 |
| `completed` | 에메랄드 체크마크. **3초 후 `idle` 복귀** |
| `error` | 로즈 테두리 + 실패 사유. 재클릭으로 재시도 |

상세 시각 규칙은 `UI_SPEC.md`가 단일 소스다.

---

## 5. 비기능적 요구사항 및 리소스 수명주기 (Non-Functional Requirements)

### 5.1 임시 파일 가비지 컬렉션 (GC)

- 작업별 작업 디렉터리는 `tempfile.gettempdir()` 하위의 `sonic_{job_id}` 이다. POSIX에서는 관례적으로 `/tmp/sonic_{job_id}`와 동일하다. Windows에서도 `/tmp` 하드코딩을 쓰지 않는다.
- 다운로드 완료 후 생성된 미디어 파일은 **클라이언트 전송 완료 즉시**, 또는 전송이 끝나지 않아도 **최대 10분 후** 작업 디렉터리에서 자동 삭제한다.
- `complete` 이후 fetch되지 않은 잡, 실패한 잡, 중단된 잡 모두 GC 대상이다.
- 프로세스 시작 시 만료된 `sonic_*` 잔존 디렉터리를 한 번 스윕한다.

### 5.2 예외 처리

원본 플랫폼의 봇 차단(HTTP 429), 지리적 제한, 삭제된 동영상, 라이브 스트림, 비공개 영상 요청 시 클라이언트에 명확한 에러 코드와 사유를 반환하고 UI를 **재시도 가능** 상태로 롤백한다. 무한 스피너/행(hang)은 결함이다.

| Code | 조건 | 사용자 메시지 (ko) |
| :--- | :--- | :--- |
| `INVALID_URL` | 정규식/스킴 실패, 빈 값 | 유효한 동영상 링크를 입력해 주세요. |
| `UNSUPPORTED_URL` | yt-dlp가 추출 불가 | 지원하지 않는 링크입니다. |
| `NOT_FOUND` | 삭제/비공개 | 영상을 찾을 수 없습니다. |
| `GEO_RESTRICTED` | 지역 제한 | 이 영상은 지역 제한으로 받을 수 없습니다. |
| `RATE_LIMITED` | HTTP 429 / 봇 차단 | 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요. |
| `LIVE_STREAM` | 진행 중 라이브 | 라이브 스트림은 지원하지 않습니다. |
| `JOB_NOT_FOUND` | 알 수 없는 job_id | 다운로드 작업을 찾을 수 없습니다. |
| `PROCESS_FAILED` | FFmpeg/yt-dlp 실패 | 변환에 실패했습니다. 다시 시도해 주세요. |
| `TIMEOUT` | 과도한 대기 | 시간이 초과되었습니다. 다시 시도해 주세요. |

Inspect와 Download는 위 코드를 JSON으로 반환한다. SSE 경로에서는 `event: error`로 동일 계약을 보낸다.

### 5.3 성능 · 보안 · 운영

- Inspect P95 목표: **800ms** (네트워크/원본 플랫폼 지연 제외 시 파싱 경로 기준).
- SSE 틱 주기: **200ms**. 동일 percent를 연속 송출하지 않도록 변화분 또는 주기 중 하나를 만족할 때만 emit 해도 된다. 다만 클라이언트는 0.2초 단위 갱신을 가정한다.
- CORS: 개발 환경에서 `http://localhost:3000`을 허용한다.
- 파일명: 원본 제목을 사용하되 Windows/HTTP 헤더에 위험한 문자는 제거한다. 긴 제목은 UI에서 `truncate`, `Content-Disposition`은 RFC 5987 `filename*`를 함께 넣는다.
- 비밀키, 광고 SDK, 트래커, 설치형 클라이언트는 도입하지 않는다.

---

## 6. 현재 구현 대비 갭 (Agent가 채워야 할 상태)

문서 작성 시점의 레포 상태. Composer는 이 갭을 기준으로 코드를 완성한다.

| 영역 | 현재 | 목표 |
| :--- | :--- | :--- |
| Frontend | Next.js 16.3.5 App Router, React 19, Tailwind CSS v4, Framer Motion, lucide-react | 유지. 목업을 실제 API/SSE로 교체 |
| `page.tsx` | URL 길이 > 10이면 Unsplash 더미 `mediaInfo` 세팅 | 600ms 디바운스 후 `POST /api/inspect` |
| `DownloadButton.tsx` | `setTimeout`/`setInterval` 가짜 진행률. `processing`/`error` 상태 없음 | 실제 `POST /api/download` + EventSource + 자동 fetch |
| `MediaCard.tsx` | 16:9 썸네일, truncate 타이틀, 채널/길이. 스펙과 거의 일치 | Inspect 실데이터만 연결 |
| `globals.css` | `@import "tailwindcss";` 만 존재. `animate-shimmer` 미정의 | `@theme` 토큰 + shimmer keyframes |
| `layout.tsx` | Create Next App 기본 메타/배경 | Obsidian 캔버스, SonicStream 메타 |
| Backend | **디렉터리 없음** | FastAPI + yt-dlp + SSE + FileResponse + GC |

---

## 7. 성공 기준 (Definition of Done)

1. 유효한 YouTube URL을 붙여넣으면 800ms급 Inspect 카드가 실제 제목/채널/길이/썸네일로 등장한다.
2. 비디오 1080p/4K, 오디오 320k/FLAC 중 하나를 고르고 버튼을 누르면 `job_id`가 발급되고 버튼이 게이지로 모핑된다.
3. SSE로 `%`, `MB/s`, `ETA`가 갱신되고, processing 구간에서 FFmpeg/ID3 카피가 보인다.
4. `complete` 후 파일이 브라우저에 저장되며, MP3에는 커버 아트가 들어 있다.
5. 실패 시 행하지 않고 `error`로 롤백되며 재시도가 가능하다.
6. fetch 직후 또는 10분 후 `sonic_{job_id}` 작업 디렉터리가 삭제된다.
7. 광고, 저품질 옵션, 설치 프로그램, 더미 진행률 타이머가 코드에 남아 있지 않다.

구현 디테일의 단일 소스는 `ARCHITECTURE.md`, 시각/인터랙션의 단일 소스는 `UI_SPEC.md`, 단계별 실행 지시는 `PROMPTS.md`다.
