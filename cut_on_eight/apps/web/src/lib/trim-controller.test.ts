import type { ProjectDocument, Segment } from '@cut-on-eight/contracts';
import { describe, expect, it } from 'vitest';
import {
  adjacentSegment,
  boundaryStep,
  escapeEditing,
  focusBoundary,
  nudgeBoundary,
} from './trim-controller.js';

const ids = [
  '10000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000002',
  '10000000-0000-4000-8000-000000000003',
] as const;

function segment(
  id: string,
  startSeconds: number,
  endSeconds: number,
): Segment {
  return { id, startSeconds, endSeconds, exportSelected: true };
}

function project(segments = [segment(ids[0], 1, 5)]): ProjectDocument {
  return {
    schemaVersion: 2,
    id: '20000000-0000-4000-8000-000000000001',
    source: {
      fileName: 'dance.mp4',
      durationSeconds: 20,
      width: 1920,
      height: 1080,
      frameRateNumerator: 25,
      frameRateDenominator: 1,
      frameRateReliability: 'reliable',
      hasAudio: true,
      inspectedAt: '2026-07-21T10:00:00.000Z',
      inspectorVersion: 'test',
    },
    settings: { pauseAfterCreation: false },
    playbackPositionSeconds: 0,
    selectedSegmentId: segments[0]?.id ?? null,
    segments,
    metadata: { title: null, tags: [], notes: null },
    editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
  };
}

describe('trim controller', () => {
  it('focuses Start and End for the selected segment', () => {
    const input = project();

    expect(focusBoundary(input, 'start')).toEqual({
      segmentId: ids[0],
      edge: 'start',
    });
    expect(focusBoundary(input, 'end')).toEqual({
      segmentId: ids[0],
      edge: 'end',
    });
  });

  it('uses reliable frames, approximate 30fps fallback, and Shift 0.1s', () => {
    const reliable = project();
    const approximate = {
      ...reliable,
      source: {
        ...reliable.source,
        frameRateNumerator: null,
        frameRateDenominator: null,
        frameRateReliability: 'approximate' as const,
      },
    };

    expect(boundaryStep(reliable, false)).toEqual({
      seconds: 0.04,
      approximate: false,
    });
    expect(boundaryStep(approximate, false)).toEqual({
      seconds: 1 / 30,
      approximate: true,
    });
    expect(boundaryStep(approximate, true)).toEqual({
      seconds: 0.1,
      approximate: false,
    });
  });

  it('clamps to source bounds and rejects crossing the other boundary', () => {
    const input = project();
    const start = focusBoundary(input, 'start');
    const end = focusBoundary(input, 'end');

    expect(nudgeBoundary(input, start, -5)).toMatchObject({
      ok: true,
      project: { segments: [{ startSeconds: 0, endSeconds: 5 }] },
    });
    expect(nudgeBoundary(input, end, 50)).toMatchObject({
      ok: true,
      project: { segments: [{ startSeconds: 1, endSeconds: 20 }] },
    });
    const invalid = nudgeBoundary(input, start, 5);
    expect(invalid).toMatchObject({ ok: false, code: 'invalid_range' });
    expect(invalid.project).toBe(input);
  });

  it('explains an outward nudge when the boundary is already source-clamped', () => {
    const input = project([segment(ids[0], 0, 20)]);

    const start = nudgeBoundary(input, focusBoundary(input, 'start'), -0.1);
    const end = nudgeBoundary(input, focusBoundary(input, 'end'), 0.1);

    expect(start).toMatchObject({ ok: false, code: 'outside_source' });
    expect(end).toMatchObject({ ok: false, code: 'outside_source' });
    expect(start.project).toBe(input);
    expect(end.project).toBe(input);
  });

  it('rejects triple overlap without mutating the project', () => {
    const input = project([
      segment(ids[0], 0, 4),
      segment(ids[1], 5, 9),
      segment(ids[2], 2, 6),
    ]);
    input.selectedSegmentId = ids[1];
    const result = nudgeBoundary(input, focusBoundary(input, 'start'), -2);

    expect(result).toMatchObject({ ok: false, code: 'triple_overlap' });
    expect(result.project).toBe(input);
  });

  it('clears focus before selection on consecutive Escape commands', () => {
    const input = project();
    const first = escapeEditing(input, focusBoundary(input, 'start'));
    const second = escapeEditing(first.project, first.focus);

    expect(first).toEqual({ project: input, focus: null });
    expect(second.focus).toBeNull();
    expect(second.project.selectedSegmentId).toBeNull();
  });

  it('finds previous and next segments in chronological order', () => {
    const input = project([
      segment(ids[2], 12, 14),
      segment(ids[0], 2, 4),
      segment(ids[1], 7, 9),
    ]);
    input.selectedSegmentId = ids[1];

    expect(adjacentSegment(input, 'previous')?.id).toBe(ids[0]);
    expect(adjacentSegment(input, 'next')?.id).toBe(ids[2]);
  });
});
