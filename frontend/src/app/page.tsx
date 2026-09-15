'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Sparkles, Clipboard, Video, Music } from 'lucide-react';
import DownloadButton from '@/components/DownloadButton';
import HistoryPanel from '@/components/HistoryPanel';
import MediaCard from '@/components/MediaCard';
import AuroraBackground from '@/components/fx/AuroraBackground';
import TiltCard from '@/components/TiltCard';
import { API_BASE, type MediaFormat, type MediaInfo, type MediaQuality } from '@/lib/constants';
import type { DownloadHistoryItem } from '@/types/history';
import { addHistoryItem } from '@/utils/historyStorage';

const RESTORABLE_QUALITIES: readonly MediaQuality[] = ['1080p', '4k', '320k', 'flac'];

function isRestorableQuality(value: string): value is MediaQuality {
  return RESTORABLE_QUALITIES.includes(value as MediaQuality);
}

export default function Home() {
  const [url, setUrl] = useState('');
  const [format, setFormat] = useState<MediaFormat>('video');
  const [quality, setQuality] = useState<MediaQuality>('1080p');
  const [mediaInfo, setMediaInfo] = useState<MediaInfo | null>(null);
  const [inspectError, setInspectError] = useState<string | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [pasteButtonLabel, setPasteButtonLabel] = useState('붙여넣기');
  const inputRef = useRef<HTMLInputElement>(null);
  const pasteHintTimer = useRef<number | null>(null);

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

    // Start the read immediately so the click still counts as a user gesture
    // and Chromium can show the native [클립보드 접근 허용] prompt.
    const pendingRead = canRead ? navigator.clipboard.readText() : null;

    if (navigator.permissions?.query) {
      try {
        await navigator.permissions.query({
          name: 'clipboard-read' as PermissionName,
        });
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
    const trimmed = url.trim();
    if (!trimmed) {
      setMediaInfo(null);
      setInspectError(null);
      setInspecting(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      if (!/^https?:\/\//i.test(trimmed)) {
        setMediaInfo(null);
        setInspectError(null);
        setInspecting(false);
        return;
      }

      setInspecting(true);
      try {
        const response = await fetch(`${API_BASE}/api/inspect`, {
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
          setInspectError(
            response.ok
              ? '영상을 분석할 수 없습니다.'
              : '영상을 분석할 수 없습니다. 잠시 후 다시 시도해 주세요.',
          );
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
        setInspectError('서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인해 주세요.');
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

  const handleDownloadCompleted = () => {
    addHistoryItem({
      url: url.trim(),
      title: mediaInfo?.title || url.trim(),
      author: mediaInfo?.author || 'Unknown',
      thumbnail: mediaInfo?.thumbnail || '',
      duration: mediaInfo?.duration || '',
      type: format,
      quality,
    });
  };

  const restoreHistoryItem = (item: DownloadHistoryItem) => {
    const nextQuality = isRestorableQuality(item.quality)
      ? item.quality
      : item.type === 'audio' ? '320k' : '1080p';
    setFormat(item.type);
    setQuality(nextQuality);
    setUrl(item.url);
  };

  return (
    <main className="relative isolate flex-1 flex flex-col items-center justify-center px-4 py-16">
      <AuroraBackground />

      <div className="relative z-10 text-center mb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-950/60 border border-cyan-500/30 text-cyan-400 text-xs font-semibold mb-4">
          <Sparkles className="w-3.5 h-3.5" />
          Ultra-Clean Downloader
        </div>
        <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-white mb-3">
          Sonic<span className="text-cyan-400">Stream</span>
        </h1>
        <p className="text-zinc-400 text-sm md:text-base max-w-md mx-auto">
          복잡한 선택지 없이, 오직 최고 품질의 1080p/4K 영상과 320kbps 음원만 다운로드합니다.
        </p>
      </div>

      <TiltCard className="mb-3" innerClassName="p-2">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="동영상 링크를 붙여넣으세요 (예: YouTube URL)"
            className="flex-1 bg-transparent px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => void handlePaste()}
            className="flex items-center justify-center gap-1.5 min-w-[7.75rem] px-3 py-2 rounded-xl bg-zinc-800/90 hover:bg-zinc-700 text-zinc-300 text-xs font-medium transition-all duration-200 cursor-pointer"
          >
            <Clipboard className="w-3.5 h-3.5 shrink-0" />
            <span className="whitespace-nowrap">{pasteButtonLabel}</span>
          </button>
        </div>
      </TiltCard>

      {inspecting && (
        <p className="relative z-10 w-full max-w-xl text-xs text-cyan-400/80 mb-4 px-1">영상 미리보기를 불러오는 중...</p>
      )}
      {inspectError && !inspecting && (
        <p className="relative z-10 w-full max-w-xl text-xs text-rose-400 mb-4 px-1">{inspectError}</p>
      )}

      {mediaInfo && <MediaCard media={mediaInfo} />}

      <TiltCard className="mb-6" innerClassName="p-5 bg-zinc-900/50">
        <div className="grid grid-cols-2 gap-2 p-1 bg-zinc-950 rounded-xl mb-4 border border-zinc-800/50">
          <button
            type="button"
            onClick={() => { setFormat('video'); setQuality('1080p'); }}
            className={`flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
              format === 'video'
                ? 'bg-zinc-800 text-cyan-400 shadow'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Video className="w-4 h-4" />
            비디오 (MP4)
          </button>
          <button
            type="button"
            onClick={() => { setFormat('audio'); setQuality('320k'); }}
            className={`flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
              format === 'audio'
                ? 'bg-zinc-800 text-cyan-400 shadow'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Music className="w-4 h-4" />
            오디오 (MP3)
          </button>
        </div>

        <div className="flex items-center justify-between text-xs">
          <span className="text-zinc-400">품질 규격:</span>
          <div className="flex gap-2">
            {format === 'video' ? (
              <>
                <button
                  type="button"
                  onClick={() => setQuality('1080p')}
                  className={`px-3 py-1.5 rounded-lg font-medium transition cursor-pointer ${
                    quality === '1080p'
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                      : 'bg-zinc-800/60 text-zinc-400 hover:bg-zinc-800'
                  }`}
                >
                  1080p FHD (표준)
                </button>
                <button
                  type="button"
                  onClick={() => setQuality('4k')}
                  className={`px-3 py-1.5 rounded-lg font-medium transition cursor-pointer ${
                    quality === '4k'
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                      : 'bg-zinc-800/60 text-zinc-400 hover:bg-zinc-800'
                  }`}
                >
                  4K UHD (최고화질)
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => setQuality('320k')}
                  className={`px-3 py-1.5 rounded-lg font-medium transition cursor-pointer ${
                    quality === '320k'
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                      : 'bg-zinc-800/60 text-zinc-400 hover:bg-zinc-800'
                  }`}
                >
                  320kbps CBR (최고음질)
                </button>
                <button
                  type="button"
                  onClick={() => setQuality('flac')}
                  className={`px-3 py-1.5 rounded-lg font-medium transition cursor-pointer ${
                    quality === 'flac'
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                      : 'bg-zinc-800/60 text-zinc-400 hover:bg-zinc-800'
                  }`}
                >
                  FLAC (무손실)
                </button>
              </>
            )}
          </div>
        </div>
      </TiltCard>

      <DownloadButton
        url={url}
        format={format}
        quality={quality}
        onCompleted={handleDownloadCompleted}
      />

      <HistoryPanel onRestore={restoreHistoryItem} />
    </main>
  );
}
