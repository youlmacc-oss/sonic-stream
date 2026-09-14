# UI/UX Specification: SonicStream

## 1. 디자인 원칙 & 토큰 (Tailwind CSS v4 기준)

- **테마:** 칠흑의 다크 모드 (Obsidian `#0B0C10`)를 캔버스로 사용하며, 고채도의 네온 시안(`#00F0FF`)과 인디고(`#6366F1`)로 액센트를 구성한다.
- **원칙:** Tailwind CSS v4의 `@import "tailwindcss";` 환경을 준수하며, 임의의 유틸리티 클래스가 누락되지 않도록 인라인 스타일과 표준 색상 클래스(`zinc-950`, `cyan-400` 등)를 조합한다.
- **현재 파일:** `frontend/src/app/globals.css`는 `@import "tailwindcss";` 한 줄만 있다. `DownloadButton`이 참조하는 `animate-shimmer`가 아직 없으므로 아래 `@theme` 블록을 **반드시** 추가한다.
- **금지:** `tailwind.config.js` v3 문법으로 되돌리기, `@tailwind base/components/utilities` 구식 지시어, 광고 배너, 새 탭 리다이렉트 CTA.

### 1.1 `globals.css` 필수 토큰

```css
@import "tailwindcss";

@theme {
  --color-obsidian: #0b0c10;
  --color-neon-cyan: #00f0ff;
  --color-accent-indigo: #6366f1;
  --animate-shimmer: shimmer 1.4s linear infinite;
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

html,
body {
  background-color: #0b0c10;
  color: #f4f4f5;
}
```

`layout.tsx`의 `<body>`는 `min-h-full flex flex-col bg-obsidian text-zinc-100 antialiased`를 유지/적용한다. 메타데이터 title은 `SonicStream`, description은 고품질 추출 한 줄 카피로 교체한다.

폰트는 기존 Geist / Geist Mono CSS variable을 사용한다. 메트릭(`MB/s`, `%`, ETA)은 `font-mono` 또는 Geist Mono.

### 1.2 색 사용 규칙

| 역할 | 토큰 / 클래스 | 용도 |
| :--- | :--- | :--- |
| Canvas | `#0B0C10` / `bg-obsidian` | 페이지 배경 |
| Surface | `bg-zinc-900/80`, `border-zinc-800` | 입력 박스, 카드 |
| Accent | `text-cyan-400`, `#00F0FF` | 로고 스팬, 아이콘, 활성 탭 |
| Secondary accent | `indigo-500`, `#6366F1` | 게이지 그라디언트 중간 |
| Gauge end | `fuchsia-500` | 게이지 우측 |
| Success | `emerald-400` | completed 글로우/카피 |
| Danger | `rose-400` | error 테두리/카피 |
| Muted | `text-zinc-400`, `placeholder-zinc-500` | 보조 카피 |

---

## 2. 화면 구성 요소 (Screen Components)

단일 페이지. 라우팅/모달/사이드바를 추가하지 않는다. 기존 골격은 `frontend/src/app/page.tsx`를 확장한다.

### 2.1 Hero & Smart Input

- 배지: `Ultra-Clean Downloader` + `Sparkles` 아이콘. `bg-cyan-950/60 border border-cyan-500/30 text-cyan-400`.
- 헤드라인: `Sonic` + `Stream`(`text-cyan-400`).
- 서브카피: `복잡한 선택지 없이, 오직 최고 품질의 1080p/4K 영상과 320kbps 음원만 다운로드합니다.`
- 입력 컨테이너: 반투명 블러 `w-full max-w-xl bg-zinc-900/80 border border-zinc-800 p-2 rounded-2xl shadow-2xl backdrop-blur-sm`.
- 클립보드 원클릭 붙여넣기(`Clipboard` 아이콘 버튼): `navigator.clipboard.readText()`를 호출하여 링크를 즉시 반영한다. 권한 거부 시 짧은 안내.
- **디바운스 600ms:** URL 입력 완료 감지 시 백그라운드에서 자동으로 `POST http://localhost:8000/api/inspect`를 호출한다. 길이 체크만으로 Unsplash 더미를 넣는 현재 로직은 제거한다.
- URL이 비거나 디바운스 도중 바뀌면 이전 Inspect 요청 결과를 폐기한다 (`AbortController` 권장).
- Inspect 실패 시 `MediaCard`를 숨기고 입력 하단 또는 버튼 `error`로 사유를 보여 준다. 페이지 전체를 죽이지 않는다.

