import type { Segment } from '@cut-on-eight/contracts';

export type PlaybackScope =
  | { readonly kind: 'source'; readonly start: 0; readonly end: number }
  | {
      readonly kind: 'segment';
      readonly segmentId: string;
      readonly start: number;
      readonly end: number;
    };

export type PlaybackCommand =
  | { readonly kind: 'none' }
  | { readonly kind: 'pause-and-seek'; readonly seconds: number }
  | { readonly kind: 'seek-and-play'; readonly seconds: number }
  | { readonly kind: 'pause'; readonly error?: string };

export interface PlaybackState {
  readonly scope: PlaybackScope;
  readonly preview: { readonly start: number; readonly end: number } | null;
}

export interface PlaybackDecision {
  readonly state: PlaybackState;
  readonly command: PlaybackCommand;
}

const noCommand: PlaybackCommand = { kind: 'none' };

export function createPlaybackState(durationSeconds: number): PlaybackState {
  return {
    scope: { kind: 'source', start: 0, end: Math.max(0, durationSeconds) },
    preview: null,
  };
}

export function selectSegment(
  state: PlaybackState,
  segment: Segment,
): PlaybackDecision {
  return {
    state: {
      scope: {
        kind: 'segment',
        segmentId: segment.id,
        start: segment.startSeconds,
        end: segment.endSeconds,
      },
      preview: null,
    },
    command: { kind: 'pause-and-seek', seconds: segment.startSeconds },
  };
}

export function clearSelection(
  state: PlaybackState,
  durationSeconds: number,
  currentSeconds: number,
): PlaybackDecision {
  const next = createPlaybackState(durationSeconds);
  return {
    state: next,
    command: {
      kind: 'pause-and-seek',
      seconds: clamp(currentSeconds, next.scope.start, next.scope.end),
    },
  };
}

export function seekBy(
  state: PlaybackState,
  currentSeconds: number,
  deltaSeconds: number,
  playing: boolean,
): PlaybackDecision {
  const seconds = clamp(
    currentSeconds + deltaSeconds,
    state.scope.start,
    state.scope.end,
  );
  return {
    state: { ...state, preview: null },
    command: {
      kind: playing ? 'seek-and-play' : 'pause-and-seek',
      seconds,
    },
  };
}

export function beginContextPreview(
  state: PlaybackState,
  durationSeconds: number,
): PlaybackDecision {
  if (state.scope.kind !== 'segment') {
    return { state, command: noCommand };
  }

  const preview = {
    start: Math.max(0, state.scope.start - 1),
    end: Math.min(Math.max(0, durationSeconds), state.scope.end + 1),
  };
  return {
    state: { ...state, preview },
    command: { kind: 'seek-and-play', seconds: preview.start },
  };
}

export function onPlaybackTime(
  state: PlaybackState,
  currentSeconds: number,
  playing: boolean,
): PlaybackDecision {
  if (state.preview !== null) {
    return currentSeconds >= state.preview.end
      ? {
          state: { ...state, preview: null },
          command: { kind: 'pause-and-seek', seconds: state.scope.start },
        }
      : { state, command: noCommand };
  }

  if (state.scope.kind !== 'segment') {
    return { state, command: noCommand };
  }
  if (currentSeconds < state.scope.start) {
    return {
      state,
      command: {
        kind: playing ? 'seek-and-play' : 'pause-and-seek',
        seconds: state.scope.start,
      },
    };
  }
  if (currentSeconds >= state.scope.end) {
    return playing
      ? {
          state,
          command: { kind: 'seek-and-play', seconds: state.scope.start },
        }
      : {
          state,
          command: { kind: 'pause-and-seek', seconds: state.scope.end },
        };
  }
  return { state, command: noCommand };
}

export function playbackFailure(
  state: PlaybackState,
  error: string,
): PlaybackDecision {
  return {
    state: { ...state, preview: null },
    command: { kind: 'pause', error },
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  if (!Number.isFinite(value)) return minimum;
  return Math.min(maximum, Math.max(minimum, value));
}
