export type FrameRateReliability = 'reliable' | 'approximate';

export interface FrameStep {
  readonly approximate: boolean;
  readonly seconds: number;
}

export interface Segment {
  id: string;
  startSeconds: number;
  endSeconds: number;
  exportSelected: boolean;
  title: string | null;
  description?: string | null;
  tagIds: string[];
  revision?: number;
}

export interface ProjectDocument {
  schemaVersion: 3;
  id: string;
  revision?: number;
  sourceHref?: string | null;
  source: {
    fileName: string;
    durationSeconds: number | null;
    width: number | null;
    height: number | null;
    frameRateNumerator: number | null;
    frameRateDenominator: number | null;
    frameRateReliability: FrameRateReliability;
    hasAudio: boolean | null;
    inspectedAt: string | null;
    inspectorVersion: string | null;
  };
  settings: { pauseAfterCreation: boolean };
  playbackPositionSeconds: number;
  selectedSegmentId: string | null;
  segments: Segment[];
  metadata: {
    title: string | null;
    tags: string[];
    notes: string | null;
  };
  editor: {
    timelineZoom: number;
    timelineOffsetSeconds: number;
  };
}

export interface ProjectSummary {
  id: string;
  fileName: string;
  durationSeconds: number | null;
  status?:
    'receiving' | 'queued' | 'processing' | 'ready' | 'failed' | 'deleting';
  revision?: number;
}

export interface WorkspaceSnapshot {
  activeProjectId: string | null;
  openProjects: ProjectDocument[];
  library: ProjectSummary[];
}

export function frameStepSeconds(source: ProjectDocument['source']): FrameStep {
  if (
    source.frameRateReliability === 'reliable' &&
    source.frameRateNumerator !== null &&
    source.frameRateDenominator !== null
  ) {
    return {
      approximate: false,
      seconds: source.frameRateDenominator / source.frameRateNumerator,
    };
  }
  return { approximate: true, seconds: 1 / 30 };
}