### 2.2 미디어 인스펙션 카드 (`MediaCard.tsx`)

구현 파일은 이미 스펙에 가깝다. 동작을 고정한다.

- 입력된 링크가 유효하고 Inspect가 성공했을 때만 렌더한다.
- `Framer Motion`의 페이드인-슬라이드업 (`initial={{ opacity: 0, y: 15 }}` → `animate={{ opacity: 1, y: 0 }}`, duration 0.3s).
- 16:9 고화질 썸네일 (`aspect-video`, `object-cover`).
- 영상 길이 오버레이 배지: `absolute bottom-1.5 right-1.5 bg-black/80 text-white text-[10px] font-mono`.
- 볼드 타이틀 `truncate` + `title={media.title}`로 긴 제목 툴팁.
- 채널(`User` 아이콘) / 재생 시간(`Clock` 아이콘).
- 카드 셸: `w-full max-w-xl bg-zinc-900/60 border border-zinc-800 rounded-2xl p-4 mb-6 backdrop-blur-md`.

`MediaCard`에 네트워크 호출을 넣지 않는다. 데이터는 부모가 주입한다.

### 2.3 듀얼 세그먼트 포맷 & 품질 셀렉터

- 비디오(`MP4`) 탭과 오디오(`MP3`) 탭 전환. 활성 탭: `bg-zinc-800 text-cyan-400`.
- 탭 전환 시 품질 기본값: video→`1080p`, audio→`320k`.
- 포맷 선택에 따라 품질 칩 동적 전환:
  - 비디오: `1080p FHD (표준)` vs `4K UHD (최고화질)`
  - 오디오: `320kbps CBR (최고음질)` vs `FLAC (무손실)`
- 활성 칩: `bg-cyan-500/20 text-cyan-300 border border-cyan-500/40`.
- 저화질/저비트레이트 칩을 추가하지 않는다.
- 탭 전환은 짧은 crossfade/layout animation을 허용하되 레이아웃 점프는 금지한다.

상태 모델 (`page.tsx`):

```ts
url: string
format: 'video' | 'audio'
quality: '1080p' | '4k' | '320k' | 'flac'
mediaInfo: { title, author, duration, thumbnail } | null
inspectError?: string | null
```

### 2.4 버튼-투-게이지 모핑 (`DownloadButton.tsx`) 상태 머신

버튼은 `w-full max-w-xl h-14 rounded-2xl` 고정 높이다. 상태 전환에서 높이/폭이 바뀌면 안 된다 (CLS 금지, 60fps).

현재 코드는 `idle | inspecting | downloading | completed`와 mock interval만 있다. **`processing`과 `error`를 추가**하고 mock 타이머를 전부 제거한다.

| 상태 (Status) | 시각적 표현 및 애니메이션 | 메트릭 표기 |
| :--- | :--- | :--- |
| **`idle`** | 짙은 Zinc 배경 + 테두리 호버 효과 | `[⬇ 비디오 다운로드 (1080P)]` • `~128 MB` |
| **`inspecting`** | 버튼 비활성화, 스피너 회전 애니메이션 | `"최적 고화질 스트림 분석 중..."` |
| **`downloading`** | 버튼 내부에서 시안-인디고-자홍 그라디언트 바가 실시간 퍼센트로 차오름 (쉬머 하이라이트) | `"다운로드 중..."` • `4.8 MB/s` • `ETA: 6s` • `68%` |
| **`processing`** | 바가 95% 지점에 고정되며 펄스 인디케이터 동작 | `"FFmpeg 패키징 및 태그 주입 중..."` |
| **`completed`** | 에메랄드 그린(`emerald-400`) 글로우와 함께 체크마크(`✓`) 표기 | `"✓ 다운로드 완료!"` (3초 후 idle 복귀) |
| **`error`** | 로즈 레드(`rose-400`) 테두리 및 에러 메시지 노출 | `"다운로드 실패 (재시도)"` |

#### idle

- 좌측: `Download` 아이콘 + `비디오 다운로드 (1080P)` 또는 `음원 추출 (320K)`.
- 우측 예상 용량(가이드): video `1080p` → `~128 MB`, video `4k` → `~420 MB`, audio `320k` → `~9.5 MB`, audio `flac` → `~28 MB`.
- 호버: `hover:border-zinc-500`.
- URL이 비어 있으면 클릭 시 알림/인라인 경고. 네트워크 호출 없음.

#### inspecting

