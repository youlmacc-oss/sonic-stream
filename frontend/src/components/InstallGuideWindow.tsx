'use client';

import React from 'react';
import InstallNeeded from '@/components/InstallNeeded';
import type { RuntimeInfo } from '@/lib/constants';
import { openInstallWindow } from '@/lib/searchWindow';

interface InstallGuideWindowProps {
  runtime?: RuntimeInfo | null;
  onClose?: () => void;
}

export default function InstallGuideWindow({ runtime, onClose }: InstallGuideWindowProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="install-guide-title"
        className="flex max-h-[92dvh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-cyan-700 bg-zinc-900 shadow-2xl"
      >
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-zinc-700 px-4 py-3">
          <h2 id="install-guide-title" className="text-[length:var(--ss-title)] font-semibold text-white">
            설치 안내
          </h2>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => openInstallWindow()}
              className="rounded-lg border border-zinc-600 bg-zinc-800 px-2.5 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-700"
            >
              새 창으로
            </button>
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-zinc-600 bg-zinc-800 px-2.5 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-700"
              >
                닫기
              </button>
            )}
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <InstallNeeded runtime={runtime} />
        </div>
      </div>
    </div>
  );
}
