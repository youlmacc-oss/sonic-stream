'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Clipboard, Monitor, Music, Server, Smartphone, Video } from 'lucide-react';
import DownloadButton from '@/components/DownloadButton';
import HistoryPanel from '@/components/HistoryPanel';
import PreviewPane from '@/components/PreviewPane';
import {
  getApiBase,
  type MediaFormat,
  type MediaInfo,
  type MediaQuality,
  type PresentationMode,
  type RuntimeInfo,
  type RuntimeLocation,
} from '@/lib/constants';
import type { DownloadHistoryItem } from '@/types/history';

const VIDEO_QUALITIES: MediaQuality[] = ['best', '720p', '1080p', '4k'];
const AUDIO_QUALITIES: MediaQuality[] = ['320k', 'flac'];

function isVideoQuality(value: string): value is MediaQuality {
  return VIDEO_QUALITIES.includes(value as MediaQuality);
}

function isAudioQuality(value: string): value is MediaQuality {
  return AUDIO_QUALITIES.includes(value as MediaQuality);
}

export default function Home() {
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
  const pasteHintTimer = useRef<number | null>(null);

  const format: MediaFormat = mode === 'audio' ? 'audio' : 'video';
  const location: RuntimeLocation = runtime?.location === 'local' ? 'local' : 'server';

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

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${getApiBase()}/api/runtime`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: RuntimeInfo | null) => {
        if (payload) setRuntime(payload);
      })
      .catch(() => {
        setRuntime({ location: 'server', location_label: '서버' });
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
        setInspectError('서버에 연결할 수 없습니다. 내 PC 모드라면 시작하기.bat을 실행해 주세요.');
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

  const restoreHistoryItem = (item: DownloadHistoryItem) => {
    setMode(item.type === 'audio' ? 'audio' : 'video');
    if (item.type === 'audio') {
      setQuality(isAudioQuality(item.quality) ? item.quality : '320k');
    } else {
      setQuality(isVideoQuality(item.quality) ? item.quality : 'best');
    }
    setUrl(item.url);
  };

  return (
    <main className="flex min-h-0 flex-1 flex-col px-3 py-3 sm:px-4">
      <header className="mb-3 flex items-center justify-between gap-3">
        <h1 className="text-lg font-semibold tracking-tight text-white">
          Sonic<span className="text-cyan-400">Stream</span>
        </h1>
        <p className="inline-flex items-center gap-1.5 rounded-full border border-zinc-800 bg-zinc-900 px-2.5 py-1 text-[11px] text-zinc-300">
          {location === 'local' ? <Monitor className="h-3.5 w-3.5 text-cyan-300" /> : <Server className="h-3.5 w-3.5 text-zinc-400" />}
          {location === 'local' ? '내 PC' : '서버'}
        </p>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,28%)_minmax(0,42%)_minmax(0,30%)] lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <div className="order-2 min-h-[18rem] lg:order-1 lg:min-h-0">
          <PreviewPane
            media={mediaInfo}
            inspecting={inspecting}
            inspectError={inspectError}
            sourceUrl={url.trim()}
          />
        </div>

        <section className="order-1 flex min-h-0 flex-col rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4 lg:order-2">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">다운로드 작업</h2>
          <div className="mb-3 flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-950 px-2 py-1.5">
            <input
              ref={inputRef}
              type="text"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="동영상 링크를 붙여넣으세요"
              className="min-w-0 flex-1 bg-transparent px-2 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => void handlePaste()}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-zinc-800 px-2.5 py-2 text-xs text-zinc-200 hover:bg-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400"
            >
              <Clipboard className="h-3.5 w-3.5" />
              {pasteButtonLabel}
            </button>
          </div>

          <div className="mb-3 grid grid-cols-3 gap-1 rounded-xl bg-zinc-950 p-1">
            <button
              type="button"
              onClick={() => { setMode('video'); if (!isVideoQuality(quality)) setQuality('best'); }}
              className={`flex items-center justify-center gap-1 rounded-lg py-2 text-[11px] font-medium ${
                mode === 'video' ? 'bg-zinc-800 text-cyan-300' : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <Video className="h-3.5 w-3.5" />
              영상
            </button>
            <button
              type="button"
              onClick={() => { setMode('shorts'); if (!isVideoQuality(quality)) setQuality('best'); }}
              className={`flex items-center justify-center gap-1 rounded-lg py-2 text-[11px] font-medium ${
                mode === 'shorts' ? 'bg-zinc-800 text-cyan-300' : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <Smartphone className="h-3.5 w-3.5" />
              세로·쇼츠
            </button>
            <button
              type="button"
              onClick={() => { setMode('audio'); if (!isAudioQuality(quality)) setQuality('320k'); }}
              className={`flex items-center justify-center gap-1 rounded-lg py-2 text-[11px] font-medium ${
                mode === 'audio' ? 'bg-zinc-800 text-cyan-300' : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <Music className="h-3.5 w-3.5" />
              오디오
            </button>
          </div>

          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs text-zinc-400">품질: {mode === 'audio' ? quality : quality === 'best' ? '원본 최고' : quality}</p>
            <button
              type="button"
              onClick={() => setAdvanced((value) => !value)}
              className="text-[11px] text-zinc-500 underline-offset-2 hover:text-zinc-300 hover:underline"
            >
              {advanced ? '간단히' : '고급 설정'}
            </button>
          </div>

          {(advanced || mode === 'audio') && (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {(mode === 'audio' ? AUDIO_QUALITIES : VIDEO_QUALITIES).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setQuality(value)}
                  className={`rounded-lg px-2.5 py-1 text-[11px] ${
                    quality === value
                      ? 'border border-cyan-500/40 bg-cyan-950/50 text-cyan-200'
                      : 'border border-zinc-800 bg-zinc-800/70 text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {value === 'best' ? '원본 최고' : value === '320k' ? 'MP3 320k' : value === 'flac' ? 'FLAC' : value.toUpperCase()}
                </button>
              ))}
            </div>
          )}

          <p className="mb-3 text-[11px] leading-relaxed text-zinc-500">
            화면비는 원본을 유지합니다. 세로 영상을 가로로 늘리거나 자르지 않습니다.
            {location === 'local' && runtime?.save_dir ? ` 저장 위치: ${runtime.save_dir}` : ''}
          </p>

          <DownloadButton
            url={url}
            format={format}
            quality={quality}
            media={mediaInfo}
            location={location}
            localReady={location === 'local'}
          />
        </section>

        <div className="order-3 min-h-[16rem] lg:col-span-2 xl:col-span-1 xl:min-h-0">
          <HistoryPanel onRestore={restoreHistoryItem} />
        </div>
      </div>
    </main>
  );
}
