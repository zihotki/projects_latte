import type { Segment } from '../domain/editor-model.js';
import { describe, expect, it } from 'vitest';
import {
  segmentDurationStatus,
  validateSegmentMutation,
} from './segment-constraints.js';

function segment(
  id: string,
  startSeconds: number,
  endSeconds: number,
): Segment {
  return {
    id,
    startSeconds,
    endSeconds,
    exportSelected: true,
    title: null,
    tagIds: [],
  };
}

const firstId = '10000000-0000-4000-8000-000000000001';
const secondId = '10000000-0000-4000-8000-000000000002';
const thirdId = '10000000-0000-4000-8000-000000000003';

describe('segment constraints', () => {
  it.each([
    [segment(firstId, 4, 4), 'invalid_range'],
    [segment(firstId, 5, 4), 'invalid_range'],
    [segment(firstId, -1, 2), 'outside_source'],
    [segment(firstId, 9, 11), 'outside_source'],
  ] as const)('rejects invalid source range %#', (candidate, code) => {
    expect(validateSegmentMutation([], candidate, 10)).toMatchObject({
      ok: false,
      code,
    });
  });

  it('accepts two simultaneous segments and rejects a third', () => {
    const existing = [segment(firstId, 1, 5), segment(secondId, 3, 7)];

    expect(
      validateSegmentMutation(existing.slice(0, 1), existing[1]!, 10),
    ).toMatchObject({ ok: true });
    expect(
      validateSegmentMutation(existing, segment(thirdId, 4, 6), 10),
    ).toMatchObject({ ok: false, code: 'triple_overlap' });
  });

  it('accepts overlaps with neighbours that occur at different times', () => {
    const existing = [segment(firstId, 0, 4), segment(thirdId, 6, 10)];

    expect(
      validateSegmentMutation(existing, segment(secondId, 3, 7), 10),
    ).toMatchObject({ ok: true });
  });

  it('treats touching boundaries as non-overlapping and ignores the edited ID', () => {
    const existing = [segment(firstId, 0, 4), segment(secondId, 4, 8)];

    expect(
      validateSegmentMutation(existing, segment(thirdId, 8, 10), 10),
    ).toMatchObject({ ok: true });
    expect(
      validateSegmentMutation(existing, segment(firstId, 1, 5), 10, firstId),
    ).toMatchObject({ ok: true });
  });

  it.each([
    [2.999, 'short'],
    [3, 'expected'],
    [8, 'expected'],
    [8.001, 'long'],
  ] as const)('classifies duration %s as %s', (seconds, status) => {
    expect(segmentDurationStatus(seconds)).toBe(status);
  });
});
