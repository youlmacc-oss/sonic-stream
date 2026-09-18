import { apiInit, getApiBase } from '@/lib/constants';
import { isLoopbackHost } from '@/lib/site';
import { applyWindowBox, clampWindowToWorkArea, fitWindowInWorkArea, windowOpenFeatures } from '@/lib/workArea';

export const SEARCH_CHANNEL = 'sonicstream.search.v1';

export interface SearchHit {
  title: string;
  author: string;
  url: string;
  thumbnail: string;
  duration: string;
  duration_known?: boolean;
  views?: string;
}

function placeOpenedWindow(popup: Window | null, box: ReturnType<typeof fitWindowInWorkArea>) {
  if (!popup) return;
  applyWindowBox(popup, box);
  window.setTimeout(() => applyWindowBox(popup, box), 50);
  window.setTimeout(() => clampWindowToWorkArea(popup), 200);
}

function openProgramWindow(url: string, name: string, width: number, height: number) {
  const box = fitWindowInWorkArea(width, height);
  const popup = window.open(url, name, windowOpenFeatures(box));
  placeOpenedWindow(popup, box);
}

export function openHelpWindow() {
  openProgramWindow(`${window.location.origin}/help`, 'sonicstream-help', 560, 640);
}

export function openInstallWindow() {
  openProgramWindow(`${window.location.origin}/install`, 'sonicstream-install', 640, 760);
}

export async function openMainWindow() {
  const desktop = isLoopbackHost(window.location.hostname);
  const url = desktop ? `${window.location.origin}/` : `${window.location.origin}/?devpc=1`;
  if (window.opener && !window.opener.closed) {
    try {
      window.opener.focus();
    } catch {
      // opener blocked — desktop API still brings the main window forward
    }
  }
  if (desktop) {
    try {
      const response = await fetch(`${getApiBase()}/api/local/window`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'open_main' }),
        ...apiInit(),
      });
      if (response.ok) return;
    } catch {
      // browser-only session
    }
  }
  const box = fitWindowInWorkArea(1280, 800);
  const popup = window.open(url, 'sonicstream-main', windowOpenFeatures(box));
  placeOpenedWindow(popup, box);
  popup?.focus();
}

export function openAiChatWindow(query?: string) {
  const q = (query || '').trim();
  const url = q
    ? `${window.location.origin}/ai?q=${encodeURIComponent(q)}`
    : `${window.location.origin}/ai`;
  openProgramWindow(url, 'sonicstream-ai', 1220, 840);
}

export function youtubeVideoId(url: string): string | null {
  const match = url.match(/(?:v=|youtu\.be\/|shorts\/|embed\/)([A-Za-z0-9_-]{11})/);
  return match?.[1] || null;
}

function publishWindowMessage(message: object) {
  try {
    const channel = new BroadcastChannel(SEARCH_CHANNEL);
    channel.postMessage(message);
    channel.close();
    return;
  } catch {
    // private mode or unsupported
  }
  if (window.opener && window.opener !== window) {
    try {
      window.opener.postMessage(message, window.location.origin);
    } catch {
      // closed opener
    }
  }
}

export interface StartDownloadPayload {
  url: string;
  format: 'video' | 'audio';
  quality: '1080p' | '320k';
  title?: string;
  author?: string;
  thumbnail?: string;
  duration?: string;
}

export async function fetchSearch(query: string, limit = 12): Promise<SearchHit[]> {
  const next = query.trim();
  if (!next) return [];
  const response = await fetch(`${getApiBase()}/api/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: next, limit }),
    ...apiInit(),
  });
  const payload = (await response.json()) as {
    items?: SearchHit[];
    detail?: string | { message?: string; detail?: string };
    message?: string;
  };
  if (!response.ok) {
    const detail = typeof payload.detail === 'string'
      ? payload.detail
      : payload.detail?.message || payload.detail?.detail;
    throw new Error(detail || payload.message || '검색하지 못했습니다.');
  }
  return payload.items || [];
}

export async function fetchAiSearch(
  prompt: string,
  history: Array<{ role: 'user' | 'assistant'; content: string }> = [],
): Promise<{ reply: string; keywords: string[]; items: SearchHit[] }> {
  const next = prompt.trim();
  if (!next) return { reply: '', keywords: [], items: [] };
  const response = await fetch(`${getApiBase()}/api/ai-search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: next, history }),
    ...apiInit(),
  });
  const payload = (await response.json()) as {
    reply?: string;
    keywords?: string[];
    items?: SearchHit[];
    detail?: string | { message?: string; detail?: string };
    message?: string;
  };
  if (!response.ok) {
    const detail = typeof payload.detail === 'string'
      ? payload.detail
      : payload.detail?.message || payload.detail?.detail;
    throw new Error(detail || payload.message || 'AI 검색하지 못했습니다.');
  }
  return {
    reply: payload.reply || '',
    keywords: payload.keywords || [],
    items: payload.items || [],
  };
}

export interface TranscriptLine {
  start: number;
  text: string;
}

export interface TranscriptResult {
  url: string;
  language: string;
  automatic: boolean;
  lines: TranscriptLine[];
  text: string;
  error?: string;
  code?: string;
}

export async function fetchTranscript(url: string): Promise<TranscriptResult> {
  const response = await fetch(`${getApiBase()}/api/transcript`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
    ...apiInit(),
  });
  const payload = (await response.json()) as TranscriptResult & {
    detail?: string | { message?: string; detail?: string };
    message?: string;
  };
  if (!response.ok) {
    const detail = typeof payload.detail === 'string'
      ? payload.detail
      : payload.detail?.message || payload.detail?.detail;
    throw new Error(detail || payload.message || '대본을 가져오지 못했습니다.');
  }
  return {
    url: payload.url || url,
    language: payload.language || '',
    automatic: Boolean(payload.automatic),
    lines: payload.lines || [],
    text: payload.text || '',
    error: payload.error || '',
    code: payload.code || '',
  };
}

export function notifyStartDownload(payload: StartDownloadPayload) {
  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  publishWindowMessage({ type: 'start-download', requestId, ...payload });
  return requestId;
}

export function notifyStartDownloadResult(requestId: string, ok: boolean, detail?: string) {
  publishWindowMessage({ type: 'start-download-result', requestId, ok, detail });
}

export function waitForDownloadAck(requestId: string, timeoutMs = 4000): Promise<{ ok: boolean; detail?: string }> {
  return new Promise((resolve) => {
    const done = (result: { ok: boolean; detail?: string }) => {
      window.clearTimeout(timer);
      window.removeEventListener('message', onMessage);
      channel?.close();
      resolve(result);
    };
    let channel: BroadcastChannel | null = null;
    try {
      channel = new BroadcastChannel(SEARCH_CHANNEL);
      channel.onmessage = (event) => {
        if (event.data?.type === 'start-download-result' && event.data.requestId === requestId) {
          done({ ok: Boolean(event.data.ok), detail: event.data.detail });
        }
      };
    } catch {
      channel = null;
    }
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === 'start-download-result' && event.data.requestId === requestId) {
        done({ ok: Boolean(event.data.ok), detail: event.data.detail });
      }
    };
    window.addEventListener('message', onMessage);
    const timer = window.setTimeout(() => {
      done({ ok: false, detail: '메인 창이 받기를 시작하지 못했습니다. 메인 화면을 연 뒤 다시 눌러 주세요.' });
    }, timeoutMs);
  });
}

export function notifyPickedUrl(url: string) {
  publishWindowMessage({ type: 'pick-url', url });
}
