import type { ProcessingSnapshotDto } from '@cut-on-eight/api-contracts';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProcessingModel } from './processing-model.svelte.js';

const snapshot: ProcessingSnapshotDto = {
  activeCount: 1,
  failedCount: 0,
  observedAt: '2026-09-23T10:00:00.000Z',
  items: [
    {
      videoId: '00000000-0000-4000-8000-000000000001',
      videoTitle: 'Practice',
      task: 'inspect',
      state: 'running',
      updatedAt: '2026-09-23T10:00:00.000Z',
      failureCode: null,
    },
  ],
};

afterEach(() => vi.useRealTimers());

describe('ProcessingModel', () => {
  it('keeps the last snapshot when refresh fails', async () => {
    const load = vi
      .fn()
      .mockResolvedValueOnce(snapshot)
      .mockRejectedValueOnce(new Error('offline'));
    const model = new ProcessingModel(load, () => true);
    await model.refresh();
    await model.refresh();
    expect(model.snapshot).toEqual(snapshot);
    expect(model.stale).toBe(true);
  });

  it('polls only while visible and stops when disposed', async () => {
    vi.useFakeTimers();
    let visible = true;
    const load = vi.fn().mockResolvedValue(snapshot);
    const model = new ProcessingModel(load, () => visible);
    model.start();
    await vi.runAllTicks();
    expect(load).toHaveBeenCalledTimes(1);
    visible = false;
    await vi.advanceTimersByTimeAsync(5000);
    expect(load).toHaveBeenCalledTimes(1);
    visible = true;
    await vi.advanceTimersByTimeAsync(5000);
    expect(load).toHaveBeenCalledTimes(2);
    model.dispose();
    await vi.advanceTimersByTimeAsync(5000);
    expect(load).toHaveBeenCalledTimes(2);
  });
});
