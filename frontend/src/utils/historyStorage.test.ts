import assert from 'node:assert/strict';
import { afterEach, describe, it } from 'node:test';

type StorageMap = Map<string, string>;

function installMemoryStorage(map: StorageMap) {
  const localStorage = {
    getItem(key: string) {
      return map.has(key) ? map.get(key)! : null;
    },
    setItem(key: string, value: string) {
      map.set(key, value);
    },
    removeItem(key: string) {
      map.delete(key);
    },
  };
  (globalThis as { window?: unknown }).window = {
    localStorage,
    addEventListener() {},
    removeEventListener() {},
    fetch: async () => {
      throw new Error('network disabled in test');
    },
  };
}

async function loadStore() {
  return import('./historyStorage');
}

describe('historyStorage snapshots', () => {
  afterEach(async () => {
    const store = await loadStore();
    store.resetHistorySnapshotsForTests();
    delete (globalThis as { window?: unknown }).window;
  });

  it('returns the same empty snapshot on repeated reads', async () => {
    installMemoryStorage(new Map());
    const store = await loadStore();
    store.resetHistorySnapshotsForTests();
    const first = store.loadHistory();
    const second = store.loadHistory();
    const third = store.getServerHistorySnapshot();
    assert.equal(first, second);
    assert.equal(first, third);
    assert.equal(first.length, 0);
  });

  it('returns the same populated snapshot until history changes', async () => {
    installMemoryStorage(new Map());
    const store = await loadStore();
    store.resetHistorySnapshotsForTests();
    const item = {
      url: 'https://youtu.be/a',
      title: 'one',
      author: 'ch',
      thumbnail: 'https://example.com/t.jpg',
      duration: '1:00',
      type: 'video' as const,
      quality: '1080p',
    };
    const saved = store.addHistoryItem(item);
    const first = store.loadHistory();
    const second = store.loadHistory();
    assert.equal(first, second);
    assert.equal(first[0].id, saved.id);

    store.updateHistoryItem(saved.id, { status: 'saved' });
    const updated = store.loadHistory();
    assert.notEqual(first, updated);
    assert.equal(updated[0].status, 'saved');
    assert.equal(store.loadHistory(), updated);

    const removed = store.removeHistoryItem(saved.id);
    assert.notEqual(updated, removed);
    assert.equal(removed.length, 0);
    assert.equal(store.loadHistory(), removed);
  });

  it('does not notify while reading a snapshot', async () => {
    installMemoryStorage(new Map());
    const store = await loadStore();
    store.resetHistorySnapshotsForTests();
    let calls = 0;
    const stop = store.subscribeHistory(() => {
      calls += 1;
    });
    store.loadHistory();
    store.loadHistory();
    assert.equal(calls, 0);
    store.addHistoryItem({
      url: 'https://youtu.be/b',
      title: 'two',
      author: 'ch',
      thumbnail: 'https://example.com/t.jpg',
      duration: '1:00',
      type: 'audio',
      quality: '320k',
    });
    assert.equal(calls, 1);
    stop();
  });

  it('keeps the empty snapshot when storage throws or JSON is corrupt', async () => {
    const map: StorageMap = new Map([['sonicstream.history.v1', '{bad']]);
    const localStorage = {
      getItem() {
        return map.get('sonicstream.history.v1') ?? null;
      },
      setItem() {},
      removeItem() {},
    };
    (globalThis as { window?: unknown }).window = {
      localStorage,
      addEventListener() {},
      removeEventListener() {},
      fetch: async () => {
        throw new Error('network disabled in test');
      },
    };
    const store = await loadStore();
    store.resetHistorySnapshotsForTests();
    const corrupt = store.loadHistory();
    assert.equal(corrupt, store.getServerHistorySnapshot());

    (globalThis as { window?: { localStorage: { getItem: () => string } } }).window = {
      localStorage: {
        getItem() {
          throw new Error('denied');
        },
      },
    };
    const denied = store.loadHistory();
    assert.equal(denied, store.getServerHistorySnapshot());
  });
});
