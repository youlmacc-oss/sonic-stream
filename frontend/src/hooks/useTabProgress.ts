'use client';

import { useEffect, useRef } from 'react';

const BASE_TITLE = 'SonicStream';

export type TabProgressStatus =
  | 'idle'
  | 'inspecting'
  | 'downloading'
  | 'processing'
  | 'completed'
  | 'error';

function ensureFaviconLink(): HTMLLinkElement {
  let link = document.querySelector<HTMLLinkElement>("link[rel='icon']");
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  return link;
}

function paintFavicon(percent: number, done = false) {
  const canvas = document.createElement('canvas');
  canvas.width = 32;
  canvas.height = 32;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  ctx.fillStyle = '#0B0C10';
  ctx.beginPath();
  ctx.arc(16, 16, 15, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = done ? '#34d399' : '#00F0FF';
  ctx.lineWidth = 3;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.arc(16, 16, 11, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * Math.min(percent, 100)) / 100);
  ctx.stroke();

  ensureFaviconLink().href = canvas.toDataURL('image/png');
}

function restoreFavicon(href: string | null) {
  const link = document.querySelector<HTMLLinkElement>("link[rel='icon']");
  if (!link) return;
  if (href) {
    link.href = href;
    return;
  }
  link.href = '/favicon.ico';
}

export function useTabProgress(status: TabProgressStatus, percent: number) {
  const originalTitle = useRef<string | null>(null);
  const originalFavicon = useRef<string | null>(null);
  const restoreTimer = useRef<number | null>(null);
  const holdingComplete = useRef(false);

  useEffect(() => {
    if (typeof document === 'undefined') return;

    if (originalTitle.current === null) {
      originalTitle.current = document.title || BASE_TITLE;
    }

    const existing = document.querySelector<HTMLLinkElement>("link[rel='icon']");
    if (existing && originalFavicon.current === null) {
      originalFavicon.current = existing.href;
    }

    if (restoreTimer.current) {
      window.clearTimeout(restoreTimer.current);
      restoreTimer.current = null;
    }

    if (status === 'downloading' || status === 'processing') {
      const shown = Math.round(status === 'processing' ? 95 : Math.min(percent, 100));
      document.title = `[${shown}%] 다운로드 중... | SonicStream`;
      paintFavicon(shown);
      return;
    }

    if (status === 'completed') {
      holdingComplete.current = true;
      document.title = '✓ 다운로드 완료! | SonicStream';
      paintFavicon(100, true);
      restoreTimer.current = window.setTimeout(() => {
        holdingComplete.current = false;
        document.title = originalTitle.current || BASE_TITLE;
        restoreFavicon(originalFavicon.current);
      }, 5000);
      return;
    }

    if (holdingComplete.current && status === 'idle') {
      return;
    }

    holdingComplete.current = false;
    document.title = originalTitle.current || BASE_TITLE;
    restoreFavicon(originalFavicon.current);

    return () => {
      if (restoreTimer.current) {
        window.clearTimeout(restoreTimer.current);
      }
    };
  }, [status, percent]);
}