- 다운로드 직후 서버가 job을 받기 전, 또는 명시적 분석 단계.
- `Loader2` `animate-spin` + `최적 고화질 스트림 분석 중...` / `최적 고화질 스트림 파싱 중...` 중 하나로 통일. **권장 카피:** `최적 고화질 스트림 분석 중...`
- 버튼 `disabled`.

#### downloading

- Fill: `bg-gradient-to-r from-cyan-500 via-indigo-500 to-fuchsia-500 opacity-80`.
- width는 SSE `percent`에 `easeOut` 0.2s. `Math.min(percent, 100)`.
- 쉬머: `from-transparent via-white/20 to-transparent animate-shimmer`. 부모 `overflow-hidden`.
- HUD: ping 닷 + `다운로드 중...` + `{speed} • ETA: {n}s` + `{n}%`.
- 속도/ETA는 목업 문자열(`4.8 MB/s` 하드코딩)을 쓰지 않고 SSE 값을 그대로 표시한다.

#### processing

- 바 width **95% 고정**, 약한 pulse (`animate-pulse` 또는 닷 ping).
- 카피: 비디오 `"FFmpeg 패키징 및 태그 주입 중..."`, 오디오 `"최고 음질 변환 및 앨범 아트 임베딩 중..."`. 서버 `detail`이 있으면 서버 문구 우선.

#### completed

- `text-emerald-400`, `Check` 아이콘, `✓ 다운로드 완료!`
- 버튼/카드에 emerald 글로우 (`shadow-[0_0_24px_rgba(52,211,153,0.35)]` 수준).
- **3초 후** `idle`, progress 0. 기존 코드의 4초는 3초로 맞춘다.
- complete 이벤트에서 hidden `<a>`로 `download_url`을 즉시 친다.

#### error

- `border-rose-400`, `text-rose-400`.
- 기본 카피 `다운로드 실패 (재시도)`. `message`가 있으면 짧게 함께 표시.
- 클릭 시 동일 url/type/quality로 재시도. disabled 아님.

### 2.5 모션 규칙

- `framer-motion` `AnimatePresence mode="wait"`로 라벨만 교체. 버튼 박스 자체는 리마운트하지 않는다.
- 게이지 width만 애니메이션. 레이아웃 속성(height, margin) 애니메이션 금지.
- 목표 60fps. 매 SSE 틱마다 전체 트리를 리렌더하지 말고 progress 숫자 상태만 갱신.

---

## 3. 프론트 네트워크 시퀀스

```text
page.tsx
  url change → 600ms debounce → POST /api/inspect → setMediaInfo | inspectError

DownloadButton
  click
    → set inspecting
    → POST /api/download { url, type: format, quality }
    → job_id
    → EventSource(GET /api/progress/{job_id})
        progress    → downloading + percent/speed/eta
        processing  → processing + detail
        complete    → <a>.click(download_url) → completed → 3s → idle
        error       → error (retryable)
```

- EventSource는 `http://localhost:8000/api/progress/{job_id}`.
- complete/error/unmount에서 `es.close()`.
- CORS 실패는 error 상태로 보여 주고 콘솔에만 남기지 않는다.

---

## 4. 카피 인벤토리 (ko)

| 위치 | 문구 |
| :--- | :--- |
| Hero badge | Ultra-Clean Downloader |
| Hero title | SonicStream |
| Hero sub | 복잡한 선택지 없이, 오직 최고 품질의 1080p/4K 영상과 320kbps 음원만 다운로드합니다. |
| Input placeholder | 동영상 링크를 붙여넣으세요 (예: YouTube URL) |
| Paste | 붙여넣기 |
| Tab video | 비디오 (MP4) |
| Tab audio | 오디오 (MP3) |
| Quality | 1080p FHD (표준) / 4K UHD (최고화질) / 320kbps CBR (최고음질) / FLAC (무손실) |
| Idle video | 비디오 다운로드 ({QUALITY}) |
| Idle audio | 음원 추출 ({QUALITY}) |
| Inspecting | 최적 고화질 스트림 분석 중... |
| Downloading | 다운로드 중... |
| Processing video | FFmpeg 패키징 및 태그 주입 중... |
| Processing audio | 최고 음질 변환 및 앨범 아트 임베딩 중... |
| Completed | ✓ 다운로드 완료! |
| Error | 다운로드 실패 (재시도) |
| Empty URL | 먼저 동영상 링크를 입력해 주세요! |

이 문서가 시각·카피·상태 머신의 단일 소스다. API 필드와 yt-dlp 옵션은 `ARCHITECTURE.md`를 따른다.
