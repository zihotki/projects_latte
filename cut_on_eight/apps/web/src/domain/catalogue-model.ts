import type { Segment } from './editor-model.js';

export interface TagDefinition {
  readonly id: string;
  readonly name: string;
}

export interface FragmentMutation {
  readonly startSeconds: number;
  readonly endSeconds: number;
  readonly exportSelected: boolean;
  readonly title: string | null;
  readonly description?: string | null;
  readonly tagIds: string[];
}

export interface FragmentPreview {
  readonly href?: string;
  readonly sampleSeconds: number;
  readonly pageFileName: string;
  readonly pageWidth: number;
  readonly pageHeight: number;
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
  readonly identity: string;
}

export interface FragmentSummary {
  readonly projectId: string;
  readonly sourceFileName: string;
  readonly sourceHref?: string;
  readonly sourceDurationSeconds: number | null;
  readonly ordinal: number;
  readonly segment: Segment;
  readonly previews: FragmentPreview[];
  readonly thumbnailState: 'ready' | 'generating' | 'failed' | 'unavailable';
  readonly thumbnailJobId: string | null;
  readonly frameStepSeconds: number;
  readonly frameStepApproximate: boolean;
}

export interface FragmentCatalogue {
  readonly fragments: FragmentSummary[];
  readonly tags: TagDefinition[];
  readonly diagnostics: {
    projectId: string;
    sourceFileName: string;
    message: string;
  }[];
}

export interface DeletedFragment {
  readonly projectId: string;
  readonly index: number;
  readonly fragment: Segment;
  readonly undoToken: string;
  readonly undoUntil: string;
}
