import { describe, expect, it } from 'vitest';
import {
  toProcessingSnapshot,
  type ProcessingRow,
} from '../src/processing/processing-service.js';

const base: ProcessingRow = {
  id: '00000000-0000-4000-8000-000000000001',
  title: 'Practice video',
  videoStatus: 'ready',
  videoUpdatedAt: new Date('2026-09-23T10:00:00.000Z'),
  videoFailureCode: null,
  thumbnailStatus: null,
  thumbnailUpdatedAt: null,
  thumbnailFailureCode: null,
};

describe('processing snapshot', () => {
  it('shows a ready video without a bundle as waiting for thumbnails', () => {
    const snapshot = toProcessingSnapshot(
      [base],
      new Date('2026-09-23T10:01:00Z'),
    );
    expect(snapshot.activeCount).toBe(1);
    expect(snapshot.items).toEqual([
      expect.objectContaining({
        videoId: base.id,
        task: 'thumbnails',
        state: 'waiting',
      }),
    ]);
  });

  it('uses only safe failure codes and excludes finished work', () => {
    const snapshot = toProcessingSnapshot([
      { ...base, videoStatus: 'failed', videoFailureCode: 'probe_failed' },
      {
        ...base,
        id: '00000000-0000-4000-8000-000000000002',
        thumbnailStatus: 'ready',
      },
    ]);
    expect(snapshot.failedCount).toBe(1);
    expect(snapshot.items).toHaveLength(1);
    expect(snapshot.items[0]).toMatchObject({
      task: 'inspect',
      state: 'failed',
      failureCode: 'probe_failed',
    });
    expect(JSON.stringify(snapshot)).not.toContain('/Users/');
  });

  it('labels failed uploads as import work', () => {
    const snapshot = toProcessingSnapshot([
      { ...base, videoStatus: 'failed', videoFailureCode: 'upload_failed' },
    ]);
    expect(snapshot.items[0]).toMatchObject({
      task: 'import',
      state: 'failed',
    });
  });

  it('counts all work before limiting the list', () => {
    const rows = Array.from({ length: 120 }, (_, index) => ({
      ...base,
      id: `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
      videoStatus: 'queued' as const,
    }));
    const snapshot = toProcessingSnapshot(rows);
    expect(snapshot.activeCount).toBe(120);
    expect(snapshot.items).toHaveLength(100);
  });
});
