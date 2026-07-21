import type { Segment } from '@cut-on-eight/contracts';

export type SegmentState = {
  segments: Segment[];
  selectedSegmentId: string | null;
};

type SegmentIdFactory = () => string;
type UpdatedSegmentState<T extends SegmentState> = Omit<T, keyof SegmentState> &
  SegmentState;

export function createSegment<T extends SegmentState>(
  state: T,
  startSeconds: number | null,
  endSeconds: number,
  createId: SegmentIdFactory = () => crypto.randomUUID(),
): UpdatedSegmentState<T> {
  if (startSeconds === null || endSeconds <= startSeconds) {
    return state;
  }

  const segment: Segment = {
    id: createId(),
    startSeconds,
    endSeconds,
    exportSelected: true,
  };

  return {
    ...state,
    segments: [...state.segments, segment],
    selectedSegmentId: segment.id,
  };
}

export function deleteSelectedSegment<T extends SegmentState>(
  state: T,
): UpdatedSegmentState<T> {
  if (
    state.selectedSegmentId === null ||
    !state.segments.some((segment) => segment.id === state.selectedSegmentId)
  ) {
    return state;
  }

  return {
    ...state,
    segments: state.segments.filter(
      (segment) => segment.id !== state.selectedSegmentId,
    ),
    selectedSegmentId: null,
  };
}

export function deleteMostRecentSegment<T extends SegmentState>(
  state: T,
): UpdatedSegmentState<T> {
  const mostRecentSegment = state.segments.at(-1);
  if (mostRecentSegment === undefined) {
    return state;
  }

  return {
    ...state,
    segments: state.segments.slice(0, -1),
    selectedSegmentId:
      state.selectedSegmentId === mostRecentSegment.id
        ? null
        : state.selectedSegmentId,
  };
}

export function sortSegmentsByStart(segments: readonly Segment[]): Segment[] {
  return [...segments].sort(
    (left, right) =>
      left.startSeconds - right.startSeconds ||
      left.endSeconds - right.endSeconds ||
      left.id.localeCompare(right.id),
  );
}
