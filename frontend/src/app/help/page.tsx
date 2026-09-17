'use client';

import React, { useEffect } from 'react';
import HelpGuide from '@/components/HelpGuide';
import WindowControls from '@/components/WindowControls';
import { applyLargeTypeClass, loadLargeType } from '@/utils/textSize';

export default function HelpPage() {
  useEffect(() => {
    applyLargeTypeClass(loadLargeType());
    document.title = 'SonicStream 도움말';
  }, []);

  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-[length:var(--ss-title)] font-semibold text-white">사용 방법</h1>
        <div className="flex items-center gap-1.5">
          <WindowControls />
          <button
            type="button"
            onClick={() => window.close()}
            className="rounded-lg border border-zinc-600 bg-zinc-800 px-2.5 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-700"
          >
            닫기
          </button>
        </div>
      </div>
      <HelpGuide />
    </main>
  );
}
