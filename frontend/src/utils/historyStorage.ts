import type { DownloadHistoryItem } from '@/types/history';

export const HISTORY_STORAGE_KEY = 'sonicstream.history.v1';
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

export function persistHistory(items: DownloadHistoryItem[]): DownloadHistoryItem[] {
  const next = items.slice(0, MAX_ITEMS);
  if (canUseStorage()) {
    try {
      window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(next));
    } catch {
      // quota / private mode — keep in-memory result only
    }
  }
  notify(next);
  return next;
}

export function addHistoryItem(
  draft: Omit<DownloadHistoryItem, 'id' | 'downloadedAt'>,
): DownloadHistoryItem[] {
  const downloadedAt = Date.now();
  const item: DownloadHistoryItem = {
    ...draft,
    id: `${downloadedAt}-${Math.random().toString(36).slice(2, 8)}`,
    downloadedAt,
  };
  const current = loadHistory().filter(
    (entry) => !(entry.url === item.url && entry.type === item.type && entry.quality === item.quality),
  );
  return persistHistory([item, ...current]);
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
