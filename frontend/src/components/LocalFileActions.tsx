'use client';

import React, { useState } from 'react';
import { Copy, FolderOpen, Play } from 'lucide-react';
import { copyText, localFileAction } from '@/lib/fileActions';

interface LocalFileActionsProps {
  path: string;
  kind: 'video' | 'audio';
  compact?: boolean;
}

export default function LocalFileActions({ path, kind, compact = false }: LocalFileActionsProps) {
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const run = async (action: 'file' | 'folder') => {
    setMessage(null);
    setFailed(false);
    try {
      const result = await localFileAction(path, action);
      if (!result.ok) {
        setFailed(true);
        setMessage(result.message || '파일을 찾을 수 없습니다.');
        return;
      }
      setFailed(false);
      setMessage(null);
    } catch {
      setFailed(true);
      setMessage(action === 'folder' ? '저장 폴더를 열 수 없습니다.' : '파일을 열 수 없습니다.');
    }
  };

  const copyPath = async () => {
    const ok = await copyText(path);
    setFailed(!ok);
    setMessage(ok ? '경로를 복사했습니다.' : '경로를 복사하지 못했습니다.');
  };

  const buttonClass = compact
    ? 'inline-flex min-h-[var(--ss-tap)] items-center rounded-lg border border-zinc-500 px-2.5 text-[length:var(--ss-body)] text-zinc-100 hover:bg-zinc-800'
    : 'inline-flex min-h-[var(--ss-tap)] items-center justify-center gap-1.5 rounded-lg bg-zinc-700 px-2.5 text-[length:var(--ss-button)] font-medium text-white hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400';

  return (
    <div className="space-y-2">
      <div className={`flex flex-wrap gap-1.5 ${compact ? '' : 'pt-1'}`}>
        <button type="button" onClick={() => void run('file')} className={buttonClass}>
          <Play className={compact ? 'mr-1 inline h-4 w-4' : 'h-5 w-5'} />
          {kind === 'audio' ? '오디오 열기' : '동영상 열기'}
        </button>
        <button type="button" onClick={() => void run('folder')} className={buttonClass}>
          <FolderOpen className={compact ? 'mr-1 inline h-4 w-4' : 'h-5 w-5'} />
          저장 폴더 열기
        </button>
        {!compact && (
          <button type="button" onClick={() => void copyPath()} className={buttonClass}>
            <Copy className="h-5 w-5" />
            경로 복사
          </button>
        )}
      </div>
      {message && (
        <p className={failed ? 'text-[length:var(--ss-body)] leading-snug text-rose-300' : 'text-[length:var(--ss-body)] text-zinc-200'}>
          {message}
        </p>
      )}
    </div>
  );
}
