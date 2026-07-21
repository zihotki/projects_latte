import type { Segment } from '@cut-on-eight/contracts';

export type SegmentConstraintCode =
  'invalid_range' | 'outside_source' | 'triple_overlap';

export type SegmentMutationResult =
  | { readonly ok: true; readonly segment: Segment }
  | {
      readonly ok: false;
      readonly code: SegmentConstraintCode;
      readonly message: string;
    };

type Event = { readonly delta: -1 | 1; readonly seconds: number };

export function validateSegmentMutation(
  segments: readonly Segment[],
  candidate: Segment,
  durationSeconds: number,
  ignoredId?: string,
): SegmentMutationResult {
  if (
    !Number.isFinite(candidate.startSeconds) ||
    !Number.isFinite(candidate.endSeconds) ||
    candidate.endSeconds <= candidate.startSeconds
  ) {
    return {
      ok: false,
      code: 'invalid_range',
      message: 'Segment end must be after its start.',
    };
  }

  if (
    !Number.isFinite(durationSeconds) ||
    durationSeconds <= 0 ||
    candidate.startSeconds < 0 ||
    candidate.endSeconds > durationSeconds
  ) {
    return {
      ok: false,
      code: 'outside_source',
      message: 'Segment must stay within the source video.',
    };
  }

  const considered = [
    ...segments.filter((segment) => segment.id !== ignoredId),
    candidate,
  ];
  const events: Event[] = considered.flatMap((segment) => [
    { seconds: segment.startSeconds, delta: 1 as const },
    { seconds: segment.endSeconds, delta: -1 as const },
  ]);
  events.sort(
    (left, right) => left.seconds - right.seconds || left.delta - right.delta,
  );

  let depth = 0;
  for (const event of events) {
    depth += event.delta;
    if (depth > 2) {
      return {
        ok: false,
        code: 'triple_overlap',
        message: 'At most two segments can overlap.',
      };
    }
  }

  return { ok: true, segment: candidate };
}

export function segmentDurationStatus(
  durationSeconds: number,
): 'short' | 'expected' | 'long' {
  if (durationSeconds < 3) return 'short';
  if (durationSeconds > 8) return 'long';
  return 'expected';
}
