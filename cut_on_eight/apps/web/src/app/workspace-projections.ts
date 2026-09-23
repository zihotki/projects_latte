import type {
  ProjectDocument,
  WorkspaceSnapshot,
} from '../domain/editor-model.js';

export function projectWorkspace(
  server: WorkspaceSnapshot | null,
  drafts: Readonly<Record<string, ProjectDocument>>,
): WorkspaceSnapshot | null {
  if (server === null) return null;
  if (Object.keys(drafts).length === 0) return server;
  return {
    ...server,
    openProjects: server.openProjects.map(
      (project) => drafts[project.id] ?? project,
    ),
  };
}

export function mergeUnsavedEditor(
  local: ProjectDocument,
  authoritative: ProjectDocument,
): ProjectDocument {
  const remoteSegments = new Map(
    authoritative.segments.map((segment) => [segment.id, segment]),
  );
  return {
    ...authoritative,
    revision: Math.max(authoritative.revision ?? 0, local.revision ?? 0),
    playbackPositionSeconds: local.playbackPositionSeconds,
    selectedSegmentId: local.selectedSegmentId,
    settings: local.settings,
    metadata: local.metadata,
    editor: local.editor,
    segments: local.segments.map((segment) => {
      const remote = remoteSegments.get(segment.id);
      return remote === undefined
        ? segment
        : {
            ...segment,
            revision: Math.max(remote.revision ?? 0, segment.revision ?? 0),
          };
    }),
  };
}
