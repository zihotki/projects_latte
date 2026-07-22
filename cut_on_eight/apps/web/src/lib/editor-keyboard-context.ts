import type { BoundaryFocus } from './trim-controller.js';

export type EditorKeyboardContext =
  | { readonly kind: 'source' }
  | { readonly kind: 'segment'; readonly segmentId: string }
  | {
      readonly kind: 'boundary';
      readonly segmentId: string;
      readonly edge: 'start' | 'end';
    };

export interface EditorKeyboardRoutingInput {
  readonly focusWithinEditor: boolean;
  readonly nativeButtonActivation: boolean;
  readonly nativeInput: boolean;
}

export interface SegmentSurfaceActivationInput {
  readonly key: string;
  readonly focusedSegmentId: string | null;
  readonly selectedSegmentId: string | null;
}

export function resolveEditorKeyboardContext(
  selectedSegmentId: string | null,
  boundaryFocus: BoundaryFocus,
): EditorKeyboardContext {
  if (boundaryFocus !== null) {
    return {
      kind: 'boundary',
      segmentId: boundaryFocus.segmentId,
      edge: boundaryFocus.edge,
    };
  }
  return selectedSegmentId === null
    ? { kind: 'source' }
    : { kind: 'segment', segmentId: selectedSegmentId };
}

export function shouldRouteEditorKeyboard(
  input: EditorKeyboardRoutingInput,
): boolean {
  return (
    input.focusWithinEditor &&
    !input.nativeInput &&
    !input.nativeButtonActivation
  );
}

export function shouldDelegateSegmentSurfaceActivation(
  input: SegmentSurfaceActivationInput,
): boolean {
  return (
    input.key === 'Space' &&
    input.focusedSegmentId !== null &&
    input.focusedSegmentId === input.selectedSegmentId
  );
}
