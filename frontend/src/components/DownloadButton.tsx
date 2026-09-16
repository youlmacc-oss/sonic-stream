'use client';

import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, Check, Download, FolderOpen, Loader2 } from 'lucide-react';
import {
  getApiBase,
  qualityLabel,
  resolveDownloadUrl,
  type MediaFormat,
  type MediaInfo,
  type MediaQuality,
  type RuntimeLocation,
} from '@/lib/constants';
import { useTabProgress } from '@/hooks/useTabProgress';
import { addHistoryItem, updateHistoryItem } from '@/utils/historyStorage';

type ButtonStatus =
  | 'idle'
  | 'inspecting'
  | 'queued'
  | 'retrying'
  | 'downloading'
  | 'processing'
  | 'started'
  | 'saved'
  | 'error';

interface DownloadButtonProps {
  url: string;
  format: MediaFormat;
  quality: MediaQuality;
  media: MediaInfo | null;
  location: RuntimeLocation;
  localReady: boolean;
}

interface ProgressPayload {
  status?: string;
  percent?: number;
  speed?: string;
  eta?: number | null;
  detail?: string;
  download_url?: string;
  saved_path?: string | null;
  file_bytes?: number | null;
  verified?: boolean;
  delivery?: string;
  width?: number | null;
  height?: number | null;
  actual_quality?: string | null;
  code?: string;
  message?: string;
  job_id?: string;
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

export default function DownloadButton({
  url,
  format,
  quality,
  media,
  location,
  localReady,
}: DownloadButtonProps) {
  const [status, setStatus] = useState<ButtonStatus>('idle');
  const [progress, setProgress] = useState(0);
  const [speed, setSpeed] = useState('0 KB/s');
  const [eta, setEta] = useState<number | null>(null);
  const [detail, setDetail] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [errorCode, setErrorCode] = useState('');
  const [savedPath, setSavedPath] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const settledRef = useRef(false);
  const historyIdRef = useRef<string | null>(null);

  useTabProgress(status === 'started' || status === 'saved' ? 'completed' : status, progress);

  const closeStream = () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  };

  useEffect(() => {
    return () => closeStream();
  }, []);

  const subscribe = (nextJobId: string) => {
    closeStream();
    settledRef.current = false;
    const source = new EventSource(`${getApiBase()}/api/progress/${nextJobId}`);
    eventSourceRef.current = source;

    source.addEventListener('queued', (event) => {
      const data = parseEventData(event.data);
      setStatus('queued');
      setDetail(data?.detail || '대기열에서 순서를 기다리는 중...');
    });

    source.addEventListener('retrying', (event) => {
      const data = parseEventData(event.data);
      setStatus('retrying');
      setDetail(data?.detail || '다른 방식으로 다시 준비하는 중...');
    });

    source.addEventListener('progress', (event) => {
      const data = parseEventData(event.data);
      if (!data) return;
      setStatus('downloading');
      setProgress(Math.min(data.percent ?? 0, 100));
      if (data.speed) setSpeed(data.speed);
      setEta(typeof data.eta === 'number' ? data.eta : null);
      if (data.detail) setDetail(data.detail);
    });

    source.addEventListener('processing', (event) => {
      const data = parseEventData(event.data);
      setStatus('processing');
      setProgress(95);
      setDetail(data?.detail || '파일을 정리하는 중...');
    });

    source.addEventListener('complete', (event) => {
      const data = parseEventData(event.data);
      settledRef.current = true;
      closeStream();
      const localSaved = data?.delivery === 'local_file' && Boolean(data.saved_path);
      if (localSaved) {
        setSavedPath(data?.saved_path || '');
        const ok = Boolean(data?.verified) || Boolean(data?.file_bytes);
        setStatus(ok ? 'saved' : 'started');
        setProgress(100);
        if (historyIdRef.current) {
          updateHistoryItem(historyIdRef.current, {
            status: ok ? 'saved' : 'started',
            savedPath: data?.saved_path || undefined,
            fileBytes: data?.file_bytes || undefined,
            actualQuality: data?.actual_quality || undefined,
            width: data?.width || undefined,
            height: data?.height || undefined,
          });
        }
        return;
      }
      if (data?.download_url) {
        triggerBrowserDownload(data.download_url);
      }
      setProgress(100);
      setStatus('started');
      if (historyIdRef.current) {
        updateHistoryItem(historyIdRef.current, {
          status: 'started',
          actualQuality: data?.actual_quality || undefined,
          width: data?.width || undefined,
          height: data?.height || undefined,
        });
      }
    });

    const fail = (message: string, code?: string) => {
      if (settledRef.current) return;
      settledRef.current = true;
      closeStream();
      setStatus('error');
      setErrorCode(code || '');
      setErrorMessage(message || '다시 시도해 주세요');
      if (historyIdRef.current) {
        updateHistoryItem(historyIdRef.current, { status: 'failed' });
      }
    };

    source.addEventListener('error', (event) => {
      if ('data' in event && typeof event.data === 'string' && event.data) {
        const data = parseEventData(event.data);
        fail(`${data?.message || '다운로드에 실패했습니다.'} 문의번호 ${nextJobId}`, data?.code);
        return;
      }
      void fetch(`${getApiBase()}/api/jobs/${nextJobId}`)
        .then((response) => response.json())
        .then((payload: ProgressPayload & { error_message?: string; error_code?: string; status?: string }) => {
          if (payload.status === 'done') {
            settledRef.current = true;
            closeStream();
            if (payload.download_url) triggerBrowserDownload(payload.download_url);
            setStatus(payload.delivery === 'local_file' && payload.verified ? 'saved' : 'started');
            return;
          }
          if (payload.status === 'error') {
            fail(payload.error_message || payload.message || '다운로드에 실패했습니다.', payload.error_code);
            return;
          }
          fail('연결이 끊겼습니다. 상태를 다시 확인한 뒤 시도해 주세요.');
        })
        .catch(() => fail('서버 연결이 끊어졌습니다. 다시 시도해 주세요.'));
    });
  };

