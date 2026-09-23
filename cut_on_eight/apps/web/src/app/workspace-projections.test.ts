import { describe, expect, it } from 'vitest';
import type {
  ProjectDocument,
  WorkspaceSnapshot,
} from '../domain/editor-model.js';
import { projectWorkspace } from './workspace-projections.js';

const project: ProjectDocument = {
  schemaVersion: 3,
  id: '10000000-0000-4000-8000-000000000001',
  source: {
    fileName: 'practice.mp4',
    durationSeconds: 20,
    width: 640,
    height: 360,
    frameRateNumerator: 30,
    frameRateDenominator: 1,
    frameRateReliability: 'reliable',
    hasAudio: true,
    inspectedAt: null,
    inspectorVersion: null,
  },
  playbackPositionSeconds: 0,
  selectedSegmentId: null,
  segments: [],
  settings: { pauseAfterCreation: false },
  metadata: { title: null, tags: [], notes: null },
  editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
};

describe('workspace projection', () => {
  it('shows a working copy without changing the server snapshot', () => {
    const server: WorkspaceSnapshot = {
      activeProjectId: project.id,
      openProjects: [project],
      library: [],
    };
    const workingCopy = {
      ...project,
      metadata: { ...project.metadata, title: 'Local edit' },
    };

    const visible = projectWorkspace(server, { [project.id]: workingCopy });

    expect(visible?.openProjects[0]?.metadata.title).toBe('Local edit');
    expect(server.openProjects[0]?.metadata.title).toBeNull();
  });
});
