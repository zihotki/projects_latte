import type { ProjectDocument, Segment } from './editor-model.js';

export type EditorOperation =
  | { kind: 'playbackPositionRecorded'; seconds: number }
  | { kind: 'timelineViewportChanged'; zoom: number; offsetSeconds: number }
  | { kind: 'fragmentSelected'; fragmentId: string | null }
  | { kind: 'fragmentCreated'; fragment: Segment }
  | { kind: 'fragmentBoundaryAdjusted'; fragment: Segment }
  | { kind: 'fragmentExportChanged'; fragmentId: string; selected: boolean }
  | {
      kind: 'fragmentMetadataChanged';
      fragmentId: string;
      title: string | null;
      tagIds: string[];
      exportSelected: boolean;
    }
  | { kind: 'pauseAfterCreationChanged'; enabled: boolean };

export function applyEditorOperation(
  project: ProjectDocument,
  operation: EditorOperation,
): ProjectDocument {
  switch (operation.kind) {
    case 'playbackPositionRecorded':
      return Math.abs(project.playbackPositionSeconds - operation.seconds) <
        0.01
        ? project
        : { ...project, playbackPositionSeconds: operation.seconds };
    case 'timelineViewportChanged':
      return Math.abs(project.editor.timelineZoom - operation.zoom) <
        0.000_001 &&
        Math.abs(
          project.editor.timelineOffsetSeconds - operation.offsetSeconds,
        ) < 0.000_001
        ? project
        : {
            ...project,
            editor: {
              timelineZoom: operation.zoom,
              timelineOffsetSeconds: operation.offsetSeconds,
            },
          };
    case 'fragmentSelected':
      if (
        operation.fragmentId !== null &&
        !project.segments.some(({ id }) => id === operation.fragmentId)
      )
        return project;
      return project.selectedSegmentId === operation.fragmentId
        ? project
        : { ...project, selectedSegmentId: operation.fragmentId };
    case 'fragmentCreated':
      return project.segments.some(({ id }) => id === operation.fragment.id)
        ? project
        : { ...project, segments: [...project.segments, operation.fragment] };
    case 'fragmentBoundaryAdjusted':
      return replaceFragment(project, operation.fragment.id, (current) =>
        current.startSeconds === operation.fragment.startSeconds &&
        current.endSeconds === operation.fragment.endSeconds
          ? current
          : operation.fragment,
      );
    case 'fragmentExportChanged':
      return replaceFragment(project, operation.fragmentId, (current) =>
        current.exportSelected === operation.selected
          ? current
          : { ...current, exportSelected: operation.selected },
      );
    case 'fragmentMetadataChanged':
      return replaceFragment(project, operation.fragmentId, (current) =>
        current.title === operation.title &&
        current.exportSelected === operation.exportSelected &&
        sameTags(current.tagIds, operation.tagIds)
          ? current
          : {
              ...current,
              title: operation.title,
              tagIds: operation.tagIds,
              exportSelected: operation.exportSelected,
            },
      );
    case 'pauseAfterCreationChanged':
      return project.settings.pauseAfterCreation === operation.enabled
        ? project
        : {
            ...project,
            settings: {
              ...project.settings,
              pauseAfterCreation: operation.enabled,
            },
          };
  }
}

function replaceFragment(
  project: ProjectDocument,
  fragmentId: string,
  change: (fragment: Segment) => Segment,
): ProjectDocument {
  let changed = false;
  const segments = project.segments.map((fragment) => {
    if (fragment.id !== fragmentId) return fragment;
    const next = change(fragment);
    changed = next !== fragment;
    return next;
  });
  return changed ? { ...project, segments } : project;
}

function sameTags(left: readonly string[], right: readonly string[]): boolean {
  return (
    left.length === right.length &&
    left.every((tag, index) => tag === right[index])
  );
}
