'use client';

import React, { useState } from 'react';
import { FolderOpen, FolderSearch } from 'lucide-react';
import { getApiBase, type RuntimeInfo } from '@/lib/constants';

interface DesktopSettingsProps {
  saveDir?: string | null;
  autostart?: boolean;
  onRuntime: (next: RuntimeInfo) => void;
}

export default function DesktopSettings({ saveDir, autostart, onRuntime }: DesktopSettingsProps) {
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
    try {
      const response = await fetch(`${getApiBase()}/api/local/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ openai_api_key: key }),
      });
      const body = (await response.json()) as RuntimeInfo & { message?: string };
      if (!response.ok) {
        setMessage(body.message || 'API 키를 저장하지 못했습니다.');
        return;
      }
      setApiKey('');
      await apply(body);
      setMessage(body.openai_label || '저장하고 연결했습니다.');
    } catch {
      setMessage('API 키를 저장하지 못했습니다.');
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
      <div className="space-y-1.5 border-t border-zinc-800 pt-1.5">
        <p className="font-semibold text-white">AI 연결</p>
        <p className="text-[length:var(--ss-body)] text-zinc-300">
          OpenAI API 키를 이 컴퓨터에 넣으면 AI 검색을 쓸 수 있습니다.
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
      </div>
      {message && <p className="text-[length:var(--ss-body)] text-zinc-200">{message}</p>}
    </div>
  );
}
