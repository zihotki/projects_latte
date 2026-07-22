import { describe, expect, it } from 'vitest';
import {
  resolveEditorKeyboardContext,
  shouldDelegateSegmentSurfaceActivation,
  shouldRouteEditorKeyboard,
} from './editor-keyboard-context.js';

const segmentId = '10000000-0000-4000-8000-000000000001';

describe('editor keyboard context', () => {
  it('uses source context without a selected segment', () => {
    expect(resolveEditorKeyboardContext(null, null)).toEqual({
      kind: 'source',
    });
  });

  it('uses the selected segment as the playback context', () => {
    expect(resolveEditorKeyboardContext(segmentId, null)).toEqual({
      kind: 'segment',
      segmentId,
    });
  });

  it('gives a focused boundary precedence over segment playback keys', () => {
    expect(
      resolveEditorKeyboardContext(segmentId, {
        segmentId,
        edge: 'end',
      }),
    ).toEqual({ kind: 'boundary', segmentId, edge: 'end' });
  });

  it('routes non-native keys while focus belongs to the editor', () => {
    expect(
      shouldRouteEditorKeyboard({
        focusWithinEditor: true,
        nativeButtonActivation: false,
        nativeInput: false,
      }),
    ).toBe(true);
  });

  it.each([
    {
      focusWithinEditor: false,
      nativeButtonActivation: false,
      nativeInput: false,
    },
    {
      focusWithinEditor: true,
      nativeButtonActivation: false,
      nativeInput: true,
    },
    {
      focusWithinEditor: true,
      nativeButtonActivation: true,
      nativeInput: false,
    },
  ])('does not steal native or out-of-editor keys', (input) => {
    expect(shouldRouteEditorKeyboard(input)).toBe(false);
  });

  it('delegates Space from the selected segment surface to playback', () => {
    expect(
      shouldDelegateSegmentSurfaceActivation({
        key: 'Space',
        focusedSegmentId: segmentId,
        selectedSegmentId: segmentId,
      }),
    ).toBe(true);
  });

  it.each([
    { key: 'Enter', focusedSegmentId: segmentId, selectedSegmentId: segmentId },
    { key: 'Space', focusedSegmentId: 'other', selectedSegmentId: segmentId },
    { key: 'Space', focusedSegmentId: null, selectedSegmentId: segmentId },
  ])('keeps native button activation for %o', (input) => {
    expect(shouldDelegateSegmentSurfaceActivation(input)).toBe(false);
  });
});
