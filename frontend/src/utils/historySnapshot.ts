import type { DownloadHistoryItem } from '../types/history';

export const EMPTY_HISTORY: DownloadHistoryItem[] = [];

export function isHistoryItem(value: unknown): value is DownloadHistoryItem {
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

export function parseHistoryRaw(raw: string | null): DownloadHistoryItem[] {
  if (!raw) return EMPTY_HISTORY;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return EMPTY_HISTORY;
    const next = parsed.filter(isHistoryItem).sort((a, b) => b.downloadedAt - a.downloadedAt);
    return next.length === 0 ? EMPTY_HISTORY : next;
  } catch {
    return EMPTY_HISTORY;
  }
}

function sameHistory(left: DownloadHistoryItem[], right: DownloadHistoryItem[]): boolean {
  if (left === right) return true;
  if (left.length !== right.length) return false;
  return JSON.stringify(left) === JSON.stringify(right);
}

export class HistorySnapshotCache {
  private raw: string | null | undefined = undefined;
  private items: DownloadHistoryItem[] = EMPTY_HISTORY;

  get(): DownloadHistoryItem[] {
    return this.items;
  }

  readFromRaw(raw: string | null): DownloadHistoryItem[] {
    if (this.raw === raw) return this.items;
    const parsed = parseHistoryRaw(raw);
    if (sameHistory(this.items, parsed)) {
      this.raw = raw;
      return this.items;
    }
    this.raw = raw;
    this.items = parsed;
    return this.items;
  }

  adopt(items: DownloadHistoryItem[], raw?: string | null): DownloadHistoryItem[] {
    const next = items.length === 0 ? EMPTY_HISTORY : items;
    const serialized = raw === undefined ? JSON.stringify(next) : raw;
    if (serialized === this.raw || sameHistory(this.items, next)) {
      this.raw = serialized;
      return this.items === EMPTY_HISTORY && next === EMPTY_HISTORY ? EMPTY_HISTORY : this.items;
    }
    this.raw = serialized;
    this.items = next;
    return this.items;
  }

  reset(): void {
    this.raw = undefined;
    this.items = EMPTY_HISTORY;
  }
}
