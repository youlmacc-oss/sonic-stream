'use client';

import React from 'react';
import { ExternalLink } from 'lucide-react';

interface MoreOnYoutubeProps {
  query: string;
}

export function youtubeResultsUrl(query: string): string {
  return `https://www.youtube.com/results?search_query=${encodeURIComponent(query.trim())}`;
}

export default function MoreOnYoutube({ query }: MoreOnYoutubeProps) {
  const next = query.trim();
  if (!next) return null;
  return (
    <div className="rounded-2xl border border-cyan-700/60 bg-zinc-950 p-4">
      <p className="text-lg leading-relaxed text-zinc-100">
        여기까지가 이 프로그램에서 찾은 결과입니다. 더 보고 싶으면 유튜브에서 이어서 찾으세요.
      </p>
      <a
        href={youtubeResultsUrl(next)}
        target="_blank"
        rel="noreferrer"
        className="mt-3 inline-flex min-h-[var(--ss-tap)] items-center gap-2 rounded-xl bg-cyan-600 px-4 text-[length:var(--ss-button)] font-semibold text-white hover:bg-cyan-500"
      >
        <ExternalLink className="h-5 w-5" />
        유튜브에서 더 찾기
      </a>
    </div>
  );
}
