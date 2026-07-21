import type { Segment } from '@cut-on-eight/contracts';
import { sortSegmentsByStart } from './segments.js';

export type SegmentRow = {
  readonly row: 0 | 1;
  readonly segment: Segment;
};

export type SegmentRowResult =
  | { readonly ok: true; readonly rows: SegmentRow[] }
  | {
      readonly ok: false;
      readonly code: 'triple_overlap';
      readonly message: string;
    };

export function assignSegmentRows(
  segments: readonly Segment[],
): SegmentRowResult {
  const rowEndSeconds = [-Infinity, -Infinity];
  const rows: SegmentRow[] = [];

  for (const segment of sortSegmentsByStart(segments)) {
    const availableRow = rowEndSeconds.findIndex(
      (endSeconds) => endSeconds <= segment.startSeconds,
    );
    if (availableRow === -1) {
      return {
        ok: false,
        code: 'triple_overlap',
        message: 'At most two segments can overlap.',
      };
    }

    const row = availableRow as 0 | 1;
    rowEndSeconds[row] = segment.endSeconds;
    rows.push({ segment, row });
  }

  return { ok: true, rows };
}
