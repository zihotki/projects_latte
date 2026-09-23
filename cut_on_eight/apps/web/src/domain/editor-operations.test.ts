import { describe, expect, it } from 'vitest';
import type { ProjectDocument, Segment } from './editor-model.js';
import { applyEditorOperation } from './editor-operations.js';

const fragment: Segment = {
  id: '20000000-0000-4000-8000-000000000001',
  startSeconds: 1,
  endSeconds: 3,
  title: null,
  tagIds: [],
  exportSelected: true,
};

function project(): ProjectDocument {
  return {
    schemaVersion: 3,
    id: '10000000-0000-4000-8000-000000000001',
    source: {
      fileName: 'practice.mp4',
      durationSeconds: 20,
      width: 640,
      height: 360,
      frameRateNumerator: 30,
      frameRateDenominator: 1,
      frameRateReliability: 'reliable',
      hasAudio: true,
      inspectedAt: null,
      inspectorVersion: null,
    },
    playbackPositionSeconds: 0,
    selectedSegmentId: null,
    segments: [fragment],
    settings: { pauseAfterCreation: false },
    metadata: { title: null, tags: [], notes: null },
    editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
  };
}

describe('editor operations', () => {
  it('selects only a fragment in the current video', () => {
    const current = project();
    expect(
      applyEditorOperation(current, {
        kind: 'fragmentSelected',
        fragmentId: fragment.id,
      }).selectedSegmentId,
    ).toBe(fragment.id);
    expect(
      applyEditorOperation(current, {
        kind: 'fragmentSelected',
        fragmentId: 'missing',
      }),
    ).toBe(current);
  });

  it('replaces one validated boundary without changing selection', () => {
    const current = project();
    const next = applyEditorOperation(current, {
      kind: 'fragmentBoundaryAdjusted',
      fragment: { ...fragment, endSeconds: 4 },
    });
    expect(next.segments).toEqual([{ ...fragment, endSeconds: 4 }]);
    expect(next.selectedSegmentId).toBeNull();
    expect(current.segments).toEqual([fragment]);
  });

  it('adds a fragment without selecting it', () => {
    const added = { ...fragment, id: '20000000-0000-4000-8000-000000000002' };
    const next = applyEditorOperation(project(), {
      kind: 'fragmentCreated',
      fragment: added,
    });
    expect(next.segments).toEqual([fragment, added]);
    expect(next.selectedSegmentId).toBeNull();
  });

  it('returns the same project for an unchanged value', () => {
    const current = project();
    expect(
      applyEditorOperation(current, {
        kind: 'pauseAfterCreationChanged',
        enabled: false,
      }),
    ).toBe(current);
  });
});
