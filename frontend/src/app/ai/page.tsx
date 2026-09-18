'use client';

import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Copy, Home, RotateCw, Send } from 'lucide-react';
import AiResultCard from '@/components/AiResultCard';
import AiSearchSkeleton from '@/components/AiSearchSkeleton';
import ApiStatus from '@/components/ApiStatus';
import TranscriptPanel from '@/components/TranscriptPanel';
import WatchPlayer, { type WatchHandle } from '@/components/WatchPlayer';
import WindowControls from '@/components/WindowControls';
import MoreOnYoutube from '@/components/MoreOnYoutube';
import { copyText } from '@/lib/fileActions';
import { fetchAiSearch, notifyPickedUrl, notifyStartDownload, openMainWindow, waitForDownloadAck, youtubeVideoId, type SearchHit } from '@/lib/searchWindow';
import { keepCurrentWindowAboveTaskbar } from '@/lib/workArea';
import { getAppShell, getServerAppShell, subscribeAppShell } from '@/lib/appShell';
import { applyLargeTypeClass, loadLargeType } from '@/utils/textSize';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  items?: SearchHit[];
  keywords?: string[];
}

function newId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function AiChatPage() {
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState('');
  const [notice, setNotice] = useState('');
  const [results, setResults] = useState<SearchHit[]>([]);
  const [watching, setWatching] = useState<SearchHit | null>(null);
  const [autoplay, setAutoplay] = useState(false);
  const [copiedId, setCopiedId] = useState('');
  const shell = useSyncExternalStore(subscribeAppShell, getAppShell, getServerAppShell);
  const desktop = shell === 'local';
  const scroller = useRef<HTMLDivElement>(null);
  const resultsPane = useRef<HTMLDivElement>(null);
  const playerBox = useRef<HTMLDivElement>(null);
  const watchApi = useRef<WatchHandle>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    applyLargeTypeClass(loadLargeType());
    document.title = 'SonicStream AI';
    const initial = new URLSearchParams(window.location.search).get('q')?.trim() || '';
    if (initial && !startedRef.current) {
      startedRef.current = true;
      void sendPrompt(initial);
    }
  }, []);

  useEffect(() => {
    if (!desktop) return undefined;
    return keepCurrentWindowAboveTaskbar();
  }, [desktop]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' });
  }, [messages, busy]);

  useEffect(() => {
    if (!autoplay || !watching) return;
    resultsPane.current?.scrollTo({ top: 0, behavior: 'smooth' });
    playerBox.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [watching, autoplay]);

  const sendPrompt = async (value: string) => {
    const next = value.trim();
    if (!next || busy) return;
    const history = messages.map((item) => ({ role: item.role, content: item.text }));
    setDraft('');
    setMessages((current) => [...current, { id: newId(), role: 'user', text: next }]);
    setBusy(true);
    try {
      const result = await fetchAiSearch(next, history);
      const items = result.items || [];
      setMessages((current) => [
        ...current,
        {
          id: newId(),
          role: 'assistant',
          text: result.reply || '이 이야기에 맞는 영상을 찾아 봤습니다.',
          items,
          keywords: result.keywords,
        },
      ]);
      setResults(items);
      setWatching(items[0] || null);
      setAutoplay(false);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: newId(),
          role: 'assistant',
          text: error instanceof Error ? error.message : '지금은 답을 내지 못했습니다. 잠시 후 다시 말해 주세요.',
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const copyMessage = async (message: ChatMessage) => {
    const ok = await copyText(message.text);
    if (!ok) return;
    setCopiedId(message.id);
    window.setTimeout(() => {
      setCopiedId((current) => (current === message.id ? '' : current));
    }, 1600);
  };

  const watchVideo = (item: SearchHit) => {
    setWatching(item);
    setAutoplay(true);
    notifyPickedUrl(item.url);
  };

  const startDownload = (item: SearchHit, format: 'video' | 'audio') => {
    const requestId = notifyStartDownload({
      url: item.url,
      format,
      quality: format === 'audio' ? '320k' : '1080p',
      title: item.title,
      author: item.author,
      thumbnail: item.thumbnail,
      duration: item.duration,
    });
    notifyPickedUrl(item.url);
    setStarted('');
    void waitForDownloadAck(requestId).then((result) => {
      setStarted(result.ok ? `${item.url}:${format}` : '');
      if (!result.ok) setNotice(result.detail || '메인 창에서 받기를 시작하지 못했습니다.');
    });
  };

  const lastAssistant = [...messages].reverse().find((item) => item.role === 'assistant' && (item.items || []).length);
  const lastUser = [...messages].reverse().find((item) => item.role === 'user');
  const moreQuery = lastAssistant?.keywords?.join(' ') || lastUser?.text || '';
  const watchId = watching ? youtubeVideoId(watching.url) : null;

  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-hidden bg-zinc-950">
      <header className="shrink-0 border-b border-zinc-800 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-sm uppercase tracking-wide text-cyan-300">SonicStream</p>
            <h1 className="text-[length:var(--ss-title)] font-semibold text-white">AI 검색 대화</h1>
          </div>
          <div className="flex items-center gap-2">
            <ApiStatus />
            <button
              type="button"
              onClick={() => void openMainWindow()}
              className="inline-flex min-h-[var(--ss-tap)] items-center gap-1.5 rounded-lg border border-cyan-500 bg-cyan-950 px-2.5 text-[length:var(--ss-button)] font-semibold text-cyan-100 hover:bg-cyan-900"
            >
              <Home className="h-4 w-4" />
              메인 화면
            </button>
            {desktop && <WindowControls />}
          </div>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,42%)_minmax(0,58%)] overflow-hidden">
        <section className="flex min-h-0 flex-col border-r border-zinc-800">
          <div ref={scroller} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {messages.length === 0 && !busy && (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/70 px-3 py-4 text-[length:var(--ss-body)] leading-snug text-zinc-200">
                예: 비 오는 날 듣기 좋은 전유진 노래, 아이와 같이 볼 수 있는 짧은 동요
              </div>
            )}
            {messages.map((message) => (
              <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`flex max-w-[94%] flex-col ${message.role === 'user' ? 'items-end' : 'items-start'}`}>
                  <div
                    className={`rounded-2xl px-3 py-2.5 text-[length:var(--ss-body)] leading-snug ${
                      message.role === 'user'
                        ? 'rounded-br-md bg-cyan-700 text-white'
                        : 'rounded-bl-md border border-zinc-700 bg-zinc-900 text-zinc-100'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{message.text}</p>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <button
                      type="button"
                      onClick={() => void copyMessage(message)}
                      className="inline-flex min-h-[var(--ss-tap)] items-center gap-1 rounded-lg px-2 text-[length:var(--ss-button)] text-zinc-300 hover:bg-zinc-800 hover:text-white"
                    >
                      <Copy className="h-3.5 w-3.5" />
                      {copiedId === message.id ? '복사됨' : '복사'}
                    </button>
                    <button
                      type="button"
                      disabled={busy || !message.text.trim()}
                      onClick={() => void sendPrompt(message.text)}
                      className="inline-flex min-h-[var(--ss-tap)] items-center gap-1 rounded-lg px-2 text-[length:var(--ss-button)] text-zinc-300 hover:bg-zinc-800 hover:text-white disabled:text-zinc-600"
                    >
                      <RotateCw className="h-3.5 w-3.5" />
                      다시 보내기
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {busy && (
              <p className="text-[length:var(--ss-body)] text-cyan-200">이야기를 읽고 영상을 고르는 중...</p>
            )}
            {started && <p className="text-[length:var(--ss-body)] text-cyan-200">원래 창에서 받기를 시작했습니다.</p>}
            {notice && !started && <p className="text-[length:var(--ss-body)] text-rose-300">{notice}</p>}
          </div>

          <form
            className="shrink-0 border-t border-zinc-800 bg-zinc-950 px-3 py-3"
            onSubmit={(event) => {
              event.preventDefault();
              void sendPrompt(draft);
            }}
          >
            <div className="flex items-end gap-2">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void sendPrompt(draft);
                  }
                }}
                rows={3}
                placeholder="찾고 싶은 영상을 말해 주세요"
                className="h-[calc(var(--ss-body)*1.4*3+1rem)] min-h-[calc(var(--ss-body)*1.4*3+1rem)] min-w-0 flex-1 resize-none rounded-xl border border-zinc-600 bg-zinc-900 px-3 py-2 text-[length:var(--ss-body)] leading-snug text-zinc-100 placeholder-zinc-400"
              />
              <button
                type="submit"
                disabled={busy || !draft.trim()}
                className="inline-flex h-[calc(var(--ss-body)*1.4*3+1rem)] items-center gap-1.5 rounded-xl bg-cyan-600 px-3 text-[length:var(--ss-button)] font-semibold text-white hover:bg-cyan-500 disabled:bg-zinc-700"
              >
                <Send className="h-4 w-4" />
                보내기
              </button>
            </div>
          </form>
        </section>

        <section className="flex min-h-0 flex-col">
          <div ref={resultsPane} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
            <div className="flex items-center justify-between gap-2">
              <h2 className="font-semibold text-white">검색 결과</h2>
              <span className="font-mono text-[length:var(--ss-body)] text-zinc-300">{results.length}건</span>
            </div>
            {watching && watchId && (
              <div ref={playerBox} className="rounded-xl border border-zinc-700 bg-black">
                <WatchPlayer ref={watchApi} videoId={watchId} title={watching.title} autoplay={autoplay} />
                <div className="px-3 py-2">
                  <p className="line-clamp-2 font-semibold text-white">{watching.title}</p>
                  {(watching.author || watching.views) && (
                    <p className="text-[length:var(--ss-body)] text-cyan-200">
                      {watching.author}
                      {watching.author && watching.views ? ' · ' : ''}
                      {watching.views}
                    </p>
                  )}
                </div>
                <TranscriptPanel url={watching.url} onSeek={(seconds) => watchApi.current?.seekTo(seconds)} />
              </div>
            )}
            {watching && !watchId && (
              <p className="text-[length:var(--ss-body)] text-rose-300">이 주소는 바로보기를 열 수 없습니다.</p>
            )}
            {busy && results.length === 0 && <AiSearchSkeleton />}
            {!busy && results.length === 0 && (
              <p className="text-[length:var(--ss-body)] text-zinc-300">대화를 보내면 찾은 영상이 여기에 모입니다.</p>
            )}
            {results.length > 0 && (
              <ul className="space-y-2">
                {results.map((item) => (
                  <AiResultCard
                    key={item.url}
                    item={item}
                    active={watching?.url === item.url}
                    onWatch={watchVideo}
                    onVideo={(next) => startDownload(next, 'video')}
                    onAudio={(next) => startDownload(next, 'audio')}
                  />
                ))}
              </ul>
            )}
            {!busy && lastUser && <MoreOnYoutube query={moreQuery} />}
          </div>
        </section>
      </div>
    </main>
  );
}
