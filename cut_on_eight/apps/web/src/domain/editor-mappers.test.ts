import { describe, expect, test } from 'vitest';
import {
  toEditorSaveRequest,
  toMicroseconds,
  toSeconds,
} from './editor-mappers.js';

describe('editor timing mappers', () => {
  test('round-trips non-integer media time at microsecond precision', () => {
    const value = 1.234567;
    expect(toSeconds(toMicroseconds(value))).toBe(value);
  });

  test('preserves revisions and tag IDs in saves', () => {
    const request = toEditorSaveRequest({
      schemaVersion: 3,
      id: '10000000-0000-4000-8000-000000000001',
      revision: 4,
      sourceHref: '/api/assets/source',
      source: {
        fileName: 'demo.mp4',
        durationSeconds: 10,
        width: 320,
        height: 180,
        frameRateNumerator: 30,
        frameRateDenominator: 1,
        frameRateReliability: 'reliable',
        hasAudio: true,
        inspectedAt: null,
        inspectorVersion: null,
      },
      settings: { pauseAfterCreation: false },
      playbackPositionSeconds: 2,
      selectedSegmentId: null,
      segments: [
        {
          id: '20000000-0000-4000-8000-000000000001',
          startSeconds: 1,
          endSeconds: 3,
          exportSelected: true,
          title: 'beat',
          tagIds: ['30000000-0000-4000-8000-000000000001'],
          revision: 2,
        },
      ],
      metadata: { title: 'Demo', tags: [], notes: null },
      editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
    });
    expect(request.expectedVideoRevision).toBe(4);
    expect(request.fragments[0]?.expectedRevision).toBe(2);
    expect(request.fragments[0]?.tagIds).toEqual([
      '30000000-0000-4000-8000-000000000001',
    ]);
  });
});
