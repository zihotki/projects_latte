import type { FragmentCatalogue, Segment } from '@cut-on-eight/contracts';
import { describe, expect, it, vi } from 'vitest';
import {
  FragmentLibrary,
  type FragmentApi,
  type JobRetryPort,
} from './fragment-library.svelte.js';
import type { WorkspacePort } from './workspace-session.svelte.js';

const projectId = '10000000-0000-4000-8000-000000000001';
const fragmentId = '20000000-0000-4000-8000-000000000001';

const segment: Segment = {
  id: fragmentId,
  startSeconds: 3,
  endSeconds: 7,
  exportSelected: true,
  title: null,
  tagIds: [],
};

function catalogue(value: Segment = segment): FragmentCatalogue {
  return {
    tags: [],
    diagnostics: [],
    fragments: [
      {
        projectId,
        sourceFileName: 'video.mp4',
        sourceDurationSeconds: 30,
        ordinal: 1,
        segment: value,
        previews: [],
        thumbnailState: 'unavailable',
        thumbnailJobId: null,
        frameStepSeconds: 1 / 30,
        frameStepApproximate: true,
      },
    ],
  };
}

function workspace(): WorkspacePort {
  return {
    hasOpenProject: vi.fn().mockReturnValue(true),
    flushProject: vi.fn().mockResolvedValue(undefined),
    patchSegment: vi.fn(),
    removeSegment: vi.fn(),
    restoreSegment: vi.fn(),
    deleteManagedVideo: vi.fn().mockResolvedValue(undefined),
  };
}

function jobs(): JobRetryPort {
  return { retryingJobId: null, retryJobById: vi.fn() };
}

function api(): FragmentApi {
  return {
    loadFragments: vi.fn().mockResolvedValue(catalogue()),
    loadTags: vi.fn().mockResolvedValue([]),
    createTag: vi.fn().mockResolvedValue({
      id: '30000000-0000-4000-8000-000000000001',
      name: 'dance',
    }),
    updateFragment: vi.fn().mockImplementation(async (_, __, mutation) => ({
      ...segment,
      ...mutation,
    })),
    deleteFragment: vi.fn().mockResolvedValue({
      projectId,
      index: 0,
      fragment: segment,
    }),
    restoreFragment: vi.fn().mockResolvedValue(segment),
  };
}

describe('FragmentLibrary', () => {
  it('refreshes the catalogue and shared tags', async () => {
    const library = new FragmentLibrary(api(), workspace(), jobs());
    await library.refresh();
    expect(library.catalogue?.fragments).toHaveLength(1);
    expect(library.loading).toBe(false);
  });

  it('flushes and patches an open project after mutation', async () => {
    const workspacePort = workspace();
    const library = new FragmentLibrary(api(), workspacePort, jobs());
    await library.refresh();
    const updated = await library.mutateFragment(projectId, fragmentId, {
      startSeconds: 3,
      endSeconds: 7,
      exportSelected: true,
      title: 'final',
      tagIds: [],
    });
    expect(workspacePort.flushProject).toHaveBeenCalledWith(projectId);
    expect(workspacePort.patchSegment).toHaveBeenCalledWith(projectId, updated);
    expect(library.catalogue?.fragments[0]?.segment.title).toBe('final');
  });

  it('removes and restores through the workspace port', async () => {
    const workspacePort = workspace();
    const library = new FragmentLibrary(api(), workspacePort, jobs());
    await library.refresh();
    const deleted = await library.removeFragment(projectId, fragmentId);
    expect(workspacePort.removeSegment).toHaveBeenCalledWith(
      projectId,
      fragmentId,
    );
    await library.restoreDeletedFragment(deleted);
    expect(workspacePort.restoreSegment).toHaveBeenCalledWith(
      projectId,
      segment,
      0,
    );
  });

  it('deduplicates tags by id', async () => {
    const apiClient = api();
    const library = new FragmentLibrary(apiClient, workspace(), jobs());
    await library.createTag('dance');
    await library.createTag('dance');
    expect(library.tags).toHaveLength(1);
  });
});
