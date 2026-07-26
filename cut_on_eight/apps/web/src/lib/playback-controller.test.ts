import type { Segment } from '@cut-on-eight/legacy-contracts';
import { describe, expect, it } from 'vitest';
import {
  beginContextPreview,
  clearSelection,
  createPlaybackState,
  onPlaybackTime,
  playbackFailure,
  seekBy,
  selectSegment,
} from './playback-controller.js';

const segment: Segment = {
  id: '10000000-0000-4000-8000-000000000001',
  startSeconds: 4,
  endSeconds: 8,
  exportSelected: true,
  title: null,
  tagIds: [],
};

describe('playback controller', () => {
  it('selects and seeks without autoplay', () => {
    const result = selectSegment(createPlaybackState(20), segment);

    expect(result.state.scope).toEqual({
      kind: 'segment',
      segmentId: segment.id,
      start: 4,
      end: 8,
    });
    expect(result.command).toEqual({ kind: 'pause-and-seek', seconds: 4 });
  });

  it.each([
    [4.5, -1, false, 4, 'pause-and-seek'],
    [7.5, 10, false, 8, 'pause-and-seek'],
    [5, -10, true, 4, 'seek-and-play'],
  ] as const)(
    'clamps scoped seeks from %s by %s',
    (current, delta, playing, seconds, kind) => {
      const selected = selectSegment(createPlaybackState(20), segment).state;

      expect(seekBy(selected, current, delta, playing).command).toEqual({
        kind,
        seconds,
      });
    },
  );

  it('loops the exact selected range while playing', () => {
    const selected = selectSegment(createPlaybackState(20), segment).state;

    expect(onPlaybackTime(selected, 8, true).command).toEqual({
      kind: 'seek-and-play',
      seconds: 4,
    });
  });

  it('clears selection into a paused source scope', () => {
    const selected = selectSegment(createPlaybackState(20), segment).state;
    const result = clearSelection(selected, 20, 7);

    expect(result.state).toEqual(createPlaybackState(20));
    expect(result.command).toEqual({ kind: 'pause-and-seek', seconds: 7 });
  });

  it.each([
    [{ ...segment, startSeconds: 0, endSeconds: 2 }, 0, 3],
    [{ ...segment, startSeconds: 18, endSeconds: 20 }, 17, 20],
  ] as const)('clamps contextual preview to the source', (clip, start, end) => {
    const selected = selectSegment(createPlaybackState(20), clip).state;
    const result = beginContextPreview(selected, 20);

    expect(result.state.preview).toEqual({ start, end });
    expect(result.command).toEqual({ kind: 'seek-and-play', seconds: start });
  });

  it('finishes preview in paused selected scope', () => {
    const selected = selectSegment(createPlaybackState(20), segment).state;
    const preview = beginContextPreview(selected, 20).state;
    const result = onPlaybackTime(preview, 9, true);

    expect(result.state.preview).toBeNull();
    expect(result.state.scope).toEqual(selected.scope);
    expect(result.command).toEqual({ kind: 'pause-and-seek', seconds: 4 });
  });

  it('turns adapter failures into visible pause decisions', () => {
    const state = beginContextPreview(
      selectSegment(createPlaybackState(20), segment).state,
      20,
    ).state;

    expect(playbackFailure(state, 'Could not seek')).toEqual({
      state: { ...state, preview: null },
      command: { kind: 'pause', error: 'Could not seek' },
    });
  });
});
