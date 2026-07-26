import type { Segment } from '../domain/editor-model.js';
import { v7 as uuidv7 } from 'uuid';
import {
  validateSegmentMutation,
  type SegmentConstraintCode,
} from './segment-constraints.js';

export type SegmentState = {
  segments: Segment[];
  selectedSegmentId: string | null;
};

type SegmentIdFactory = () => string;
export type UpdatedSegmentState<T extends SegmentState> = Omit<
  T,
  keyof SegmentState
> &
  SegmentState;

export type CreateSegmentResult<T extends SegmentState> =
  | { readonly ok: true; readonly state: UpdatedSegmentState<T> }
  | {
      readonly ok: false;
      readonly state: T;
      readonly code: SegmentConstraintCode;
      readonly message: string;
    };

export function createSegment<T extends SegmentState>(
  state: T,
  startSeconds: number | null,
  endSeconds: number,
  durationSeconds: number,
  createId: SegmentIdFactory = uuidv7,
): CreateSegmentResult<T> {
  if (startSeconds === null || endSeconds <= startSeconds) {
    return {
      ok: false,
      state,
      code: 'invalid_range',
      message: 'Segment end must be after its start.',
    };
  }

  const segment: Segment = {
    id: createId(),
    startSeconds,
    endSeconds,
    exportSelected: true,
    title: null,
    tagIds: [],
  };

  const validated = validateSegmentMutation(
    state.segments,
    segment,
    durationSeconds,
  );
  if (!validated.ok) return { ...validated, state };

  return {
    ok: true,
    state: {
      ...state,
      segments: [...state.segments, validated.segment],
      selectedSegmentId: state.selectedSegmentId,
    },
  };
}

export function fragmentForDeletionKey(
  state: SegmentState,
  key: 'Delete' | 'Backspace',
): Segment | null {
  if (key === 'Backspace') return state.segments.at(-1) ?? null;
  return (
    state.segments.find((segment) => segment.id === state.selectedSegmentId) ??
    null
  );
}

export function sortSegmentsByStart(segments: readonly Segment[]): Segment[] {
  return [...segments].sort(
    (left, right) =>
      left.startSeconds - right.startSeconds ||
      left.endSeconds - right.endSeconds ||
      left.id.localeCompare(right.id),
  );
}
