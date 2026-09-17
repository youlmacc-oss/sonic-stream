'use client';

import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Volume2, VolumeX } from 'lucide-react';

const VOLUME_KEY = 'sonicstream.watchVolume.v1';

interface YtPlayer {
  cueVideoById: (id: string) => void;
  destroy: () => void;
  getVideoData?: () => { video_id?: string };
  isMuted: () => boolean;
  loadVideoById: (id: string) => void;
  mute: () => void;
  playVideo: () => void;
  seekTo: (seconds: number, allowSeekAhead?: boolean) => void;
  setVolume: (value: number) => void;
  unMute: () => void;
}

interface YtReadyEvent {
  target: YtPlayer;
}

declare global {
  interface Window {
    YT?: {
      Player: new (
        element: HTMLElement,
        options: {
          events?: { onReady?: (event: YtReadyEvent) => void };
          height?: string | number;
          host?: string;
          playerVars?: Record<string, number | string>;
          videoId?: string;
          width?: string | number;
        },
      ) => YtPlayer;
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

function readStoredVolume(): number | null {
  try {
    const raw = window.localStorage.getItem(VOLUME_KEY);
    if (raw == null || raw === '') return null;
    const value = Number(raw);
    if (Number.isFinite(value)) return Math.max(0, Math.min(100, Math.round(value)));
  } catch {
    // private mode
  }
  return null;
}

function readVolume() {
  return readStoredVolume() ?? 80;
}

function writeVolume(value: number) {
  try {
    window.localStorage.setItem(VOLUME_KEY, String(value));
  } catch {
    // private mode
  }
}

function loadYoutubeApi() {
  if (window.YT?.Player) return Promise.resolve();
  return new Promise<void>((resolve) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      resolve();
    };
    if (document.getElementById('ss-yt-iframe-api')) return;
    const script = document.createElement('script');
    script.id = 'ss-yt-iframe-api';
    script.src = 'https://www.youtube.com/iframe_api';
    document.head.appendChild(script);
  });
}

function applySound(player: YtPlayer, volume: number, muted: boolean) {
  player.setVolume(volume);
  if (muted || volume === 0) player.mute();
  else player.unMute();
}

export interface WatchHandle {
  seekTo: (seconds: number) => void;
}

interface WatchPlayerProps {
  autoplay: boolean;
  title: string;
  videoId: string;
}

const WatchPlayer = forwardRef<WatchHandle, WatchPlayerProps>(function WatchPlayer(
  { videoId, title, autoplay },
  ref,
) {
  const host = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YtPlayer | null>(null);
  const latest = useRef({ videoId, autoplay, volume: 80, muted: false });
  const [ready, setReady] = useState(false);
  const [volume, setVolume] = useState(80);
  const [muted, setMuted] = useState(false);
  const lastAudible = useRef(80);
  const [playerError, setPlayerError] = useState('');

  latest.current = { videoId, autoplay, volume, muted };

  useImperativeHandle(ref, () => ({
    seekTo: (seconds: number) => {
      const player = playerRef.current;
      if (!player) return;
      player.seekTo(Math.max(0, seconds), true);
      player.playVideo();
    },
  }));

  useEffect(() => {
    const start = readVolume();
    setVolume(start);
    setMuted(start === 0);
    if (start > 0) lastAudible.current = start;
    latest.current.volume = start;
    latest.current.muted = start === 0;
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      if (!cancelled && !playerRef.current) setPlayerError('미리보기를 준비하지 못했습니다. 원본 페이지에서 확인해 주세요.');
    }, 12000);

    void loadYoutubeApi().then(() => {
      if (cancelled || !host.current || !window.YT?.Player) return;
      const player = new window.YT.Player(host.current, {
        width: '100%',
        height: '100%',
        videoId: latest.current.videoId,
        host: 'https://www.youtube-nocookie.com',
        playerVars: {
          rel: 0,
          modestbranding: 1,
          playsinline: 1,
          fs: 1,
          iv_load_policy: 3,
          autoplay: latest.current.autoplay ? 1 : 0,
          origin: window.location.origin,
        },
        events: {
          onReady: (event) => {
            playerRef.current = event.target;
            applySound(event.target, latest.current.volume, latest.current.muted);
            if (latest.current.autoplay) event.target.playVideo();
            setPlayerError('');
            setReady(true);
          },
        },
      });
      playerRef.current = player;
    });

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
      setReady(false);
      try {
        playerRef.current?.destroy();
      } catch {
        // player already gone
      }
      playerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const player = playerRef.current;
    if (!ready || !player) return;
    applySound(player, volume, muted);
  }, [ready, volume, muted]);

  useEffect(() => {
    const player = playerRef.current;
    if (!ready || !player) return;
    const currentId = player.getVideoData?.().video_id;
    if (currentId === videoId) {
      if (autoplay) player.playVideo();
      return;
    }
    if (autoplay) player.loadVideoById(videoId);
    else player.cueVideoById(videoId);
  }, [videoId, autoplay, ready]);

  const changeVolume = (next: number) => {
    const value = Math.max(0, Math.min(100, next));
    setVolume(value);
    setMuted(value === 0);
    if (value > 0) lastAudible.current = value;
    writeVolume(value);
    if (playerRef.current) applySound(playerRef.current, value, value === 0);
  };

  const toggleMute = () => {
    if (muted || volume === 0) {
      const restored = volume > 0 ? volume : lastAudible.current || 80;
      setVolume(restored);
      setMuted(false);
      writeVolume(restored);
      if (playerRef.current) applySound(playerRef.current, restored, false);
      return;
    }
    setMuted(true);
    if (playerRef.current) applySound(playerRef.current, volume, true);
  };

  return (
    <div>
      <div className="relative w-full bg-black" style={{ aspectRatio: '16 / 9' }}>
        <div ref={host} title={title} className="absolute inset-0 h-full w-full" />
        {playerError && (
          <p className="absolute inset-x-2 bottom-2 rounded bg-black/70 px-2 py-1 text-[length:var(--ss-body)] text-zinc-100">
            {playerError}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          onClick={toggleMute}
          className="inline-flex min-h-[var(--ss-tap)] min-w-[var(--ss-tap)] items-center justify-center rounded-lg text-zinc-100 hover:bg-zinc-800"
          aria-label={muted || volume === 0 ? '소리 켜기' : '소리 끄기'}
        >
          {muted || volume === 0 ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
        </button>
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={muted ? 0 : volume}
          onChange={(event) => changeVolume(Number(event.target.value))}
          aria-label="소리 크기"
          className="min-h-[var(--ss-tap)] min-w-0 flex-1 accent-cyan-400"
        />
        <span className="w-12 text-right font-mono text-[length:var(--ss-body)] text-zinc-200">
          {muted ? 0 : volume}
        </span>
      </div>
    </div>
  );
});

export default WatchPlayer;
