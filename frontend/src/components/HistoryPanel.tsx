'use client';

import React, { useEffect, useState } from 'react';
import { Clock, History, Trash2 } from 'lucide-react';
import type { DownloadHistoryItem } from '@/types/history';
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

export default function HistoryPanel({ onRestore }: HistoryPanelProps) {
  const [items, setItems] = useState<DownloadHistoryItem[]>([]);

  useEffect(() => {
    setItems(loadHistory());
    return subscribeHistory(setItems);
  }, []);

  return (
    <section className="relative z-10 w-full max-w-xl mt-8">
      <div className="flex items-center justify-between mb-3 px-1">
        <div className="flex items-center gap-2 text-sm text-zinc-200">
          <History className="w-4 h-4 text-cyan-400" />
          <h2 className="font-semibold">최근 다운로드</h2>
          <span className="text-xs text-zinc-500 font-mono">{items.length}</span>
        </div>
        {items.length > 0 && (
          <button
            type="button"
            onClick={() => clearHistory()}
            className="text-[11px] text-zinc-500 hover:text-rose-300 transition cursor-pointer"
          >
            전체 삭제
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <p className="text-xs text-zinc-500 px-1">
          이 브라우저에만 저장됩니다. 완료된 다운로드가 여기에 쌓입니다.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={item.id}>
              <div className="group flex items-center gap-3 rounded-2xl border border-zinc-800/70 border-t-white/15 bg-zinc-900/55 backdrop-blur-xl p-2.5">
                <button
                  type="button"
                  onClick={() => onRestore(item)}
                  className="flex flex-1 min-w-0 items-center gap-3 text-left cursor-pointer"
                >
                  <div className="relative w-16 aspect-video rounded-lg overflow-hidden bg-zinc-800 shrink-0 border border-zinc-700/50">
                    {item.thumbnail ? (
                      <img src={item.thumbnail} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full bg-zinc-800" />
                    )}
                    {item.duration && (
                      <span className="absolute bottom-0.5 right-0.5 bg-black/80 text-white text-[8px] font-mono px-1 rounded">
                        {item.duration}
                      </span>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-white truncate" title={item.title}>
                      {item.title}
                    </p>
                    <p className="text-[11px] text-zinc-400 truncate mt-0.5">{item.author}</p>
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-zinc-500 font-mono">
                      <span className="text-cyan-300/90">
                        {item.type === 'video' ? 'MP4' : 'AUDIO'} {item.quality.toUpperCase()}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatWhen(item.downloadedAt)}
                      </span>
                    </div>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => removeHistoryItem(item.id)}
                  aria-label="이력 삭제"
                  className="p-1.5 rounded-lg text-zinc-500 hover:text-rose-300 hover:bg-zinc-800/80 transition cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
