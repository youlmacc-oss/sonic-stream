'use client';

import React, { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { Clock, History, RotateCw, Search, Trash2 } from 'lucide-react';
import LocalFileActions from '@/components/LocalFileActions';
import { qualityLabel } from '@/lib/constants';
import type { DownloadHistoryItem, HistoryStatus } from '@/types/history';
import {
  clearHistory,
  getServerHistorySnapshot,
  hydrateHistoryFromPc,
  loadHistory,
  removeHistoryItem,
  subscribeHistory,
} from '@/utils/historyStorage';

interface HistoryPanelProps {
  onRestore: (item: DownloadHistoryItem) => void;
  onRedownload: (item: DownloadHistoryItem) => void;
  localReady: boolean;
}

function formatWhen(timestamp: number): string {
  const delta = Date.now() - timestamp;
  const minutes = Math.floor(delta / 60_000);
  if (minutes < 1) return '방금';
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}일 전`;
  return new Date(timestamp).toLocaleDateString('ko-KR');
}

function statusLabel(status?: HistoryStatus): string {
  if (status === 'running') return '진행 중';
  if (status === 'started') return '다운로드 시작됨';
  if (status === 'saved') return '저장됨';
  if (status === 'failed') return '실패';
  if (status === 'cancelled') return '취소';
  return '완료';
}

export default function HistoryPanel({ onRestore, onRedownload, localReady }: HistoryPanelProps) {
  const items = useSyncExternalStore(subscribeHistory, loadHistory, getServerHistorySnapshot);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | HistoryStatus>('all');

  useEffect(() => {
    if (!localReady) return undefined;
    void hydrateHistoryFromPc();
    return undefined;
  }, [localReady]);

  const visible = useMemo(() => {
    return items.filter((item) => {
      if (filter !== 'all' && (item.status || 'started') !== filter) return false;
      if (!query.trim()) return true;
      const hay = `${item.title} ${item.author} ${item.url}`.toLowerCase();
      return hay.includes(query.trim().toLowerCase());
    });
  }, [items, query, filter]);

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900 p-3">
      <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-[length:var(--ss-body)] text-zinc-100">
          <History className="h-4 w-4 text-cyan-300" />
          <h2 className="font-semibold">다운로드 이력</h2>
          <span className="font-mono text-zinc-300">{items.length}</span>
        </div>
        {items.length > 0 && (
          <button
            type="button"
            onClick={() => clearHistory()}
            className="ss-link text-[length:var(--ss-body)] text-zinc-200 hover:text-rose-300"
          >
            이력만 비우기
          </button>
        )}
      </div>

      <label className="mb-2 flex shrink-0 items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-950 px-2.5">
        <Search className="h-4 w-4 text-zinc-300" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="제목 또는 주소 검색"
          className="w-full bg-transparent text-[length:var(--ss-body)] text-zinc-100 placeholder-zinc-400 focus:outline-none"
        />
      </label>

      <div className="mb-2 flex shrink-0 flex-wrap gap-1">
        {(['all', 'running', 'started', 'saved', 'failed'] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={`rounded-full px-2.5 text-[length:var(--ss-body)] ${
              filter === value ? 'bg-cyan-800 text-cyan-100' : 'bg-zinc-800 text-zinc-200'
            }`}
          >
            {value === 'all' ? '전체' : statusLabel(value)}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="text-[length:var(--ss-body)] leading-snug text-zinc-200">
          이 브라우저에만 이력이 남습니다. 이력 삭제는 저장된 파일을 지우지 않습니다.
        </p>
      ) : (
        <ul className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          {visible.map((item) => (
            <li key={item.id}>
              <div className="rounded-lg border border-zinc-600 bg-zinc-950 p-2">
                <div className="flex items-start gap-2">
                  <div className="relative h-12 w-9 shrink-0 overflow-hidden rounded-md bg-zinc-800">
                    {item.thumbnail ? (
                      <img src={item.thumbnail} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <div className="h-full w-full bg-zinc-800" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 font-semibold text-white" title={item.title}>
                      {item.title}
                    </p>
                    <p className="mt-0.5 font-mono text-[length:var(--ss-body)] text-cyan-200">
                      {qualityLabel(item.actualQuality || item.quality)}
                      {item.location === 'server' ? ' · 이전 서버 기록' : ' · 이 PC'}
                    </p>
                    <p className="mt-0.5 flex items-center gap-1.5 text-[length:var(--ss-body)] text-zinc-200">
                      <Clock className="h-3.5 w-3.5" />
                      {statusLabel(item.status)} · {formatWhen(item.downloadedAt)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeHistoryItem(item.id)}
                    aria-label="이력 삭제"
                    className="ss-link rounded-lg p-1.5 text-zinc-300 hover:bg-zinc-800 hover:text-rose-300"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {localReady && item.location === 'local' && item.savedPath && (
                    <LocalFileActions path={item.savedPath} kind={item.type} compact />
                  )}
                  <button
                    type="button"
                    onClick={() => onRedownload(item)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-500 px-2.5 text-[length:var(--ss-body)] text-zinc-100 hover:bg-zinc-800"
                  >
                    <RotateCw className="h-3.5 w-3.5" />
                    다시 다운로드
                  </button>
                  <button
                    type="button"
                    onClick={() => onRestore(item)}
                    className="ss-link rounded-lg px-2 text-[length:var(--ss-body)] text-zinc-200 hover:text-white"
                  >
                    주소만 불러오기
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