  const startDownload = async () => {
    const frozenUrl = url.trim();
    if (!frozenUrl) {
      setStatus('error');
      setErrorMessage('먼저 동영상 링크를 입력해 주세요.');
      return;
    }

    closeStream();
    const item = addHistoryItem({
      url: frozenUrl,
      title: media?.title || frozenUrl,
      author: media?.author || 'Unknown',
      thumbnail: media?.thumbnail || '',
      duration: media?.duration || '',
      type: format,
      quality,
      location,
      status: 'running',
    });
    historyIdRef.current = item.id;

    setStatus('inspecting');
    setProgress(0);
    setSpeed('0 KB/s');
    setEta(null);
    setDetail('연결 중...');
    setErrorMessage('');
    setErrorCode('');
    setSavedPath('');
    setJobId(null);

    try {
      const response = await fetch(`${getApiBase()}/api/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: frozenUrl, type: format, quality }),
      });
      const payload = (await response.json()) as { job_id?: string; message?: string; code?: string };
      if (!response.ok || !payload.job_id) {
        setStatus('error');
        setErrorCode(payload.code || '');
        setErrorMessage(payload.message || '다시 시도해 주세요');
        updateHistoryItem(item.id, { status: 'failed' });
        return;
      }
      setJobId(payload.job_id);
      updateHistoryItem(item.id, { jobId: payload.job_id });
      setStatus('queued');
      subscribe(payload.job_id);
    } catch {
      setStatus('error');
      setErrorMessage('서버에 연결할 수 없습니다.');
      updateHistoryItem(item.id, { status: 'failed' });
    }
  };

  const cancelJob = async () => {
    if (!jobId) return;
    await fetch(`${getApiBase()}/api/jobs/${jobId}/cancel`, { method: 'POST' });
    setStatus('error');
    setErrorMessage('다운로드를 취소했습니다.');
    if (historyIdRef.current) updateHistoryItem(historyIdRef.current, { status: 'cancelled' });
    closeStream();
  };

  const busy = status === 'inspecting' || status === 'queued' || status === 'retrying' || status === 'downloading' || status === 'processing';
  const canClick = status === 'idle' || status === 'error' || status === 'started' || status === 'saved';

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={canClick ? () => void startDownload() : undefined}
        disabled={busy}
        className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-cyan-700 text-sm font-semibold text-white transition hover:bg-cyan-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400 disabled:cursor-not-allowed disabled:bg-zinc-700"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
        {format === 'video' ? `다운로드 (${qualityLabel(quality)})` : `추출 (${qualityLabel(quality)})`}
      </button>

      <div className="min-h-[5.5rem] rounded-xl border border-zinc-800 bg-zinc-950/70 px-3 py-2.5 text-xs text-zinc-300">
        {status === 'idle' && (
          <p className="text-zinc-500">준비되면 진행 상태가 여기에 고정되어 표시됩니다.</p>
        )}
        {status === 'inspecting' && <p className="text-cyan-300">연결 중 / 영상 확인 중...</p>}
        {(status === 'queued' || status === 'retrying' || status === 'downloading' || status === 'processing') && (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <p className="truncate">{detail || '받는 중...'}</p>
              <span className="font-mono text-zinc-200">{Math.round(progress)}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-zinc-800">
              <div className="h-full bg-cyan-500" style={{ width: `${status === 'processing' ? 95 : progress}%` }} />
            </div>
            <div className="flex items-center justify-between text-zinc-500">
              <span>{speed}{eta !== null ? ` · 남은 시간 ${eta}초` : ''}</span>
              <button type="button" onClick={() => void cancelJob()} className="text-zinc-400 underline-offset-2 hover:text-zinc-200 hover:underline">
                취소
              </button>
            </div>
          </div>
        )}
        {status === 'saved' && (
          <p className="flex items-start gap-2 text-emerald-300">
            <Check className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              이 PC에 저장했습니다.
              {savedPath ? ` ${savedPath}` : ''}
            </span>
          </p>
        )}
        {status === 'started' && (
          <p className="flex items-start gap-2 text-cyan-200">
            <FolderOpen className="mt-0.5 h-4 w-4 shrink-0" />
            <span>브라우저 다운로드를 시작했습니다. 저장 폴더에서 파일이 끝났는지 확인해 주세요.</span>
          </p>
        )}
        {status === 'error' && (
          <div className="space-y-2 text-rose-300">
            <p className="flex items-start gap-2 leading-relaxed">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{errorMessage || '다시 시도해 주세요'}</span>
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void startDownload()}
                className="rounded-lg border border-rose-400/40 px-2.5 py-1 text-rose-100 hover:bg-rose-950/60"
              >
                다시 시도
              </button>
              {location === 'server' && !localReady && (
                <p className="text-zinc-400">
                  서버에서 막히면 프로젝트의 <span className="font-mono text-zinc-300">시작하기.bat</span>으로 이 PC에서 받아 보세요.
                </p>
              )}
              {errorCode && <span className="font-mono text-[10px] text-zinc-500">{errorCode}</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
