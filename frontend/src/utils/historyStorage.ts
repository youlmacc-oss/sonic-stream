import type { DownloadHistoryItem } from '@/types/history';
import { getApiBase } from '@/lib/constants';

export const HISTORY_STORAGE_KEY = 'sonicstream.history.v1';
export const ACTIVE_JOBS_KEY = 'sonicstream.activeJobs.v1';
const MAX_ITEMS = 30;

type HistoryListener = (items: DownloadHistoryItem[]) => void;

const listeners = new Set<HistoryListener>();

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

export function subscribeHistory(listener: HistoryListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notify(items: DownloadHistoryItem[]): void {
  listeners.forEach((listener) => listener(items));
}

export function loadHistory(): DownloadHistoryItem[] {
  if (!canUseStorage()) return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isHistoryItem).sort((a, b) => b.downloadedAt - a.downloadedAt);
  } catch {
    return [];
  }
}

function pushHistoryToPc(items: DownloadHistoryItem[]): void {
  if (typeof window === 'undefined') return;
  void fetch(`${getApiBase()}/api/local/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  }).catch(() => undefined);
}

export async function hydrateHistoryFromPc(): Promise<DownloadHistoryItem[]> {
  try {
    const response = await fetch(`${getApiBase()}/api/local/history`, { cache: 'no-store' });
    if (!response.ok) return loadHistory();
    const payload = (await response.json()) as { items?: DownloadHistoryItem[] };
    const remote = (payload.items || []).filter(isHistoryItem);
    if (!remote.length) return loadHistory();
    return persistHistory(remote, false);
  } catch {
    return loadHistory();
  }
}

export function persistHistory(items: DownloadHistoryItem[], syncRemote = true): DownloadHistoryItem[] {
  const next = items.slice(0, MAX_ITEMS);
  if (canUseStorage()) {
    try {
      window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(next));
    } catch {
      // quota / private mode — keep in-memory result only
    }
  }
  if (syncRemote) pushHistoryToPc(next);
  notify(next);
  return next;
}

export function persistActiveJob(jobId: string, historyId: string) {
  if (!canUseStorage()) return;
  try {
    const raw = window.localStorage.getItem(ACTIVE_JOBS_KEY);
    const current = raw ? (JSON.parse(raw) as Record<string, string>) : {};
    current[jobId] = historyId;
    window.localStorage.setItem(ACTIVE_JOBS_KEY, JSON.stringify(current));
  } catch {
    // ignore
  }
}

export function loadActiveJobs(): Record<string, string> {
  if (!canUseStorage()) return {};
  try {
    const raw = window.localStorage.getItem(ACTIVE_JOBS_KEY);
    return raw ? (JSON.parse(raw) as Record<string, string>) : {};
  } catch {
    return {};
  }
}

export function clearActiveJob(jobId: string) {
  if (!canUseStorage()) return;
  try {
    const current = loadActiveJobs();
    delete current[jobId];
    window.localStorage.setItem(ACTIVE_JOBS_KEY, JSON.stringify(current));
  } catch {
    // ignore
  }
}

export function addHistoryItem(
  draft: Omit<DownloadHistoryItem, 'id' | 'downloadedAt'> & { id?: string; downloadedAt?: number },
): DownloadHistoryItem {
  const downloadedAt = draft.downloadedAt ?? Date.now();
  const item: DownloadHistoryItem = {
    ...draft,
    id: draft.id || `${downloadedAt}-${Math.random().toString(36).slice(2, 8)}`,
    downloadedAt,
  };
  const current = loadHistory().filter((entry) => entry.id !== item.id);
  persistHistory([item, ...current]);
  return item;
}

export function updateHistoryItem(
  id: string,
  patch: Partial<DownloadHistoryItem>,
): DownloadHistoryItem | null {
  const current = loadHistory();
  let updated: DownloadHistoryItem | null = null;
  const next = current.map((item) => {
    if (item.id !== id) return item;
    updated = { ...item, ...patch, id: item.id, url: item.url, type: item.type, quality: item.quality };
    return updated;
  });
  persistHistory(next);
  return updated;
}

export function removeHistoryItem(id: string): DownloadHistoryItem[] {
  return persistHistory(loadHistory().filter((item) => item.id !== id));
}

export function clearHistory(): DownloadHistoryItem[] {
  return persistHistory([]);
}

function isHistoryItem(value: unknown): value is DownloadHistoryItem {
  if (!value || typeof value !== 'object') return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.id === 'string'
    && typeof item.url === 'string'
    && typeof item.title === 'string'
    && typeof item.author === 'string'
    && typeof item.thumbnail === 'string'
    && typeof item.duration === 'string'
    && (item.type === 'video' || item.type === 'audio')
    && typeof item.quality === 'string'
    && typeof item.downloadedAt === 'number'
  );
}
