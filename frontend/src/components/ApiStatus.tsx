'use client';

import React, { useEffect, useState } from 'react';
import { DISCONNECTED, fetchConnectionStatus, hasSavedOpenaiKey, type ConnectionStatus } from '@/lib/apiStatus';

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? 'bg-emerald-400' : 'bg-rose-400'}`}
      aria-hidden
    />
  );
}

export default function ApiStatus() {
  const [status, setStatus] = useState<ConnectionStatus>(DISCONNECTED);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      const next = await fetchConnectionStatus();
      if (!cancelled) setStatus(next);
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 8000);
    const onSaved = () => void refresh();
    window.addEventListener('sonicstream:status', onSaved);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener('sonicstream:status', onSaved);
    };
  }, []);

  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[length:var(--ss-body)] text-zinc-200" aria-live="polite">
      <p className="inline-flex items-center gap-1.5 rounded-full border border-zinc-600 bg-zinc-900 px-2 py-0.5">
        <Dot ok={status.engine === 'ok'} />
        {status.engine_label}
      </p>
      <p className="inline-flex items-center gap-1.5 rounded-full border border-zinc-600 bg-zinc-900 px-2 py-0.5">
        <Dot ok={hasSavedOpenaiKey(status)} />
        {status.openai_label}
        {status.openai_model ? ` · ${status.openai_model}` : ''}
      </p>
    </div>
  );
}
