'use client';

import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, Check, Download, FolderOpen, Loader2 } from 'lucide-react';
import LocalFileActions from '@/components/LocalFileActions';
import {
  getApiBase,
  qualityLabel,
  resolveDownloadUrl,
  type MediaFormat,
  type MediaInfo,
  type MediaQuality,
  type RuntimeLocation,
} from '@/lib/constants';
import { fileNameFromPath, formatBytes } from '@/lib/fileActions';
import { useTabProgress } from '@/hooks/useTabProgress';
import { addHistoryItem, persistActiveJob, updateHistoryItem } from '@/utils/historyStorage';

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
  saveDir?: string | null;
  startRef?: React.MutableRefObject<((opts?: StartDownloadOpts) => void) | null>;
}

export interface StartDownloadOpts {
  url: string;
  format: MediaFormat;
  quality: MediaQuality;
  title?: string;
  author?: string;
  thumbnail?: string;
  duration?: string;
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

async function fetchJobWithRetry(jobId: string, tries = 4) {
  for (let index = 0; index < tries; index += 1) {
    try {
      const response = await fetch(`${getApiBase()}/api/jobs/${jobId}`);
      const payload = (await response.json()) as ProgressPayload & {
        error_message?: string;
        error_code?: string;
        status?: string;
      };
      if (response.status === 404) return { status: 'missing' } as typeof payload;
      if (response.ok) return payload;
    } catch {
      // retry
    }
    await new Promise((resolve) => window.setTimeout(resolve, 600 * (index + 1)));
  }
  return null;
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
  startRef,
}: DownloadButtonProps) {
  const [status, setStatus] = useState<ButtonStatus>('idle');
  const [progress, setProgress] = useState(0);
  const [speed, setSpeed] = useState('0 KB/s');
  const [eta, setEta] = useState<number | null>(null);
  const [detail, setDetail] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [errorCode, setErrorCode] = useState('');
  const [savedPath, setSavedPath] = useState('');
  const [fileBytes, setFileBytes] = useState<number | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const sourcesRef = useRef<Map<string, EventSource>>(new Map());
  const historyByJobRef = useRef<Map<string, string>>(new Map());
  const settledJobsRef = useRef<Set<string>>(new Set());
  const historyIdRef = useRef<string | null>(null);

  useTabProgress(status === 'started' || status === 'saved' ? 'completed' : status, progress);

  const closeStream = (job?: string) => {
    if (job) {
      sourcesRef.current.get(job)?.close();
      sourcesRef.current.delete(job);
      if (eventSourceRef.current && !sourcesRef.current.has(job)) eventSourceRef.current = null;
      return;
    }
    sourcesRef.current.forEach((source) => source.close());
    sourcesRef.current.clear();
    eventSourceRef.current = null;
  };

  useEffect(() => {
    return () => closeStream();
  }, []);

  const applyJobResult = (nextJobId: string, data: ProgressPayload & { error_message?: string; error_code?: string }) => {
    if (settledJobsRef.current.has(nextJobId)) return;
    settledJobsRef.current.add(nextJobId);
    closeStream(nextJobId);
    const historyId = historyByJobRef.current.get(nextJobId) || historyIdRef.current;
    const localSaved = data.delivery === 'local_file' && Boolean(data.saved_path) && data.verified === true;
    if (localSaved) {
      setJobId(nextJobId);
      setSavedPath(data.saved_path || '');
      setFileBytes(typeof data.file_bytes === 'number' ? data.file_bytes : null);
      setStatus('saved');
      setProgress(100);
      if (historyId) {
        updateHistoryItem(historyId, {
          status: 'saved',
          jobId: nextJobId,
          savedPath: data.saved_path || undefined,
          fileBytes: data.file_bytes || undefined,
          actualQuality: data.actual_quality || undefined,
          width: data.width || undefined,
          height: data.height || undefined,
        });
      }
      return;
    }
    if (data.status === 'done' && data.delivery !== 'local_file' && data.download_url) {
      triggerBrowserDownload(data.download_url);
      setStatus('started');
      setProgress(100);
      if (historyId) {
        updateHistoryItem(historyId, {
          status: 'started',
          jobId: nextJobId,
          actualQuality: data.actual_quality || undefined,
          width: data.width || undefined,
          height: data.height || undefined,
        });
      }
      return;
    }
    setStatus('error');
    setErrorCode(data.error_code || data.code || 'VERIFY_FAILED');
    setErrorMessage(data.error_message || data.message || '파일이 완료 조건을 통과하지 못했습니다.');
    if (historyId) updateHistoryItem(historyId, { status: 'failed', jobId: nextJobId });
  };

  const failJob = (nextJobId: string, message: string, code?: string) => {
    if (settledJobsRef.current.has(nextJobId)) return;
    settledJobsRef.current.add(nextJobId);
    closeStream(nextJobId);
    setStatus('error');
    setErrorCode(code || '');
    setErrorMessage(message || '다시 시도해 주세요');
    const historyId = historyByJobRef.current.get(nextJobId) || historyIdRef.current;
    if (historyId) updateHistoryItem(historyId, { status: 'failed', jobId: nextJobId });
  };

  const subscribe = (nextJobId: string) => {
    sourcesRef.current.get(nextJobId)?.close();
    const source = new EventSource(`${getApiBase()}/api/progress/${nextJobId}`);
    sourcesRef.current.set(nextJobId, source);
    eventSourceRef.current = source;

    source.addEventListener('queued', (event) => {
      const data = parseEventData(event.data);
      if (jobShows(nextJobId)) {
        setStatus('queued');
        setDetail(data?.detail || '대기열에서 순서를 기다리는 중...');
      }
    });

    source.addEventListener('retrying', (event) => {
      const data = parseEventData(event.data);
      if (jobShows(nextJobId)) {
        setStatus('retrying');
        setDetail(data?.detail || '다른 방식으로 다시 준비하는 중...');
      }
    });

    source.addEventListener('progress', (event) => {
      const data = parseEventData(event.data);
      if (!data || !jobShows(nextJobId)) return;
      setStatus('downloading');
      setProgress(Math.min(data.percent ?? 0, 100));
      if (data.speed) setSpeed(data.speed);
      setEta(typeof data.eta === 'number' ? data.eta : null);
      if (data.detail) setDetail(data.detail);
    });

    source.addEventListener('processing', (event) => {
      const data = parseEventData(event.data);
      if (!jobShows(nextJobId)) return;
      setStatus('processing');
      setProgress(95);
      setDetail(data?.detail || '파일을 정리하는 중...');
    });

    source.addEventListener('complete', (event) => {
      const data = parseEventData(event.data) || {};
      applyJobResult(nextJobId, { ...data, status: 'done' });
    });

    source.addEventListener('error', (event) => {
      if ('data' in event && typeof event.data === 'string' && event.data) {
        const data = parseEventData(event.data);
        failJob(nextJobId, `${data?.message || '다운로드에 실패했습니다.'} 문의번호 ${nextJobId}`, data?.code);
        return;
      }
      void fetchJobWithRetry(nextJobId).then((payload) => {
        if (!payload) {
          failJob(nextJobId, '서버 연결이 끊어졌습니다. 다시 시도해 주세요.');
          return;
        }
        if (payload.status === 'done') {
          applyJobResult(nextJobId, payload);
          return;
        }
        if (payload.status === 'error') {
          failJob(nextJobId, payload.error_message || payload.message || '다운로드에 실패했습니다.', payload.error_code);
          return;
        }
        if (payload.status === 'queued' || payload.status === 'retrying' || payload.status === 'downloading' || payload.status === 'processing') {
          return;
        }
        failJob(nextJobId, '작업을 찾을 수 없습니다. 엔진이 다시 시작된 것 같습니다.', 'JOB_NOT_FOUND');
      });
    });
  };

  const jobShows = (nextJobId: string) => jobId === nextJobId || !jobId;

  const startDownload = async (override?: StartDownloadOpts) => {
    const frozenUrl = (override?.url || url).trim();
    const frozenFormat = override?.format || format;
    const frozenQuality = override?.quality || quality;
    if (!frozenUrl) {
      setStatus('error');
      setErrorMessage('먼저 동영상 링크를 입력해 주세요.');
      return;
    }

    const item = addHistoryItem({
      url: frozenUrl,
      title: override?.title || media?.title || frozenUrl,
      author: override?.author || media?.author || 'Unknown',
      thumbnail: override?.thumbnail || media?.thumbnail || '',
      duration: override?.duration || media?.duration || '',
      type: frozenFormat,
      quality: frozenQuality,
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
    setFileBytes(null);
    setJobId(null);

    try {
      const response = await fetch(`${getApiBase()}/api/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: frozenUrl, type: frozenFormat, quality: frozenQuality }),
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
      historyByJobRef.current.set(payload.job_id, item.id);
      persistActiveJob(payload.job_id, item.id);
      updateHistoryItem(item.id, { jobId: payload.job_id });
      setStatus('queued');
      subscribe(payload.job_id);
    } catch {
      setStatus('error');
      setErrorMessage('서버에 연결할 수 없습니다.');
      updateHistoryItem(item.id, { status: 'failed' });
    }
  };

  useEffect(() => {
    if (!startRef) return;
    startRef.current = (opts) => {
      void startDownload(opts);
    };
    return () => {
      startRef.current = null;
    };
  });

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
    <div className="space-y-2">
      <button
        type="button"
        onClick={canClick ? () => void startDownload() : undefined}
        disabled={busy}
        className="flex min-h-[var(--ss-tap)] w-full items-center justify-center gap-2 rounded-lg bg-cyan-600 px-3 text-[length:var(--ss-button)] font-semibold text-white transition hover:bg-cyan-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300 disabled:cursor-not-allowed disabled:bg-zinc-600"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
        {format === 'video' ? `다운로드 (${qualityLabel(quality)})` : `추출 (${qualityLabel(quality)})`}
      </button>

      <div className="min-h-[3.25rem] rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-2 text-[length:var(--ss-body)] text-zinc-100">
        {status === 'idle' && (
          <p className="text-zinc-200">준비되면 진행 상태가 여기에 고정되어 표시됩니다.</p>
        )}
        {status === 'inspecting' && <p className="text-cyan-300">연결 중 / 영상 확인 중...</p>}
        {(status === 'queued' || status === 'retrying' || status === 'downloading' || status === 'processing') && (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <p className="truncate">{detail || '받는 중...'}</p>
              <span className="font-mono text-zinc-200">{Math.round(progress)}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
              <div className="h-full bg-cyan-500" style={{ width: `${status === 'processing' ? 95 : progress}%` }} />
            </div>
            <div className="flex items-center justify-between text-zinc-200">
              <span>{speed}{eta !== null ? ` · 남은 시간 ${eta}초` : ''}</span>
              <button type="button" onClick={() => void cancelJob()} className="ss-link text-zinc-100 underline-offset-2 hover:text-white hover:underline">
                취소
              </button>
            </div>
          </div>
        )}
        {status === 'saved' && (
          <div className="space-y-2 text-zinc-200">
            <p className="flex items-start gap-2 font-medium text-emerald-300">
              <Check className="mt-0.5 h-4 w-4 shrink-0" />
              다운로드가 완료되었습니다.
            </p>
            <dl className="space-y-1 text-[length:var(--ss-body)] text-zinc-200">
              <div>
                <dt className="text-zinc-500">파일</dt>
                <dd className="break-all text-zinc-200">{fileNameFromPath(savedPath) || '저장됨'}</dd>
              </div>
              {fileBytes != null && (
                <div>
                  <dt className="text-zinc-500">크기</dt>
                  <dd>{formatBytes(fileBytes)}</dd>
                </div>
              )}
              <div>
                <dt className="text-zinc-500">저장 위치</dt>
                <dd className="break-all font-mono">{savedPath}</dd>
              </div>
            </dl>
            {savedPath && <LocalFileActions path={savedPath} kind={format} />}
          </div>
        )}
        {status === 'started' && (
          <p className="flex items-start gap-2 text-cyan-200">
            <FolderOpen className="mt-0.5 h-4 w-4 shrink-0" />
            <span>저장은 시작됐습니다. 저장 폴더에서 파일이 끝났는지 확인해 주세요.</span>
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
                className="rounded-lg border border-rose-300 px-3 text-[length:var(--ss-button)] text-rose-100 hover:bg-rose-950"
              >
                다시 시도
              </button>
              {errorCode && <span className="font-mono text-[10px] text-zinc-500">{errorCode}</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
