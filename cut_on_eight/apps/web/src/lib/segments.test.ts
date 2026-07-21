import { describe, expect, it } from 'vitest';
import {
  createSegment,
  deleteMostRecentSegment,
  deleteSelectedSegment,
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

describe('segment operations', () => {
  it('creates and selects segments in creation order', () => {
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
    expect(state.selectedSegmentId).toBe(segmentIds[2]);
    expect(state.segments.every((segment) => segment.exportSelected)).toBe(
      true,
    );
  });

  it('sorts a copy chronologically by start, end, and ID', () => {
    const state = [
      {
        id: segmentIds[3],
        startSeconds: 8,
        endSeconds: 12,
        exportSelected: true,
      },
      {
        id: segmentIds[2],
        startSeconds: 2,
        endSeconds: 7,
        exportSelected: true,
      },
      {
        id: segmentIds[1],
        startSeconds: 2,
        endSeconds: 6,
        exportSelected: true,
      },
      {
        id: segmentIds[0],
        startSeconds: 2,
        endSeconds: 6,
        exportSelected: true,
      },
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

  it('deletes the selected segment and clears the selection without mutation', () => {
    const state = [
      {
        id: segmentIds[0],
        startSeconds: 1,
        endSeconds: 2,
        exportSelected: true,
      },
      {
        id: segmentIds[1],
        startSeconds: 3,
        endSeconds: 4,
        exportSelected: true,
      },
    ];
    const input = { segments: state, selectedSegmentId: segmentIds[0] };

    const result = deleteSelectedSegment(input);

    expect(result.segments.map((segment) => segment.id)).toEqual([
      segmentIds[1],
    ]);
    expect(result.selectedSegmentId).toBeNull();
    expect(input.segments).toBe(state);
    expect(input.segments).toHaveLength(2);
  });

  it('deletes the most recently created segment rather than the latest by time', () => {
    const input = {
      segments: [
        {
          id: segmentIds[0],
          startSeconds: 10,
          endSeconds: 12,
          exportSelected: true,
        },
        {
          id: segmentIds[1],
          startSeconds: 2,
          endSeconds: 4,
          exportSelected: true,
        },
      ],
      selectedSegmentId: segmentIds[0],
    };

    const result = deleteMostRecentSegment(input);

    expect(result.segments.map((segment) => segment.id)).toEqual([
      segmentIds[0],
    ]);
    expect(result.selectedSegmentId).toBe(segmentIds[0]);
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
      segments: [
        {
          id: segmentIds[0],
          startSeconds: 1,
          endSeconds: 5,
          exportSelected: true,
        },
        {
          id: segmentIds[1],
          startSeconds: 2,
          endSeconds: 6,
          exportSelected: true,
        },
      ],
      selectedSegmentId: segmentIds[1],
    };

    const result = createSegment(input, 3, 4, 10, () => segmentIds[2]);

    expect(result).toMatchObject({ ok: false, code: 'triple_overlap' });
    expect(result.state).toBe(input);
  });

  it('clears selection when deleting the most recent selected segment', () => {
    const input = {
      segments: [
        {
          id: segmentIds[0],
          startSeconds: 1,
          endSeconds: 2,
          exportSelected: true,
        },
      ],
      selectedSegmentId: segmentIds[0],
    };

    expect(deleteMostRecentSegment(input)).toEqual({
      segments: [],
      selectedSegmentId: null,
    });
  });
});
