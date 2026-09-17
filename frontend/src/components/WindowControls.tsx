'use client';

import React from 'react';
import { Maximize2, Minimize2, Square } from 'lucide-react';
import { getApiBase } from '@/lib/constants';
import { applyWindowBox, fillWorkArea, fitWindowInWorkArea } from '@/lib/workArea';

type WindowAction = 'minimize' | 'maximize' | 'restore';

async function applyWindowAction(action: WindowAction) {
  if (action === 'maximize') {
    fillWorkArea();
  }
  if (action === 'restore') {
    applyWindowBox(window, fitWindowInWorkArea(1280, 800));
  }
  try {
    await fetch(`${getApiBase()}/api/local/window`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    });
  } catch {
    // browser-only session
  }
}

export default function WindowControls() {
  return (
    <div className="flex shrink-0 items-center gap-1" aria-label="창 조절">
      <button
        type="button"
        onClick={() => void applyWindowAction('minimize')}
        className="rounded-lg border border-zinc-600 bg-zinc-800 px-2 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-700"
        title="최소화"
        aria-label="최소화"
      >
        <Minimize2 className="inline h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={() => void applyWindowAction('maximize')}
        className="rounded-lg border border-zinc-600 bg-zinc-800 px-2 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-700"
        title="전체"
        aria-label="전체"
      >
        <Maximize2 className="inline h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={() => void applyWindowAction('restore')}
        className="rounded-lg border border-zinc-600 bg-zinc-800 px-2 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-700"
        title="조절창"
        aria-label="조절창"
      >
        <Square className="inline h-3.5 w-3.5" />
      </button>
    </div>
  );
}
