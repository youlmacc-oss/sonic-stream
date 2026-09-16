'use client';

import React from 'react';
import { Clock, ExternalLink, User } from 'lucide-react';
import type { MediaInfo } from '@/lib/constants';

interface PreviewPaneProps {
  media: MediaInfo | null;
  inspecting: boolean;
  inspectError: string | null;
  sourceUrl: string;
}

function durationLabel(media: MediaInfo): string {
  if (media.duration_known === false || !media.duration) return '정보 없음';
  if (media.duration === '00:00' && media.preview_only) return '확인 중';
  return media.duration;
}

export default function PreviewPane({ media, inspecting, inspectError, sourceUrl }: PreviewPaneProps) {
  const portrait = media?.orientation === 'portrait' || (media?.height && media?.width && media.height > media.width);
  const pageUrl = media?.webpage_url || sourceUrl;

  return (
    <section className="flex h-full min-h-0 flex-col rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">선택한 영상</h2>
      {!media && !inspecting && !inspectError && (
        <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-zinc-800 bg-zinc-950/50 px-4 py-10 text-center">
          <div className="mb-3 aspect-video w-full max-w-[220px] rounded-lg bg-zinc-800/80" />
          <p className="text-sm text-zinc-400">주소를 넣으면 미리보기가 여기에 나타납니다.</p>
        </div>
      )}
      {inspecting && !media && (
        <p className="text-sm text-cyan-300/90">영상 정보를 확인하는 중...</p>
      )}
      {inspectError && !inspecting && (
        <p className="text-sm leading-relaxed text-rose-300">{inspectError}</p>
      )}
      {media && (
        <div className="flex min-h-0 flex-1 flex-col gap-3">
          <div
            className={`overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 ${
              portrait ? 'mx-auto max-h-[28rem] w-auto max-w-full' : 'w-full'
            }`}
          >
            <img
              src={media.thumbnail}
              alt=""
              className={`block bg-zinc-900 object-contain ${
                portrait ? 'mx-auto max-h-[28rem] w-auto max-w-full' : 'h-auto w-full'
              }`}
              style={
                media.width && media.height
                  ? { aspectRatio: `${media.width} / ${media.height}` }
                  : portrait
                    ? { aspectRatio: '9 / 16' }
                    : { aspectRatio: '16 / 9' }
              }
            />
          </div>
          <h3 className="line-clamp-3 text-sm font-semibold leading-snug text-zinc-100" title={media.title}>
            {media.title}
          </h3>
          <div className="space-y-1.5 text-xs text-zinc-400">
            <p className="flex items-center gap-1.5">
              <User className="h-3.5 w-3.5 shrink-0 text-cyan-400" />
              <span className="truncate">{media.author}</span>
            </p>
            <p className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
              <span>재생 시간: {inspecting && !media.duration_known ? '확인 중' : durationLabel(media)}</span>
            </p>
            {(media.aspect_ratio || media.orientation) && (
              <p>
                {media.aspect_ratio || '해상도 미확인'}
                {media.orientation === 'portrait' ? ' · 세로' : media.orientation === 'landscape' ? ' · 가로' : ''}
              </p>
            )}
            {media.preview_only && (
              <p className="text-zinc-500">미리보기입니다. 제목 조회 성공은 다운로드 가능을 의미하지 않습니다.</p>
            )}
          </div>
          {pageUrl && (
            <a
              href={pageUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-auto inline-flex items-center gap-1.5 text-xs text-cyan-300 hover:text-cyan-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              원본 페이지 열기
            </a>
          )}
        </div>
      )}
    </section>
  );
}
