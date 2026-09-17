'use client';

import React, { useState } from 'react';
import { Clock, ExternalLink, Search, User } from 'lucide-react';
import type { MediaInfo } from '@/lib/constants';
import { fetchConnectionStatus, hasSavedOpenaiKey } from '@/lib/apiStatus';
import { fetchSearch, openAiChatWindow, type SearchHit } from '@/lib/searchWindow';

interface PreviewPaneProps {
  media: MediaInfo | null;
  inspecting: boolean;
  inspectError: string | null;
  sourceUrl: string;
  onPickUrl?: (url: string) => void;
}

function durationLabel(media: MediaInfo): string {
  if (media.duration_known === false || !media.duration) return '정보 없음';
  if (media.duration === '00:00' && media.preview_only) return '확인 중';
  return media.duration;
}

export default function PreviewPane({ media, inspecting, inspectError, sourceUrl, onPickUrl }: PreviewPaneProps) {
  const portrait = media?.orientation === 'portrait' || (media?.height && media?.width && media.height > media.width);
  const pageUrl = media?.webpage_url || sourceUrl;
  const [search, setSearch] = useState('');
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [busy, setBusy] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [aiGuide, setAiGuide] = useState(false);

  const runRegularSearch = async () => {
    const next = search.trim();
    if (!next || busy) return;
    setBusy(true);
    setSearchError('');
    try {
      const items = await fetchSearch(next, 12);
      setHits(items);
      if (!items.length) setSearchError('찾은 영상이 없습니다. 다른 말로 다시 찾아 보세요.');
    } catch (error) {
      setHits([]);
      setSearchError(error instanceof Error ? error.message : '검색하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  const runAiSearch = async () => {
    const status = await fetchConnectionStatus();
    if (!hasSavedOpenaiKey(status)) {
      setAiGuide(true);
      return;
    }
    openAiChatWindow(search.trim());
  };

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900 p-3">
      <h2 className="mb-2 shrink-0 font-semibold text-zinc-100">선택한 영상</h2>
      <form
        className="mb-2 flex shrink-0 items-center gap-1.5"
        onSubmit={(event) => {
          event.preventDefault();
          void runRegularSearch();
        }}
      >
        <div className="flex min-h-[var(--ss-tap)] min-w-0 flex-1 items-center rounded-lg border border-zinc-600 bg-zinc-950">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="찾고 싶은 영상을 말해 보세요"
            className="min-h-[var(--ss-tap)] min-w-0 flex-1 bg-transparent py-1 pl-2.5 pr-1 text-[length:var(--ss-body)] text-zinc-100 placeholder-zinc-400 focus:outline-none"
          />
          <button
            type="submit"
            disabled={busy}
            title="일반 검색"
            aria-label="일반 검색"
            className="mr-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-zinc-200 hover:bg-zinc-800 hover:text-white disabled:text-zinc-500"
          >
            <Search className="h-4 w-4" />
          </button>
        </div>
        <button
          type="button"
          onClick={() => void runAiSearch()}
          className="inline-flex min-h-[var(--ss-tap)] shrink-0 items-center justify-center rounded-lg bg-cyan-700 px-3 text-[length:var(--ss-button)] font-semibold text-white hover:bg-cyan-600"
        >
          AI 검색
        </button>
      </form>
      {aiGuide && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="ai-guide-title"
            className="w-full max-w-lg rounded-2xl border border-cyan-700 bg-zinc-900 p-5 shadow-2xl"
          >
            <h3 id="ai-guide-title" className="text-[length:var(--ss-title)] font-semibold text-white">
              AI 검색을 쓸 수 없습니다
            </h3>
            <p className="mt-3 text-[length:var(--ss-body)] leading-relaxed text-zinc-100">
              AI 검색은 OpenAI API 키가 연결되어 있어야 합니다. 가운데 AI 연결에 키를 넣고 저장하고 연결을 누르세요.
            </p>
            <p className="mt-2 text-[length:var(--ss-body)] leading-relaxed text-zinc-200">
              지금은 검색창 오른쪽 돋보기로 일반 검색을 할 수 있습니다.
            </p>
            <button
              type="button"
              onClick={() => setAiGuide(false)}
              className="mt-4 inline-flex min-h-[var(--ss-tap)] w-full items-center justify-center rounded-xl bg-cyan-600 px-4 text-[length:var(--ss-button)] font-semibold text-white hover:bg-cyan-500"
            >
              확인
            </button>
          </div>
        </div>
      )}
      {busy && (
        <p className="mb-2 text-[length:var(--ss-body)] text-cyan-200">영상을 찾는 중...</p>
      )}
      {searchError && !busy && (
        <p className="mb-2 text-[length:var(--ss-body)] leading-snug text-rose-300">{searchError}</p>
      )}
      {hits.length > 0 && (
        <ul className="mb-2 max-h-[28%] min-h-0 shrink-0 space-y-1.5 overflow-y-auto pr-0.5">
          {hits.map((item) => (
            <li key={item.url}>
              <button
                type="button"
                onClick={() => onPickUrl?.(item.url)}
                className={`flex w-full gap-2 rounded-lg border bg-zinc-950 p-1.5 text-left hover:border-cyan-500 ${
                  sourceUrl === item.url ? 'border-cyan-500' : 'border-zinc-700'
                }`}
              >
                <div className="h-12 w-20 shrink-0 overflow-hidden rounded bg-zinc-800">
                  {item.thumbnail ? (
                    <img src={item.thumbnail} alt="" className="h-full w-full object-cover" />
                  ) : null}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="line-clamp-2 text-[length:var(--ss-body)] font-semibold text-white">{item.title}</p>
                  <p className="truncate text-[length:var(--ss-body)] text-cyan-200">
                    {item.author}
                    {item.author && item.views ? ' · ' : ''}
                    {item.views}
                  </p>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
      {!media && !inspecting && !inspectError && !busy && !searchError && hits.length === 0 && (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center rounded-lg border border-dashed border-zinc-800 bg-zinc-950/50 px-3 py-6 text-center">
          <div className="mb-2 aspect-video w-full max-w-[160px] rounded-md bg-zinc-800/80" />
          <p className="text-[length:var(--ss-body)] text-zinc-200">주소를 넣거나 돋보기로 찾아 보세요.</p>
        </div>
      )}
      {inspecting && !media && (
        <p className="text-[length:var(--ss-body)] text-cyan-200">영상 정보를 확인하는 중...</p>
      )}
      {inspectError && !inspecting && !media && (
        <p className="text-[length:var(--ss-body)] leading-snug text-rose-300">{inspectError}</p>
      )}
      {media && (
        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
          <div
            className={`overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 ${
              portrait ? 'mx-auto max-h-[min(14rem,34vh)] w-auto max-w-full' : 'w-full'
            }`}
          >
            <img
              src={media.thumbnail}
              alt=""
              className={`block bg-zinc-900 object-contain ${
                portrait ? 'mx-auto max-h-[min(14rem,34vh)] w-auto max-w-full' : 'h-auto max-h-[min(12rem,30vh)] w-full'
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
          <h3 className="line-clamp-2 font-semibold leading-snug text-white" title={media.title}>
            {media.title}
          </h3>
          <div className="space-y-1 text-[length:var(--ss-body)] text-zinc-200">
            <p className="flex items-center gap-1.5">
              <User className="h-4 w-4 shrink-0 text-cyan-300" />
              <span className="truncate">{media.author}</span>
            </p>
            <p className="flex items-center gap-1.5">
              <Clock className="h-4 w-4 shrink-0 text-zinc-300" />
              <span>재생 시간: {inspecting && !media.duration_known ? '확인 중' : durationLabel(media)}</span>
            </p>
            {(media.aspect_ratio || media.orientation) && (
              <p>
                {media.aspect_ratio || '해상도 미확인'}
                {media.orientation === 'portrait' ? ' · 세로' : media.orientation === 'landscape' ? ' · 가로' : ''}
              </p>
            )}
            {media.preview_only && (
              <p className="text-zinc-300">미리보기입니다. 제목 조회 성공은 다운로드 가능을 의미하지 않습니다.</p>
            )}
          </div>
          {pageUrl && (
            <a
              href={pageUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-auto inline-flex items-center gap-1.5 text-[length:var(--ss-body)] text-cyan-200 hover:text-cyan-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400"
            >
              <ExternalLink className="h-4 w-4" />
              원본 페이지 열기
            </a>
          )}
        </div>
      )}
    </section>
  );
}
