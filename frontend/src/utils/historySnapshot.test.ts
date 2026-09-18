import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  EMPTY_HISTORY,
  HistorySnapshotCache,
  parseHistoryRaw,
} from './historySnapshot';

function sample(id: string, downloadedAt = 1): Record<string, unknown> {
  return {
    id,
    url: `https://youtu.be/${id}`,
    title: `title-${id}`,
    author: 'channel',
    thumbnail: 'https://example.com/t.jpg',
    duration: '1:00',
    type: 'video',
    quality: '1080p',
    downloadedAt,
  };
}

describe('history snapshot cache', () => {
  it('returns the same empty reference for missing, invalid, and corrupt JSON', () => {
    assert.equal(parseHistoryRaw(null), EMPTY_HISTORY);
    assert.equal(parseHistoryRaw(''), EMPTY_HISTORY);
    assert.equal(parseHistoryRaw('{}'), EMPTY_HISTORY);
    assert.equal(parseHistoryRaw('{not-json'), EMPTY_HISTORY);
    assert.equal(parseHistoryRaw('[]'), EMPTY_HISTORY);
  });

  it('keeps the same snapshot reference while the raw value is unchanged', () => {
    const cache = new HistorySnapshotCache();
    const raw = JSON.stringify([sample('a', 20), sample('b', 10)]);
    const first = cache.readFromRaw(raw);
    const second = cache.readFromRaw(raw);
    const third = cache.readFromRaw(raw);
    assert.equal(first.length, 2);
    assert.equal(first[0].id, 'a');
    assert.equal(first, second);
    assert.equal(second, third);
  });

  it('returns a new snapshot only after the stored data changes', () => {
    const cache = new HistorySnapshotCache();
    const firstRaw = JSON.stringify([sample('a', 20)]);
    const first = cache.readFromRaw(firstRaw);
    const same = cache.readFromRaw(firstRaw);
    assert.equal(first, same);

    const secondRaw = JSON.stringify([sample('a', 20), sample('b', 30)]);
    const second = cache.readFromRaw(secondRaw);
    assert.notEqual(first, second);
    assert.equal(second[0].id, 'b');
    assert.equal(cache.readFromRaw(secondRaw), second);
  });

  it('reuses the empty snapshot after a write that clears history', () => {
    const cache = new HistorySnapshotCache();
    cache.readFromRaw(JSON.stringify([sample('a')]));
    const cleared = cache.adopt([]);
    assert.equal(cleared, EMPTY_HISTORY);
    assert.equal(cache.readFromRaw('[]'), EMPTY_HISTORY);
    assert.equal(cache.readFromRaw(null), EMPTY_HISTORY);
  });

  it('keeps the last snapshot when adopt writes the same items', () => {
    const cache = new HistorySnapshotCache();
    const items = [sample('a', 5)] as ReturnType<HistorySnapshotCache['get']>;
    const first = cache.adopt(items);
    const second = cache.adopt([{ ...items[0] }]);
    assert.equal(first, second);
  });
});
