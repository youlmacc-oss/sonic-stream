'use client';

import React from 'react';
import { Loader2 } from 'lucide-react';

export default function AiSearchSkeleton() {
  return (
    <div className="space-y-3" aria-live="polite">
      <p className="inline-flex items-center gap-2 text-lg text-cyan-200">
        <Loader2 className="h-5 w-5 animate-spin" />
        이야기를 읽고 영상을 고르는 중...
      </p>
      {[0, 1, 2].map((index) => (
        <div key={index} className="animate-pulse rounded-2xl border border-zinc-700 bg-zinc-900 p-3">
          <div className="flex gap-3">
            <div className="h-24 w-40 shrink-0 rounded-lg bg-zinc-800" />
            <div className="min-w-0 flex-1 space-y-2 py-1">
              <div className="h-5 w-4/5 rounded bg-zinc-800" />
              <div className="h-4 w-2/5 rounded bg-zinc-800" />
              <div className="h-3 w-3/5 rounded bg-zinc-800" />
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <div className="h-12 rounded-xl bg-zinc-800" />
            <div className="h-12 rounded-xl bg-zinc-800" />
          </div>
        </div>
      ))}
    </div>
  );
}
