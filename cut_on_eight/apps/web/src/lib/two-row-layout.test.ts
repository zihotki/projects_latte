import type { Segment } from '@cut-on-eight/contracts';
import { describe, expect, it } from 'vitest';
import { assignSegmentRows } from './two-row-layout.js';

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

describe('two-row segment layout', () => {
  it('assigns chronological rows independently of input order', () => {
    const chronological = [
      segment(firstId, 0, 4),
      segment(secondId, 3, 7),
      segment(thirdId, 6, 10),
    ];
    const expected = [
      { segment: chronological[0], row: 0 },
      { segment: chronological[1], row: 1 },
      { segment: chronological[2], row: 0 },
    ];

    expect(assignSegmentRows(chronological)).toEqual({
      ok: true,
      rows: expected,
    });
    expect(assignSegmentRows([...chronological].reverse())).toEqual({
      ok: true,
      rows: expected,
    });
  });

  it('rejects a third simultaneous segment', () => {
    expect(
      assignSegmentRows([
        segment(firstId, 0, 5),
        segment(secondId, 1, 6),
        segment(thirdId, 2, 7),
      ]),
    ).toMatchObject({ ok: false, code: 'triple_overlap' });
  });
});
