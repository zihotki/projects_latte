import {
  type EditorSaveRequest,
  type EditorVideoDto,
  type WorkspaceDto,
} from '@cut-on-eight/api-contracts';
import type { ProjectDocument, WorkspaceSnapshot } from './editor-model.js';

const US_PER_SECOND = 1_000_000;

export const toSeconds = (microseconds: number): number =>
  microseconds / US_PER_SECOND;

export const toMicroseconds = (seconds: number): number => {
  const value = Math.round(seconds * US_PER_SECOND);
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error('Editor timing is outside the supported range');
  }
  return value;
};

export function toProjectDocument(dto: EditorVideoDto): ProjectDocument {
  return {
    schemaVersion: 3,
    id: dto.video.id,
    revision: dto.video.revision,
    sourceHref: dto.source?.href ?? null,
    source: {
      fileName: dto.video.originalFileName,
      durationSeconds:
        dto.video.durationUs === null ? null : toSeconds(dto.video.durationUs),
      width: dto.video.width,
      height: dto.video.height,
      frameRateNumerator: dto.video.frameRateNumerator,
      frameRateDenominator: dto.video.frameRateDenominator,
      frameRateReliability: dto.video.frameRateReliability,
      hasAudio: dto.video.hasAudio,
      inspectedAt: null,
      inspectorVersion: null,
    },
    settings: { pauseAfterCreation: dto.editor.pauseAfterCreation },
    playbackPositionSeconds: toSeconds(dto.playbackPositionUs),
    selectedSegmentId: dto.editor.selectedFragmentId,
    segments: dto.fragments.map((fragment) => ({
      id: fragment.id,
      startSeconds: toSeconds(fragment.startUs),
      endSeconds: toSeconds(fragment.endUs),
      exportSelected: fragment.exportSelected,
      title: fragment.title,
      description: fragment.description,
      tagIds: fragment.tags.map(({ id }) => id),
      revision: fragment.revision,
    })),
    metadata: {
      title: dto.video.title,
      tags: dto.video.tags.map(({ id }) => id),
      notes: dto.video.description,
    },
    editor: {
      timelineZoom: dto.editor.timelineZoom,
      timelineOffsetSeconds: toSeconds(dto.editor.timelineOffsetUs),
    },
  };
}

export function toEditorSaveRequest(
  project: ProjectDocument,
): EditorSaveRequest {
  return {
    expectedVideoRevision: project.revision ?? 0,
    title: project.metadata.title?.trim() || project.source.fileName,
    description: project.metadata.notes?.trim() || null,
    tagIds: project.metadata.tags,
    playbackPositionUs: toMicroseconds(project.playbackPositionSeconds),
    editor: {
      selectedFragmentId: project.selectedSegmentId,
      pauseAfterCreation: project.settings.pauseAfterCreation,
      timelineZoom: project.editor.timelineZoom,
      timelineOffsetUs: toMicroseconds(project.editor.timelineOffsetSeconds),
    },
    fragments: project.segments.map((segment) => ({
      id: segment.id,
      expectedRevision: segment.revision ?? null,
      startUs: toMicroseconds(segment.startSeconds),
      endUs: toMicroseconds(segment.endSeconds),
      title: segment.title,
      description: segment.description ?? null,
      exportSelected: segment.exportSelected,
      tagIds: segment.tagIds,
    })),
  };
}

export function toWorkspaceSnapshot(dto: WorkspaceDto): WorkspaceSnapshot {
  return {
    activeProjectId: dto.activeVideoId,
    openProjects: dto.openVideos.map(toProjectDocument),
    library: dto.library.map((video) => ({
      id: video.id,
      fileName: video.originalFileName,
      durationSeconds:
        video.durationUs === null ? null : toSeconds(video.durationUs),
      status: video.status,
      revision: video.revision,
    })),
  };
}
