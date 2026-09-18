'use client';

import React, { useEffect, useState, useSyncExternalStore } from 'react';
import InstallNeeded from '@/components/InstallNeeded';
import WindowControls from '@/components/WindowControls';
import { getApiBase, type RuntimeInfo } from '@/lib/constants';
import {
  getAppShell,
  getServerAppShell,
  getServerShowDevMainButton,
  getShowDevMainButton,
  openLocalMainScreen,
  subscribeAppShell,
  subscribeShowDevMainButton,
} from '@/lib/appShell';
import { applyLargeTypeClass, loadLargeType } from '@/utils/textSize';

export default function InstallPage() {
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const shell = useSyncExternalStore(subscribeAppShell, getAppShell, getServerAppShell);
  const showDevMain = useSyncExternalStore(
    subscribeShowDevMainButton,
    getShowDevMainButton,
    getServerShowDevMainButton,
  );
  const local = shell === 'local';

  useEffect(() => {
    applyLargeTypeClass(loadLargeType());
    document.title = 'SonicStream 설치';
    if (!local) return undefined;
    const controller = new AbortController();
    fetch(`${getApiBase()}/api/runtime`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: RuntimeInfo | null) => {
        setRuntime(payload);
      })
      .catch(() => {
        setRuntime(null);
      });
    return () => controller.abort();
  }, [local]);

  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-[length:var(--ss-title)] font-semibold text-white">설치 안내</h1>
        <div className="flex items-center gap-1.5">
          {showDevMain && (
            <button
              type="button"
              onClick={() => openLocalMainScreen()}
              className="rounded-lg border border-cyan-500 bg-cyan-950 px-2.5 text-[length:var(--ss-button)] font-semibold text-cyan-100 hover:bg-cyan-900"
            >
              메인 화면
            </button>
          )}
          {local && <WindowControls />}
          <button
            type="button"
            onClick={() => window.close()}
            className="rounded-lg border border-zinc-600 bg-zinc-800 px-2.5 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-700"
          >
            닫기
          </button>
        </div>
      </div>
      <InstallNeeded runtime={local ? runtime : null} />
    </main>
  );
}
