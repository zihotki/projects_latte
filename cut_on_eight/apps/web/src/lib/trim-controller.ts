import {
  frameStepSeconds,
  type FrameStep,
  type ProjectDocument,
  type Segment,
} from '@cut-on-eight/contracts';
import {
  validateSegmentMutation,
  type SegmentConstraintCode,
} from './segment-constraints.js';
import { sortSegmentsByStart } from './segments.js';

export type BoundaryFocus = {
  readonly segmentId: string;
  readonly edge: 'start' | 'end';
} | null;

export type TrimResult =
  | {
      readonly ok: true;
      readonly project: ProjectDocument;
      readonly focus: Exclude<BoundaryFocus, null>;
    }
  | {
      readonly ok: false;
      readonly project: ProjectDocument;
      readonly focus: BoundaryFocus;
      readonly code: SegmentConstraintCode;
      readonly message: string;
    };

export function focusBoundary(
  project: ProjectDocument,
  edge: 'start' | 'end',
): BoundaryFocus {
  return project.selectedSegmentId === null
    ? null
    : { segmentId: project.selectedSegmentId, edge };
}

export function boundaryStep(
  project: ProjectDocument,
  coarse: boolean,
): FrameStep {
  return coarse
    ? { seconds: 0.1, approximate: false }
    : frameStepSeconds(project.source);
}

export function nudgeBoundary(
  project: ProjectDocument,
  focus: BoundaryFocus,
  deltaSeconds: number,
): TrimResult {
  if (focus === null || !Number.isFinite(deltaSeconds)) {
    return failure(
      project,
      focus,
      'invalid_range',
      'Select a segment boundary before adjusting it.',
    );
  }

  const durationSeconds = project.source.durationSeconds;
  const segment = project.segments.find(
    (candidate) => candidate.id === focus.segmentId,
  );
  if (durationSeconds === null || segment === undefined) {
    return failure(
      project,
      focus,
      'outside_source',
      'The source duration is unavailable.',
    );
  }

  const nextSeconds =
    focus.edge === 'start'
      ? Math.max(0, segment.startSeconds + deltaSeconds)
      : Math.min(durationSeconds, segment.endSeconds + deltaSeconds);
  const currentSeconds =
    focus.edge === 'start' ? segment.startSeconds : segment.endSeconds;
  if (nextSeconds === currentSeconds && deltaSeconds !== 0) {
    return failure(
      project,
      focus,
      'outside_source',
      'The boundary is already at the source limit.',
    );
  }
  const candidate: Segment = {
    ...segment,
    [focus.edge === 'start' ? 'startSeconds' : 'endSeconds']: nextSeconds,
  };
  const validated = validateSegmentMutation(
    project.segments,
    candidate,
    durationSeconds,
    segment.id,
  );
  if (!validated.ok) {
    return failure(project, focus, validated.code, validated.message);
  }

  return {
    ok: true,
    focus,
    project: {
      ...project,
      segments: project.segments.map((existing) =>
        existing.id === segment.id ? validated.segment : existing,
      ),
    },
  };
}

export function escapeEditing(
  project: ProjectDocument,
  focus: BoundaryFocus,
): { readonly project: ProjectDocument; readonly focus: BoundaryFocus } {
  if (focus !== null) return { project, focus: null };
  return project.selectedSegmentId === null
    ? { project, focus }
    : { project: { ...project, selectedSegmentId: null }, focus };
}

export function adjacentSegment(
  project: ProjectDocument,
  direction: 'previous' | 'next',
): Segment | null {
  if (project.selectedSegmentId === null) return null;

  const segments = sortSegmentsByStart(project.segments);
  const currentIndex = segments.findIndex(
    (segment) => segment.id === project.selectedSegmentId,
  );
  const offset = direction === 'previous' ? -1 : 1;
  return segments[currentIndex + offset] ?? null;
}

function failure(
  project: ProjectDocument,
  focus: BoundaryFocus,
  code: SegmentConstraintCode,
  message: string,
): TrimResult {
  return { ok: false, project, focus, code, message };
}
