import type { DownloadHistoryItem } from '../types/history';
import { getApiBase, apiInit } from '../lib/constants';
import { isLoopbackHost } from '../lib/site';
import { EMPTY_HISTORY, HistorySnapshotCache, isHistoryItem } from './historySnapshot';

export const HISTORY_STORAGE_KEY = 'sonicstream.history.v1';
export const ACTIVE_JOBS_KEY = 'sonicstream.activeJobs.v1';
const MAX_ITEMS = 30;

type HistoryListener = (items?: DownloadHistoryItem[]) => void;

const listeners = new Set<HistoryListener>();
const snapshots = new HistorySnapshotCache();

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function onHistoryStorage(event: StorageEvent): void {
  if (event.key !== null && event.key !== HISTORY_STORAGE_KEY) return;
  notify(loadHistory());
}

export function subscribeHistory(listener: HistoryListener): () => void {
  const start = listeners.size === 0;
  listeners.add(listener);
  if (start && typeof window !== 'undefined') {
    window.addEventListener('storage', onHistoryStorage);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && typeof window !== 'undefined') {
      window.removeEventListener('storage', onHistoryStorage);
    }
  };
}

function notify(items: DownloadHistoryItem[]): void {
  listeners.forEach((listener) => listener(items));
}

export function getServerHistorySnapshot(): DownloadHistoryItem[] {
  return EMPTY_HISTORY;
}

export function loadHistory(): DownloadHistoryItem[] {
  if (!canUseStorage()) return snapshots.get();
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    return snapshots.readFromRaw(raw);
  } catch {
    return snapshots.get();
  }
}

function pushHistoryToPc(items: DownloadHistoryItem[]): void {
  const host = typeof window === 'undefined' ? '' : window.location?.hostname || '';
  if (!host || !isLoopbackHost(host)) return;
  void fetch(`${getApiBase()}/api/local/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
    ...apiInit(),
  }).catch(() => undefined);
}

export async function hydrateHistoryFromPc(): Promise<DownloadHistoryItem[]> {
  const host = typeof window === 'undefined' ? '' : window.location?.hostname || '';
  if (!host || !isLoopbackHost(host)) return loadHistory();
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
  const raw = JSON.stringify(next);
  if (canUseStorage()) {
    try {
      window.localStorage.setItem(HISTORY_STORAGE_KEY, raw);
    } catch {
      // quota / private mode — keep in-memory result only
    }
  }
  const stored = snapshots.adopt(next, raw);
  if (syncRemote) pushHistoryToPc(stored);
  notify(stored);
  return stored;
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

export function resetHistorySnapshotsForTests(): void {
  snapshots.reset();
}
