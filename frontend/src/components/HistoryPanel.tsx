'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Clock, History, Search, Trash2 } from 'lucide-react';
import { qualityLabel } from '@/lib/constants';
import type { DownloadHistoryItem, HistoryStatus } from '@/types/history';
import {
  clearHistory,
  loadHistory,
  removeHistoryItem,
  subscribeHistory,
} from '@/utils/historyStorage';

interface HistoryPanelProps {
  onRestore: (item: DownloadHistoryItem) => void;
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

export default function HistoryPanel({ onRestore }: HistoryPanelProps) {
  const [items, setItems] = useState<DownloadHistoryItem[]>(() => loadHistory());
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | HistoryStatus>('all');

  useEffect(() => subscribeHistory(setItems), []);

  const visible = useMemo(() => {
    return items.filter((item) => {
      if (filter !== 'all' && (item.status || 'started') !== filter) return false;
      if (!query.trim()) return true;
      const hay = `${item.title} ${item.author} ${item.url}`.toLowerCase();
      return hay.includes(query.trim().toLowerCase());
    });
  }, [items, query, filter]);

  return (
    <section className="flex h-full min-h-0 flex-col rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm text-zinc-200">
          <History className="h-4 w-4 text-cyan-400" />
          <h2 className="font-semibold">다운로드 이력</h2>
          <span className="font-mono text-xs text-zinc-500">{items.length}</span>
        </div>
        {items.length > 0 && (
          <button
            type="button"
            onClick={() => clearHistory()}
            className="text-[11px] text-zinc-500 hover:text-rose-300"
          >
            이력만 비우기
          </button>
        )}
      </div>

      <label className="mb-2 flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1.5">
        <Search className="h-3.5 w-3.5 text-zinc-500" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="제목 또는 주소 검색"
          className="w-full bg-transparent text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none"
        />
      </label>

      <div className="mb-3 flex flex-wrap gap-1">
        {(['all', 'running', 'started', 'saved', 'failed'] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={`rounded-full px-2 py-0.5 text-[10px] ${
              filter === value ? 'bg-cyan-900/70 text-cyan-200' : 'bg-zinc-800 text-zinc-400'
            }`}
          >
            {value === 'all' ? '전체' : statusLabel(value)}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="text-xs leading-relaxed text-zinc-500">
          이 브라우저에만 이력이 남습니다. 이력 삭제는 저장된 파일을 지우지 않습니다.
        </p>
      ) : (
        <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {visible.map((item) => (
            <li key={item.id}>
              <div className="flex items-start gap-2 rounded-xl border border-zinc-800 bg-zinc-950/60 p-2">
                <button
                  type="button"
                  onClick={() => onRestore(item)}
                  className="flex min-w-0 flex-1 items-start gap-2 text-left"
                >
                  <div className="relative h-12 w-10 shrink-0 overflow-hidden rounded-md bg-zinc-800">
                    {item.thumbnail ? (
                      <img src={item.thumbnail} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <div className="h-full w-full bg-zinc-800" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 text-xs font-semibold text-white" title={item.title}>
                      {item.title}
                    </p>
                    <p className="mt-0.5 font-mono text-[10px] text-cyan-300/90">
                      {qualityLabel(item.actualQuality || item.quality)}
                      {item.location === 'local' ? ' · 내 PC' : item.location === 'server' ? ' · 서버' : ''}
                    </p>
                    <p className="mt-0.5 flex items-center gap-1 text-[10px] text-zinc-500">
                      <Clock className="h-3 w-3" />
                      {statusLabel(item.status)} · {formatWhen(item.downloadedAt)}
                    </p>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => removeHistoryItem(item.id)}
                  aria-label="이력 삭제"
                  className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-rose-300"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
