'use client';

import React, { useRef, useState } from 'react';
import { ChevronDown, Copy, ScrollText } from 'lucide-react';
import { copyText } from '@/lib/fileActions';
import { fetchTranscript, type TranscriptLine } from '@/lib/searchWindow';

function formatCue(seconds: number) {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  if (hours) return `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
  return `${minutes}:${String(rest).padStart(2, '0')}`;
}

function languageLabel(language: string, automatic: boolean) {
  const korean = language.toLowerCase().startsWith('ko');
  const english = language.toLowerCase().startsWith('en');
  const name = korean ? '한글' : english ? '영어' : language || '대본';
  return automatic ? `자동 ${name}` : name;
}

interface TranscriptPanelProps {
  url: string;
  onSeek: (seconds: number) => void;
}

export default function TranscriptPanel({ url, onSeek }: TranscriptPanelProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  const [language, setLanguage] = useState('');
  const [automatic, setAutomatic] = useState(false);
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [loadedFor, setLoadedFor] = useState('');
  const requestRef = useRef(0);

  const shownLines = loadedFor === url ? lines : [];
  const shownError = loadedFor === url ? error : '';
  const shownLanguage = loadedFor === url ? language : '';

  const load = async () => {
    if (!url || busy) return;
    if (loadedFor === url && (lines.length > 0 || error)) {
      setOpen(true);
      return;
    }
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    setBusy(true);
    setError('');
    setOpen(true);
    try {
      const result = await fetchTranscript(url);
      if (requestRef.current !== requestId) return;
      setLanguage(result.language);
      setAutomatic(result.automatic);
      setLines(result.lines);
      setLoadedFor(url);
      if (result.lines.length === 0) {
        setError(result.error || '이 영상은 대본이 없습니다.');
      }
    } catch (fail) {
      if (requestRef.current !== requestId) return;
      setLines([]);
      setLoadedFor(url);
      setError(fail instanceof Error ? fail.message : '대본을 가져오지 못했습니다.');
    } finally {
      if (requestRef.current === requestId) setBusy(false);
    }
  };

  const copyAll = async () => {
    const ok = await copyText(lines.map((line) => line.text).join('\n'));
    if (!ok) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className="border-t border-zinc-800">
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          onClick={() => {
            if (open) setOpen(false);
            else void load();
          }}
          className="inline-flex min-h-[var(--ss-tap)] flex-1 items-center gap-1.5 rounded-lg px-2 text-left text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-800"
        >
          <ScrollText className="h-4 w-4" />
          대본
          {shownLanguage && !busy && !shownError && (
            <span className="text-zinc-400">· {languageLabel(shownLanguage, automatic)}</span>
          )}
          <ChevronDown className={`ml-auto h-4 w-4 ${open ? 'rotate-180' : ''}`} />
        </button>
        {open && shownLines.length > 0 && (
          <button
            type="button"
            onClick={() => void copyAll()}
            className="inline-flex min-h-[var(--ss-tap)] items-center gap-1 rounded-lg px-2 text-[length:var(--ss-button)] text-zinc-300 hover:bg-zinc-800 hover:text-white"
          >
            <Copy className="h-3.5 w-3.5" />
            {copied ? '복사됨' : '복사'}
          </button>
        )}
      </div>
      {open && (
        <div className="max-h-56 overflow-y-auto px-3 pb-3">
          {busy && <p className="text-[length:var(--ss-body)] text-cyan-200">대본을 읽는 중...</p>}
          {!busy && shownError && <p className="text-[length:var(--ss-body)] text-zinc-300">{shownError}</p>}
          {!busy && !shownError && (
            <ul className="space-y-1">
              {shownLines.map((line, index) => (
                <li key={`${line.start}-${index}`}>
                  <button
                    type="button"
                    onClick={() => onSeek(line.start)}
                    className="flex w-full gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-zinc-800"
                  >
                    <span className="w-12 shrink-0 font-mono text-[length:var(--ss-body)] text-cyan-300">
                      {formatCue(line.start)}
                    </span>
                    <span className="min-w-0 text-[length:var(--ss-body)] leading-snug text-zinc-100">
                      {line.text}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
