'use client';

import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Download, Check, Loader2, AlertCircle } from 'lucide-react';
import {
  API_BASE,
  estimatedSize,
  resolveDownloadUrl,
  type MediaFormat,
  type MediaQuality,
} from '@/lib/constants';
import BorderBeam from '@/components/fx/BorderBeam';
import { useTabProgress } from '@/hooks/useTabProgress';
import { burstNeonConfetti } from '@/utils/celebrate';
import { playErrorBeep, playSuccessChime, unlockAudio } from '@/utils/sound';

type ButtonStatus =
  | 'idle'
  | 'inspecting'
  | 'queued'
  | 'retrying'
  | 'downloading'
  | 'processing'
  | 'completed'
  | 'error';

interface DownloadButtonProps {
  url: string;
  format: MediaFormat;
  quality: MediaQuality;
  onCompleted?: () => void;
}

interface ProgressPayload {
  status?: string;
  percent?: number;
  speed?: string;
  eta?: number | null;
  detail?: string;
  download_url?: string;
  code?: string;
  message?: string;
}

function parseEventData(raw: string): ProgressPayload | null {
  try {
    return JSON.parse(raw) as ProgressPayload;
  } catch {
    return null;
  }
}

function triggerBrowserDownload(downloadUrl: string) {
  const href = resolveDownloadUrl(downloadUrl);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export default function DownloadButton({ url, format, quality, onCompleted }: DownloadButtonProps) {
  const [status, setStatus] = useState<ButtonStatus>('idle');
  const [progress, setProgress] = useState(0);
  const [speed, setSpeed] = useState('0 KB/s');
  const [eta, setEta] = useState<number | null>(null);
  const [detail, setDetail] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const eventSourceRef = useRef<EventSource | null>(null);
  const idleTimerRef = useRef<number | null>(null);
  const settledRef = useRef(false);
  const buttonRef = useRef<HTMLDivElement>(null);
  const celebratedRef = useRef(false);
  const onCompletedRef = useRef(onCompleted);

  useEffect(() => {
    onCompletedRef.current = onCompleted;
  }, [onCompleted]);

  useTabProgress(status, progress);

  const closeStream = () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  };

  const resetIdleSoon = () => {
    if (idleTimerRef.current) {
      window.clearTimeout(idleTimerRef.current);
    }
    idleTimerRef.current = window.setTimeout(() => {
      setStatus('idle');
      setProgress(0);
      setSpeed('0 KB/s');
      setEta(null);
      setDetail('');
    }, 3000);
  };

  useEffect(() => {
    return () => {
      closeStream();
      if (idleTimerRef.current) {
        window.clearTimeout(idleTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (status === 'completed' && !celebratedRef.current) {
      celebratedRef.current = true;
      playSuccessChime();
      if ('vibrate' in navigator) {
        navigator.vibrate([40, 60, 40]);
      }
      burstNeonConfetti(buttonRef.current);
      onCompletedRef.current?.();
      return;
    }

    if (status === 'error') {
      playErrorBeep();
      celebratedRef.current = false;
      return;
    }

    if (status === 'idle' || status === 'inspecting') {
      celebratedRef.current = false;
    }
  }, [status]);

  const subscribe = (jobId: string) => {
    closeStream();
    settledRef.current = false;
    const source = new EventSource(`${API_BASE}/api/progress/${jobId}`);
    eventSourceRef.current = source;

    source.addEventListener('queued', (event) => {
      const data = parseEventData(event.data);
      setStatus('queued');
      setDetail(data?.detail || '대기열에서 순서를 기다리는 중...');
    });

    source.addEventListener('retrying', (event) => {
      const data = parseEventData(event.data);
      setStatus('retrying');
      setDetail(data?.detail || '연결 재시도 중...');
    });

    source.addEventListener('progress', (event) => {
      const data = parseEventData(event.data);
      if (!data) return;
      setStatus('downloading');
      setProgress(Math.min(data.percent ?? 0, 100));
      if (data.speed) setSpeed(data.speed);
      setEta(typeof data.eta === 'number' ? data.eta : null);
    });

    source.addEventListener('processing', (event) => {
      const data = parseEventData(event.data);
      setStatus('processing');
      setProgress(95);
      setDetail(
        data?.detail
        || (format === 'audio'
          ? '최고 음질 변환 및 앨범 아트 임베딩 중...'
          : 'FFmpeg 패키징 및 태그 주입 중...'),
      );
    });

    source.addEventListener('complete', (event) => {
      const data = parseEventData(event.data);
      settledRef.current = true;
      closeStream();
      if (data?.download_url) {
        triggerBrowserDownload(data.download_url);
      }
      setProgress(100);
      setStatus('completed');
      resetIdleSoon();
    });

    const fail = (message: string) => {
      if (settledRef.current) return;
      settledRef.current = true;
      closeStream();
      setStatus('error');
      setErrorMessage(message || '다시 시도해 주세요');
    };

    source.addEventListener('error', (event) => {
      if ('data' in event && typeof event.data === 'string' && event.data) {
        const data = parseEventData(event.data);
        const suffix = ` 문의번호 ${jobId}`;
        fail(`${data?.message || '다운로드 실패 (재시도)'}${suffix}`);
        return;
      }
      if (source.readyState === EventSource.CLOSED) {
        fail('서버 연결이 끊어졌습니다. 다시 시도해 주세요.');
      }
    });
  };

  const startDownload = async () => {
    if (!url.trim()) {
      alert('먼저 동영상 링크를 입력해 주세요!');
      return;
    }

    await unlockAudio();

    closeStream();
    if (idleTimerRef.current) {
      window.clearTimeout(idleTimerRef.current);
    }

    setStatus('inspecting');
    setProgress(0);
    setSpeed('0 KB/s');
    setEta(null);
    setDetail('');
    setErrorMessage('');

    try {
      const response = await fetch(`${API_BASE}/api/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim(), type: format, quality }),
      });
      const payload = (await response.json()) as { job_id?: string; message?: string };
      if (!response.ok || !payload.job_id) {
        setStatus('error');
        setErrorMessage(payload.message || '다시 시도해 주세요');
        resetIdleSoon();
        return;
      }
      setStatus('queued');
      subscribe(payload.job_id);
    } catch {
      setStatus('error');
      setErrorMessage('서버에 연결할 수 없습니다.');
      resetIdleSoon();
    }
  };

  const busy = status === 'inspecting' || status === 'queued' || status === 'retrying' || status === 'downloading' || status === 'processing';
  const gaugeVisible = status === 'downloading' || status === 'processing';
  const gaugeWidth = status === 'processing' ? 95 : Math.min(progress, 100);
  const canClick = status === 'idle' || status === 'error';

  const borderClass =
    status === 'error'
      ? 'border-rose-500/50'
      : status === 'completed'
        ? 'border-emerald-400/60 shadow-[0_0_24px_rgba(52,211,153,0.35)]'
        : 'border-zinc-700/80 hover:border-zinc-500';

  return (
    <div
      ref={buttonRef}
      className={`relative z-10 w-full max-w-xl mx-auto overflow-hidden rounded-2xl p-px shadow-2xl transition-all duration-500 ${
        status === 'downloading'
          ? 'drop-shadow-[0_0_20px_rgba(0,240,255,0.35)]'
          : ''
      }`}
    >
      {status !== 'error' && <BorderBeam durationClass="animate-border-beam" />}
      <button
        type="button"
        onClick={canClick ? () => void startDownload() : undefined}
        disabled={busy}
        className={`relative z-10 w-full h-14 rounded-2xl bg-zinc-900/90 border border-zinc-700/60 border-t border-t-white/15 overflow-hidden shadow-2xl transition-all duration-300 focus:outline-none backdrop-blur-sm ${borderClass}`}
      >
        {gaugeVisible && (
          <motion.div
            className={`absolute left-0 top-0 bottom-0 bg-gradient-to-r from-cyan-500 via-indigo-500 to-fuchsia-500 opacity-80 ${
              status === 'processing' ? 'animate-pulse' : ''
            }`}
            initial={false}
            animate={{ width: `${gaugeWidth}%` }}
            transition={{ ease: 'easeOut', duration: 0.2 }}
          >
            {status === 'downloading' && (
              <div className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
            )}
          </motion.div>
        )}

        <div className="relative z-10 flex items-center justify-between px-6 h-full font-medium text-sm text-zinc-100">
          <AnimatePresence mode="wait">
            {status === 'idle' && (
              <motion.div
                key="idle"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="flex items-center justify-between w-full"
              >
                <span className="flex items-center gap-2">
                  <Download className="w-4 h-4 text-cyan-400" />
                  {format === 'video'
                    ? `비디오 다운로드 (${quality.toUpperCase()})`
                    : `음원 추출 (${quality.toUpperCase()})`}
                </span>
                <span className="text-xs text-zinc-400 font-mono">
                  {estimatedSize(format, quality)}
                </span>
              </motion.div>
            )}

            {status === 'inspecting' && (
              <motion.div
                key="inspecting"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex items-center justify-center w-full gap-2 text-cyan-400 text-xs"
              >
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>다운로드를 준비하는 중...</span>
              </motion.div>
            )}

            {status === 'queued' && (
              <motion.div
                key="queued"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex items-center justify-center w-full gap-2 text-cyan-400 text-xs"
              >
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{detail || '대기열에서 순서를 기다리는 중...'}</span>
              </motion.div>
            )}

            {status === 'retrying' && (
              <motion.div
                key="retrying"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex items-center justify-center w-full gap-2 text-amber-300 text-xs"
              >
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="truncate">{detail || '연결 재시도 중...'}</span>
              </motion.div>
            )}

            {status === 'downloading' && (
              <motion.div
                key="downloading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex items-center justify-between w-full text-xs font-mono"
              >
                <span className="flex items-center gap-2 text-zinc-200">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                  다운로드 중...
                </span>
                <span className="text-zinc-400">
                  {speed}
                  {eta !== null ? ` • ETA: ${eta}s` : ''}
                </span>
                <span className="font-bold text-white text-sm">{Math.round(Math.min(progress, 100))}%</span>
              </motion.div>
            )}

            {status === 'processing' && (
              <motion.div
                key="processing"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex items-center justify-center w-full gap-2 text-xs font-mono text-zinc-100"
              >
                <span className="w-2 h-2 rounded-full bg-fuchsia-400 animate-ping" />
                <span className="truncate">
                  {detail
                    || (format === 'audio'
                      ? '최고 음질 변환 및 앨범 아트 임베딩 중...'
                      : 'FFmpeg 패키징 및 태그 주입 중...')}
                </span>
              </motion.div>
            )}

            {status === 'completed' && (
              <motion.div
                key="completed"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex items-center justify-center w-full gap-2 text-emerald-400 font-semibold"
              >
                <Check className="w-4 h-4" />
                <span>✓ 다운로드 완료!</span>
              </motion.div>
            )}

            {status === 'error' && (
              <motion.div
                key="error"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex items-center justify-center w-full gap-2 text-rose-400 text-xs font-medium"
              >
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span className="truncate">
                  {errorMessage || '다시 시도해 주세요'}
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </button>
    </div>
  );
}
