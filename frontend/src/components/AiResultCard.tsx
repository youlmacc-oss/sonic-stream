'use client';

import React from 'react';
import { Download, Music, Play } from 'lucide-react';
import type { SearchHit } from '@/lib/searchWindow';

interface AiResultCardProps {
  item: SearchHit;
  active?: boolean;
  onWatch: (item: SearchHit) => void;
  onVideo: (item: SearchHit) => void;
  onAudio: (item: SearchHit) => void;
}

export default function AiResultCard({ item, active = false, onWatch, onVideo, onAudio }: AiResultCardProps) {
  return (
    <li className={`rounded-xl border p-2.5 ${active ? 'border-cyan-400 bg-cyan-950/40' : 'border-zinc-600 bg-zinc-900'}`}>
      <button type="button" onClick={() => onWatch(item)} className="flex w-full gap-2.5 text-left">
        <div className="relative h-16 w-28 shrink-0 overflow-hidden rounded-md border border-zinc-700 bg-zinc-800">
          {item.thumbnail ? (
            <img src={item.thumbnail} alt="" className="h-full w-full object-cover" />
          ) : (
            <div className="h-full w-full bg-zinc-800" />
          )}
          {item.duration && (
            <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 text-[11px] text-white">{item.duration}</span>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 font-semibold text-white">{item.title}</p>
          {(item.author || item.views) && (
            <p className="mt-0.5 truncate text-[length:var(--ss-body)] text-cyan-200">
              {item.author}
              {item.author && item.views ? " · " : ""}
              {item.views}
            </p>
          )}
        </div>
      </button>
      <div className="mt-2 grid grid-cols-3 gap-1.5">
        <button
          type="button"
          onClick={() => onWatch(item)}
          className="inline-flex min-h-[var(--ss-tap)] items-center justify-center gap-1 rounded-lg border border-zinc-500 px-2 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-800"
        >
          <Play className="h-3.5 w-3.5" />
          바로보기
        </button>
        <button
          type="button"
          onClick={() => onVideo(item)}
          className="inline-flex min-h-[var(--ss-tap)] items-center justify-center gap-1 rounded-lg bg-cyan-600 px-2 text-[length:var(--ss-button)] font-semibold text-white hover:bg-cyan-500"
        >
          <Download className="h-3.5 w-3.5" />
          1080p
        </button>
        <button
          type="button"
          onClick={() => onAudio(item)}
          className="inline-flex min-h-[var(--ss-tap)] items-center justify-center gap-1 rounded-lg border border-cyan-400 bg-zinc-950 px-2 text-[length:var(--ss-button)] font-semibold text-cyan-100 hover:bg-cyan-950"
        >
          <Music className="h-3.5 w-3.5" />
          MP3
        </button>
      </div>
    </li>
  );
}
