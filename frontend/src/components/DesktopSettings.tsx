'use client';

import React, { useState } from 'react';
import { FolderOpen, FolderSearch } from 'lucide-react';
import { apiInit, getApiBase, type RuntimeInfo } from '@/lib/constants';

interface DesktopSettingsProps {
  saveDir?: string | null;
  autostart?: boolean;
  onRuntime: (next: RuntimeInfo) => void;
  variant?: 'desktop' | 'web';
}

export default function DesktopSettings({ saveDir, autostart, onRuntime, variant = 'desktop' }: DesktopSettingsProps) {
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [apiKey, setApiKey] = useState('');

  const apply = async (payload: RuntimeInfo) => {
    onRuntime(payload);
    setMessage('저장했습니다.');
  };

  const pickFolder = async () => {
    setBusy(true);
    setMessage('폴더 선택 창을 열고 있습니다...');
    try {
      const response = await fetch(`${getApiBase()}/api/local/pick-folder`, { method: 'POST' });
      const body = (await response.json()) as RuntimeInfo & { ok?: boolean; cancelled?: boolean; message?: string };
      if (body.cancelled) {
        setMessage('폴더 선택을 취소했습니다.');
        return;
      }
      if (!response.ok) {
        setMessage(body.message || '폴더를 바꾸지 못했습니다.');
        return;
      }
      await apply(body);
    } catch {
      setMessage('폴더를 바꾸지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  const openFolder = async () => {
    try {
      await fetch(`${getApiBase()}/api/local/open`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: '', action: 'folder' }),
      });
    } catch {
      setMessage('저장 폴더를 열지 못했습니다.');
    }
  };

  const shutdown = async () => {
    if (!window.confirm('SonicStream을 종료할까요? 받은 파일은 그대로 있습니다.')) return;
    try {
      await fetch(`${getApiBase()}/api/local/shutdown`, { method: 'POST' });
      setMessage('프로그램을 종료했습니다. 다시 쓰려면 바탕화면 아이콘을 누르세요.');
    } catch {
      setMessage('종료 신호를 보냈습니다.');
    }
  };

  const saveApiKey = async () => {
    const key = apiKey.trim();
    if (!key) {
      setMessage('API 키를 입력해 주세요.');
      return;
    }
    setBusy(true);
    setMessage(variant === 'web' ? '키를 확인하고 있습니다...' : '');
    try {
      const response = await fetch(
        variant === 'web' ? `${getApiBase()}/api/web/session` : `${getApiBase()}/api/local/settings`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ openai_api_key: key }),
          ...apiInit(),
        },
      );
      const body = (await response.json()) as RuntimeInfo & { message?: string; openai_label?: string; retention_label?: string };
      if (!response.ok) {
        setMessage(body.message || 'API 키를 저장하지 못했습니다.');
        return;
      }
      setApiKey('');
      if (variant === 'web') {
        window.dispatchEvent(new Event('sonicstream:status'));
        const label = body.openai_label || '상태를 확인했습니다.';
        setMessage(body.retention_label ? `${label} ${body.retention_label}` : label);
        return;
      }
      await apply(body);
      setMessage(body.openai_label || '저장하고 연결했습니다.');
    } catch {
      setMessage(variant === 'web' ? '배포 프로그램에 연결할 수 없습니다.' : 'API 키를 저장하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  const toggleAutostart = async () => {
    setBusy(true);
    try {
      const response = await fetch(`${getApiBase()}/api/local/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ autostart: !autostart }),
      });
      const body = (await response.json()) as RuntimeInfo & { message?: string };
      if (!response.ok) {
        setMessage(body.message || '시작 프로그램 설정을 바꾸지 못했습니다.');
        return;
      }
      await apply(body);
    } catch {
      setMessage('시작 프로그램 설정을 바꾸지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-2 space-y-1.5 rounded-lg border border-zinc-600 bg-zinc-950 px-2.5 py-2">
      {variant === 'desktop' && (
        <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold text-white">저장 폴더</p>
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            disabled={busy}
            onClick={() => void pickFolder()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-700 px-2.5 text-[length:var(--ss-button)] text-white hover:bg-zinc-600"
          >
            <FolderSearch className="h-4 w-4" />
            폴더 바꾸기
          </button>
          <button
            type="button"
            onClick={() => void openFolder()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-500 px-2.5 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-800"
          >
            <FolderOpen className="h-4 w-4" />
            폴더 열기
          </button>
        </div>
      </div>
      <p className="truncate font-mono text-[length:var(--ss-body)] text-zinc-100" title={saveDir || undefined}>
        {saveDir || '기본 폴더: 다운로드\\SonicStream'}
      </p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-[length:var(--ss-body)] text-zinc-100">
          <input
            type="checkbox"
            checked={Boolean(autostart)}
            disabled={busy}
            onChange={() => void toggleAutostart()}
            className="h-4 w-4"
          />
          켜질 때 같이 시작
        </label>
        <button
          type="button"
          onClick={() => void shutdown()}
          className="rounded-lg border border-zinc-500 px-2.5 text-[length:var(--ss-button)] text-zinc-200 hover:bg-zinc-800"
        >
          프로그램 종료
        </button>
      </div>
        </>
      )}
      <div className="space-y-1.5 border-t border-zinc-800 pt-1.5">
        <p className="font-semibold text-white">AI 연결</p>
        <p className="text-[length:var(--ss-body)] text-zinc-300">
          {variant === 'web'
            ? '키는 이 브라우저 세션에만 12시간 보관됩니다. 서버가 다시 시작되면 다시 입력해야 합니다. 이 컴퓨터나 서버 .env에 저장하지 않습니다.'
            : 'OpenAI API 키를 이 컴퓨터에 넣으면 AI 검색을 쓸 수 있습니다.'}
        </p>
        <div className="flex flex-wrap gap-1.5">
          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="sk-로 시작하는 키"
            autoComplete="off"
            className="min-w-0 flex-1 rounded-lg border border-zinc-600 bg-zinc-900 px-2.5 text-[length:var(--ss-body)] text-zinc-100 placeholder-zinc-500"
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => void saveApiKey()}
            className="rounded-lg bg-zinc-700 px-2.5 text-[length:var(--ss-button)] text-white hover:bg-zinc-600"
          >
            저장하고 연결
          </button>
        </div>
        {variant === 'web' && (
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              void fetch(`${getApiBase()}/api/web/session`, { method: 'DELETE', ...apiInit() }).then(() => {
                window.dispatchEvent(new Event('sonicstream:status'));
                setMessage('이 브라우저 세션의 키를 지웠습니다.');
              }).catch(() => setMessage('키를 지우지 못했습니다.'));
            }}
            className="rounded-lg border border-zinc-500 px-2.5 text-[length:var(--ss-button)] text-zinc-200 hover:bg-zinc-800"
          >
            세션 키 지우기
          </button>
        )}
      </div>
      {message && <p className="text-[length:var(--ss-body)] text-zinc-200">{message}</p>}
    </div>
  );
}
