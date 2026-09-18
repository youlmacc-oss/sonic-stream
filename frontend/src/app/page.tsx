'use client';

import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Clipboard, HelpCircle, Music, Smartphone, Video } from 'lucide-react';
import ApiStatus from '@/components/ApiStatus';
import DesktopSettings from '@/components/DesktopSettings';
import DownloadButton, { type StartDownloadOpts } from '@/components/DownloadButton';
import HistoryPanel from '@/components/HistoryPanel';
import InstallNeeded from '@/components/InstallNeeded';
import PreviewPane from '@/components/PreviewPane';
import WindowControls from '@/components/WindowControls';
import {
  getApiBase,
  type MediaFormat,
  type MediaInfo,
  type MediaQuality,
  type PresentationMode,
  type RuntimeInfo,
} from '@/lib/constants';
import type { DownloadHistoryItem } from '@/types/history';
import { SEARCH_CHANNEL, notifyStartDownloadResult, openHelpWindow } from '@/lib/searchWindow';
import { keepCurrentWindowAboveTaskbar } from '@/lib/workArea';
import {
  getAppShell,
  getServerAppShell,
  getServerShowDevMainButton,
  getShowDevMainButton,
  openLocalMainScreen,
  subscribeAppShell,
} from '@/lib/appShell';
import { applyLargeTypeClass, loadLargeType, persistLargeType, subscribeLargeType } from '@/utils/textSize';

const VIDEO_QUALITIES: MediaQuality[] = ['best', '720p', '1080p', '4k'];
const AUDIO_QUALITIES: MediaQuality[] = ['320k', 'flac'];

function isVideoQuality(value: string): value is MediaQuality {
  return VIDEO_QUALITIES.includes(value as MediaQuality);
}

function isAudioQuality(value: string): value is MediaQuality {
  return AUDIO_QUALITIES.includes(value as MediaQuality);
}

function AppHeader({
  largeType,
  local,
  showDevMain = false,
}: {
  largeType: boolean;
  local: boolean;
  showDevMain?: boolean;
}) {
  return (
    <header className="mb-2 flex shrink-0 items-center justify-between gap-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <h1 className="text-[length:var(--ss-title)] font-semibold tracking-tight text-white">
          Sonic<span className="text-cyan-300">Stream</span>
        </h1>
        {local && <ApiStatus />}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {showDevMain && (
          <button
            type="button"
            onClick={() => openLocalMainScreen()}
            className="rounded-lg border border-cyan-500 bg-cyan-950 px-2.5 text-[length:var(--ss-button)] font-semibold text-cyan-100 hover:bg-cyan-900"
          >
            메인 화면
          </button>
        )}
        <button
          type="button"
          onClick={() => openHelpWindow()}
          className="rounded-lg border border-zinc-600 bg-zinc-800 px-2.5 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-700"
        >
          <HelpCircle className="mr-1 inline h-4 w-4" />
          사용 방법
        </button>
        <button
          type="button"
          onClick={() => persistLargeType(!largeType)}
          className="rounded-lg border border-zinc-600 bg-zinc-800 px-2.5 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-700"
        >
          {largeType ? '기본 글씨' : '더 큰 글씨'}
        </button>
        {local && <WindowControls />}
      </div>
    </header>
  );
}

function BootScreen({ largeType }: { largeType: boolean }) {
  return (
    <main className="relative flex min-h-0 flex-1 flex-col overflow-hidden px-3 py-2">
      <AppHeader largeType={largeType} local={false} />
      <section className="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-700 bg-zinc-900">
        <p className="px-4 text-center text-[length:var(--ss-body)] leading-relaxed text-zinc-200">
          화면을 준비하는 중
        </p>
      </section>
    </main>
  );
}

function PublicInstallScreen({ largeType }: { largeType: boolean }) {
  const showDevMain = useSyncExternalStore(
    subscribeAppShell,
    getShowDevMainButton,
    getServerShowDevMainButton,
  );
  return (
    <main className="relative flex min-h-0 flex-1 flex-col overflow-hidden px-3 py-2">
      <AppHeader largeType={largeType} local={false} showDevMain={showDevMain} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <InstallNeeded />
      </div>
    </main>
  );
}

