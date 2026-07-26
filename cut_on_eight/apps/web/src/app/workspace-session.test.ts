import type {
  ProjectDocument,
  WorkspaceSnapshot,
} from '../domain/editor-model.js';
import { describe, expect, it, vi } from 'vitest';
import {
  WorkspaceSession,
  type WorkspaceApi,
} from './workspace-session.svelte.js';

const projectId = '10000000-0000-4000-8000-000000000001';

function project(): ProjectDocument {
  return {
    schemaVersion: 3,
    id: projectId,
    source: {
      fileName: 'video.mp4',
      durationSeconds: 100,
      width: 1920,
      height: 1080,
      frameRateNumerator: 30,
      frameRateDenominator: 1,
      frameRateReliability: 'reliable',
      hasAudio: true,
      inspectedAt: '2026-01-01T00:00:00.000Z',
      inspectorVersion: 'test',
    },
    playbackPositionSeconds: 3,
    selectedSegmentId: null,
    segments: [],
    settings: { pauseAfterCreation: false },
    metadata: { title: null, tags: [], notes: null },
    editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
  };
}

function snapshot(): WorkspaceSnapshot {
  return { activeProjectId: projectId, openProjects: [project()], library: [] };
}

function api(): WorkspaceApi {
  const current = snapshot();
  return {
    loadWorkspace: vi.fn().mockResolvedValue(current),
    selectImport: vi.fn().mockResolvedValue({
      outcome: 'cancelled',
      workspace: current,
    }),
    openProject: vi.fn().mockResolvedValue(current),
    activateProject: vi.fn().mockResolvedValue(current),
    saveProject: vi.fn().mockImplementation(async (value) => value),
    closeProject: vi.fn().mockResolvedValue(current),
    deleteProject: vi.fn().mockResolvedValue(current),
  };
}

describe('WorkspaceSession', () => {
  it('initializes and exposes the active project', async () => {
    const session = new WorkspaceSession(api());
    await session.initialize();
    expect(session.activeProject?.id).toBe(projectId);
    expect(session.loading).toBe(false);
  });

  it('preserves a sampled playback position in later edits', () => {
    const session = new WorkspaceSession(api());
    session.applyWorkspace(snapshot(), false);
    session.samplePlaybackPosition(projectId, 42.5);
    session.updateProject(projectId, (current) => ({
      ...current,
      selectedSegmentId: '20000000-0000-4000-8000-000000000001',
    }));
    expect(session.documentFor(projectId).playbackPositionSeconds).toBe(42.5);
    expect(session.saveStateFor(projectId)).toBe('unsaved');
  });

  it('patches open-project segments through the narrow port', () => {
    const session = new WorkspaceSession(api());
    session.applyWorkspace(snapshot(), false);
    const segment = {
      id: '20000000-0000-4000-8000-000000000001',
      startSeconds: 1,
      endSeconds: 5,
      title: 'clip',
      tagIds: [],
      exportSelected: true,
    };
    session.restoreSegment(projectId, segment, 0);
    expect(session.activeProject?.segments).toEqual([segment]);
    session.removeSegment(projectId, segment.id);
    expect(session.activeProject?.segments).toEqual([]);
  });

  it('deletes a closed video using the library revision', async () => {
    const apiClient = api();
    const session = new WorkspaceSession(apiClient);
    session.applyWorkspace(
      {
        activeProjectId: null,
        openProjects: [],
        library: [
          {
            id: projectId,
            fileName: 'video.mp4',
            durationSeconds: 100,
            revision: 7,
          },
        ],
      },
      false,
    );
    await session.deleteManagedVideo(projectId);
    expect(apiClient.deleteProject).toHaveBeenCalledWith(projectId, 7);
  });

  it('cancels late workspace writes after disposal', () => {
    const session = new WorkspaceSession(api());
    session.dispose();
    session.applyWorkspace(snapshot());
    expect(session.workspace).toBeNull();
  });
});
