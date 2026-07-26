import { describe, expect, it } from 'vitest';
import {
  createSegment,
  fragmentForDeletionKey,
  sortSegmentsByStart,
  type SegmentState,
} from './segments.js';

const segmentIds = [
  '10000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000002',
  '10000000-0000-4000-8000-000000000003',
  '10000000-0000-4000-8000-000000000004',
  '10000000-0000-4000-8000-000000000005',
] as const;

function emptyState(): SegmentState {
  return { segments: [], selectedSegmentId: null };
}

function segment(id: string, startSeconds: number, endSeconds: number) {
  return {
    id,
    startSeconds,
    endSeconds,
    exportSelected: true,
    title: null,
    tagIds: [],
  };
}

describe('segment operations', () => {
  it('creates segments in creation order without changing playback selection', () => {
    let state = emptyState();

    for (const [index, id] of segmentIds.slice(0, 3).entries()) {
      const result = createSegment(
        state,
        index * 4,
        index * 4 + 4,
        12,
        () => id,
      );
      expect(result.ok).toBe(true);
      state = result.state;
    }

    expect(state.segments.map((segment) => segment.id)).toEqual(
      segmentIds.slice(0, 3),
    );
    expect(state.selectedSegmentId).toBeNull();
    expect(state.segments.every((segment) => segment.exportSelected)).toBe(
      true,
    );

    const withSelection = {
      ...state,
      selectedSegmentId: segmentIds[0],
    };
    const additional = createSegment(
      withSelection,
      1,
      2,
      12,
      () => segmentIds[3],
    );

    expect(additional.ok).toBe(true);
    expect(additional.state.selectedSegmentId).toBe(segmentIds[0]);
  });

  it('sorts a copy chronologically by start, end, and ID', () => {
    const state = [
      segment(segmentIds[3], 8, 12),
      segment(segmentIds[2], 2, 7),
      segment(segmentIds[1], 2, 6),
      segment(segmentIds[0], 2, 6),
    ];

    const sorted = sortSegmentsByStart(state);

    expect(sorted.map((segment) => segment.id)).toEqual([
      segmentIds[0],
      segmentIds[1],
      segmentIds[2],
      segmentIds[3],
    ]);
    expect(sorted).not.toBe(state);
    expect(state[0]?.id).toBe(segmentIds[3]);
  });

  it('routes Delete to the selected fragment without mutating the editor', () => {
    const state = [segment(segmentIds[0], 1, 2), segment(segmentIds[1], 3, 4)];
    const input = { segments: state, selectedSegmentId: segmentIds[0] };

    expect(fragmentForDeletionKey(input, 'Delete')?.id).toBe(segmentIds[0]);
    expect(input.segments).toBe(state);
    expect(input.segments).toHaveLength(2);
  });

  it('routes Backspace to the most recently created fragment', () => {
    const input = {
      segments: [segment(segmentIds[0], 10, 12), segment(segmentIds[1], 2, 4)],
      selectedSegmentId: segmentIds[0],
    };

    expect(fragmentForDeletionKey(input, 'Backspace')?.id).toBe(segmentIds[1]);
    expect(input.segments).toHaveLength(2);
  });

  it.each([
    { startSeconds: null, endSeconds: 2, code: 'invalid_range' },
    { startSeconds: 2, endSeconds: 2, code: 'invalid_range' },
    { startSeconds: 3, endSeconds: 2, code: 'invalid_range' },
    { startSeconds: 8, endSeconds: 11, code: 'outside_source' },
  ] as const)(
    'keeps the same state and explains invalid O behavior: %o',
    ({ startSeconds, endSeconds, code }) => {
      const input = emptyState();
      const result = createSegment(input, startSeconds, endSeconds, 10);

      expect(result).toMatchObject({ ok: false, code });
      expect(result.state).toBe(input);
    },
  );

  it('rejects a third overlap without mutating state', () => {
    const input = {
      segments: [segment(segmentIds[0], 1, 5), segment(segmentIds[1], 2, 6)],
      selectedSegmentId: segmentIds[1],
    };

    const result = createSegment(input, 3, 4, 10, () => segmentIds[2]);

    expect(result).toMatchObject({ ok: false, code: 'triple_overlap' });
    expect(result.state).toBe(input);
  });
});