function LocalProgram({ largeType }: { largeType: boolean }) {
  const [url, setUrl] = useState('');
  const [mode, setMode] = useState<PresentationMode>('video');
  const [quality, setQuality] = useState<MediaQuality>('best');
  const [mediaInfo, setMediaInfo] = useState<MediaInfo | null>(null);
  const [inspectError, setInspectError] = useState<string | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [pasteButtonLabel, setPasteButtonLabel] = useState('붙여넣기');
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const startRef = useRef<((opts?: StartDownloadOpts) => void) | null>(null);
  const pasteHintTimer = useRef<number | null>(null);

  const format: MediaFormat = mode === 'audio' ? 'audio' : 'video';

  const isMobileViewport = () => {
    if (typeof window === 'undefined') return false;
    return (
      window.matchMedia('(pointer: coarse)').matches
      || navigator.maxTouchPoints > 1
      || /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent)
    );
  };

  const focusForNativePaste = () => {
    const input = inputRef.current;
    if (!input) return;
    input.focus();
    requestAnimationFrame(() => {
      try {
        const end = input.value.length;
        input.setSelectionRange(0, end);
        input.select();
      } catch {
        // some inputs reject selection while composing
      }
      input.click();
    });
  };

  const showPasteFallback = () => {
    focusForNativePaste();
    setPasteButtonLabel(isMobileViewport() ? '길게 눌러 붙여넣기' : 'Ctrl+V를 눌러주세요');
    if (pasteHintTimer.current) {
      window.clearTimeout(pasteHintTimer.current);
    }
    pasteHintTimer.current = window.setTimeout(() => {
      setPasteButtonLabel('붙여넣기');
    }, 2000);
  };

  const handlePaste = async () => {
    const canRead = typeof navigator !== 'undefined'
      && window.isSecureContext
      && typeof navigator.clipboard?.readText === 'function';
    const pendingRead = canRead ? navigator.clipboard.readText() : null;
    if (navigator.permissions?.query) {
      try {
        await navigator.permissions.query({ name: 'clipboard-read' as PermissionName });
      } catch {
        // Firefox / Safari may reject this PermissionName.
      }
    }
    if (pendingRead) {
      try {
        const text = (await pendingRead).trim();
        if (text) {
          setUrl(text);
          setPasteButtonLabel('붙여넣기');
          return;
        }
      } catch {
        // denied, dismissed, or not focused
      }
    }
    showPasteFallback();
  };

  useEffect(() => keepCurrentWindowAboveTaskbar(), []);

  useEffect(() => {
    const takeUrl = (value: unknown) => {
      if (typeof value === 'string' && /^https?:\/\//i.test(value)) {
        setUrl(value);
      }
    };
    let lastStartKey = '';
    let lastStartAt = 0;
    const startFromSearch = (data: { requestId?: string; url?: string; format?: string; quality?: string; title?: string; author?: string; thumbnail?: string; duration?: string }) => {
      if (typeof data.url !== 'string' || !/^https?:\/\//i.test(data.url)) {
        if (data.requestId) notifyStartDownloadResult(data.requestId, false, '주소가 올바르지 않습니다.');
        return;
      }
      const nextFormat: MediaFormat = data.format === 'audio' ? 'audio' : 'video';
      const nextQuality: MediaQuality = nextFormat === 'audio' ? '320k' : '1080p';
      const key = `${data.url}|${nextFormat}|${nextQuality}`;
      const now = Date.now();
      if (key === lastStartKey && now - lastStartAt < 2000) {
        if (data.requestId) notifyStartDownloadResult(data.requestId, false, '같은 받기가 이미 진행 중입니다.');
        return;
      }
      lastStartKey = key;
      lastStartAt = now;
      setUrl(data.url);
      setMode(nextFormat === 'audio' ? 'audio' : 'video');
      setQuality(nextQuality);
      if (!startRef.current) {
        if (data.requestId) notifyStartDownloadResult(data.requestId, false, '메인 화면이 아직 받을 준비가 되지 않았습니다.');
        return;
      }
      startRef.current({
        url: data.url,
        format: nextFormat,
        quality: nextQuality,
        title: data.title,
        author: data.author,
        thumbnail: data.thumbnail,
        duration: data.duration,
      });
      if (data.requestId) notifyStartDownloadResult(data.requestId, true);
    };
    let channel: BroadcastChannel | null = null;
    try {
      channel = new BroadcastChannel(SEARCH_CHANNEL);
      channel.onmessage = (event) => {
        if (event.data?.type === 'pick-url') takeUrl(event.data.url);
        if (event.data?.type === 'start-download') startFromSearch(event.data);
      };
    } catch {
      channel = null;
    }
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === 'pick-url') takeUrl(event.data.url);
      if (event.data?.type === 'start-download') startFromSearch(event.data);
    };
    window.addEventListener('message', onMessage);
    return () => {
      channel?.close();
      window.removeEventListener('message', onMessage);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${getApiBase()}/api/runtime`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: RuntimeInfo | null) => {
        if (controller.signal.aborted) return;
        setRuntime(payload || { location: 'local', location_label: '이 PC' });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setRuntime({ location: 'local', location_label: '이 PC' });
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const trimmed = url.trim();
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      if (!trimmed || !/^https?:\/\//i.test(trimmed)) {
        setMediaInfo(null);
        setInspectError(null);
        setInspecting(false);
        return;
      }

      setInspecting(true);
      try {
        const response = await fetch(`${getApiBase()}/api/inspect`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: trimmed }),
          signal: controller.signal,
        });
        let payload: MediaInfo & { message?: string; detail?: string };
        try {
          payload = (await response.json()) as MediaInfo & { message?: string; detail?: string };
        } catch {
          setMediaInfo(null);
          setInspectError('영상을 분석할 수 없습니다.');
          return;
        }
        if (!response.ok) {
          setMediaInfo(null);
          setInspectError(payload.detail || payload.message || '영상을 분석할 수 없습니다.');
          return;
        }
        setMediaInfo(payload);
        setInspectError(null);
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        setMediaInfo(null);
        setInspectError('프로그램에 연결할 수 없습니다. 바탕화면의 SonicStream을 다시 눌러 주세요.');
      } finally {
        if (!controller.signal.aborted) {
          setInspecting(false);
        }
      }
    }, 600);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [url]);

  useEffect(() => {
    return () => {
      if (pasteHintTimer.current) {
        window.clearTimeout(pasteHintTimer.current);
      }
    };
  }, []);

  const qualityFromHistory = (item: DownloadHistoryItem): MediaQuality => {
    if (item.type === 'audio') {
      return isAudioQuality(item.quality) ? item.quality : '320k';
    }
    return isVideoQuality(item.quality) ? item.quality : 'best';
  };

  const restoreHistoryItem = (item: DownloadHistoryItem) => {
    setMode(item.type === 'audio' ? 'audio' : 'video');
    setQuality(qualityFromHistory(item));
    setUrl(item.url);
  };

  const redownloadHistoryItem = (item: DownloadHistoryItem) => {
    restoreHistoryItem(item);
    startRef.current?.({
      url: item.url,
      format: item.type,
      quality: qualityFromHistory(item),
    });
  };

  return (
    <main className="relative flex min-h-0 flex-1 flex-col overflow-hidden px-3 py-2">
      <AppHeader largeType={largeType} local />

      <div className="grid min-h-0 min-w-0 flex-1 grid-cols-[minmax(0,1.3fr)_minmax(0,2.2fr)_minmax(0,1.5fr)] gap-2 overflow-hidden">
        <div className="min-h-0 overflow-hidden">
          <PreviewPane
            media={mediaInfo}
            inspecting={inspecting}
            inspectError={inspectError}
            sourceUrl={url.trim()}
            onPickUrl={setUrl}
          />
        </div>

        <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900 p-3">
          <h2 className="mb-2 shrink-0 font-semibold text-zinc-200">다운로드 작업</h2>
          <div className="mb-2 flex shrink-0 items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-950 px-2">
            <input
              ref={inputRef}
              type="text"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="동영상 링크를 붙여넣으세요"
              className="min-w-0 flex-1 bg-transparent px-2 text-[length:var(--ss-body)] text-zinc-100 placeholder-zinc-400 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => void handlePaste()}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-zinc-700 px-2.5 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400"
            >
              <Clipboard className="h-4 w-4" />
              {pasteButtonLabel}
            </button>
          </div>

          <div className="mb-2 grid shrink-0 grid-cols-3 gap-1 rounded-lg bg-zinc-950 p-1">
            <button
              type="button"
              onClick={() => { setMode('video'); if (!isVideoQuality(quality)) setQuality('best'); }}
              className={`flex min-h-[var(--ss-tap)] items-center justify-center gap-1.5 rounded-md px-1 text-[length:var(--ss-button)] font-medium ${
                mode === 'video' ? 'bg-zinc-800 text-cyan-200' : 'text-zinc-300 hover:text-white'
              }`}
            >
              <Video className="h-4 w-4" />
              영상
            </button>
            <button
              type="button"
              onClick={() => { setMode('shorts'); if (!isVideoQuality(quality)) setQuality('best'); }}
              className={`flex min-h-[var(--ss-tap)] items-center justify-center gap-1.5 rounded-md px-1 text-[length:var(--ss-button)] font-medium ${
                mode === 'shorts' ? 'bg-zinc-800 text-cyan-200' : 'text-zinc-300 hover:text-white'
              }`}
            >
              <Smartphone className="h-4 w-4" />
              세로·쇼츠
            </button>
            <button
              type="button"
              onClick={() => { setMode('audio'); if (!isAudioQuality(quality)) setQuality('320k'); }}
              className={`flex min-h-[var(--ss-tap)] items-center justify-center gap-1.5 rounded-md px-1 text-[length:var(--ss-button)] font-medium ${
                mode === 'audio' ? 'bg-zinc-800 text-cyan-200' : 'text-zinc-300 hover:text-white'
              }`}
            >
              <Music className="h-4 w-4" />
              오디오
            </button>
          </div>

          <div className="mb-1.5 flex shrink-0 items-center justify-between">
            <p className="text-[length:var(--ss-body)] text-zinc-200">품질: {mode === 'audio' ? quality : quality === 'best' ? '원본 최고' : quality}</p>
            <button
              type="button"
              onClick={() => setAdvanced((value) => !value)}
              className="ss-link text-[length:var(--ss-body)] text-zinc-200 underline-offset-2 hover:text-white hover:underline"
            >
              {advanced ? '간단히' : '고급 설정'}
            </button>
          </div>

          {(advanced || mode === 'audio') && (
            <div className="mb-2 flex shrink-0 flex-wrap gap-1">
              {(mode === 'audio' ? AUDIO_QUALITIES : VIDEO_QUALITIES).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setQuality(value)}
                  className={`rounded-lg px-2.5 text-[length:var(--ss-body)] ${
                    quality === value
                      ? 'border border-cyan-400 bg-cyan-950 text-cyan-100'
                      : 'border border-zinc-600 bg-zinc-800 text-zinc-200 hover:text-white'
                  }`}
                >
                  {value === 'best' ? '원본 최고' : value === '320k' ? 'MP3 320k' : value === 'flac' ? 'FLAC' : value.toUpperCase()}
                </button>
              ))}
            </div>
          )}

          <p className="mb-2 shrink-0 text-[length:var(--ss-body)] leading-snug text-zinc-300">
            화면비는 원본을 유지합니다. 세로 영상을 가로로 늘리거나 자르지 않습니다.
          </p>

          <div className="min-h-0 flex-1 overflow-y-auto pr-0.5">
            <DesktopSettings
              saveDir={runtime?.save_dir}
              autostart={runtime?.autostart}
              onRuntime={setRuntime}
            />

            <DownloadButton
              url={url}
              format={format}
              quality={quality}
              media={mediaInfo}
              location="local"
              localReady
              saveDir={runtime?.save_dir}
              startRef={startRef}
            />
          </div>
        </section>

        <div className="min-h-0 overflow-hidden">
          <HistoryPanel
            onRestore={restoreHistoryItem}
            onRedownload={redownloadHistoryItem}
            localReady
          />
        </div>
      </div>
    </main>
  );
}

export default function Home() {
  const largeType = useSyncExternalStore(subscribeLargeType, loadLargeType, () => false);
  const shell = useSyncExternalStore(subscribeAppShell, getAppShell, getServerAppShell);

  useEffect(() => {
    applyLargeTypeClass(largeType);
  }, [largeType]);

  if (shell === 'boot') {
    return <BootScreen largeType={largeType} />;
  }
  if (shell === 'public') {
    return <PublicInstallScreen largeType={largeType} />;
  }
  return <LocalProgram largeType={largeType} />;
}
