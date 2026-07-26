import type { FragmentCatalogue } from '../domain/catalogue-model.js';
import type { Segment } from '../domain/editor-model.js';
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
    fragmentFor: vi.fn().mockReturnValue({ segment, index: 0 }),
    patchSegment: vi.fn(),
    removeSegment: vi.fn(),
    restoreSegment: vi.fn(),
    deleteManagedVideo: vi.fn().mockResolvedValue(undefined),
  };
}

function jobs(): JobRetryPort {
  return { retryingJobId: null, retryJobById: vi.fn() };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, reject, resolve };
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
      undoToken: 'undo-token',
      undoUntil: new Date(Date.now() + 60_000).toISOString(),
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

  it('uses the fragment revision produced by the flush for focused mutation', async () => {
    const apiClient = api();
    const workspacePort = workspace();
    let revision = 1;
    vi.mocked(workspacePort.flushProject).mockImplementation(async () => {
      revision = 8;
    });
    vi.mocked(workspacePort.fragmentFor).mockImplementation(() => ({
      segment: { ...segment, revision },
      index: 0,
    }));
    const library = new FragmentLibrary(apiClient, workspacePort, jobs());
    await library.refresh();
    const mutation = {
      startSeconds: 3,
      endSeconds: 7,
      exportSelected: true,
      title: 'current revision',
      tagIds: [],
    };
    await library.mutateFragment(projectId, fragmentId, mutation);
    expect(apiClient.updateFragment).toHaveBeenCalledWith(
      projectId,
      fragmentId,
      mutation,
      8,
    );
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
    expect(library.deletedFragment).toBeNull();
  });

  it('deletes the post-flush editor revision through the soft-delete API', async () => {
    const apiClient = api();
    const workspacePort = workspace();
    const saved = { ...segment, revision: 9 };
    vi.mocked(workspacePort.fragmentFor).mockReturnValue({
      segment: saved,
      index: 0,
    });
    const library = new FragmentLibrary(apiClient, workspacePort, jobs());
    await library.refresh();
    await library.removeFragment(projectId, fragmentId);
    expect(workspacePort.flushProject).toHaveBeenCalledWith(projectId);
    expect(apiClient.deleteFragment).toHaveBeenCalledWith(projectId, saved, 0);
    expect(workspacePort.removeSegment).toHaveBeenCalledWith(
      projectId,
      fragmentId,
    );
    expect(library.deletedFragment?.undoToken).toBe('undo-token');
    library.dispose();
  });

  it('drops expired Undo state and refreshes authoritative fragments', async () => {
    const apiClient = api();
    vi.mocked(apiClient.restoreFragment).mockRejectedValue(
      Object.assign(new Error('expired'), {
        code: 'fragment_restore_expired',
      }),
    );
    const library = new FragmentLibrary(apiClient, workspace(), jobs());
    await library.refresh();
    const deleted = await library.removeFragment(projectId, fragmentId);
    await expect(library.restoreDeletedFragment(deleted)).rejects.toThrow(
      'expired',
    );
    expect(library.deletedFragment).toBeNull();
    expect(apiClient.loadFragments).toHaveBeenCalledTimes(2);
  });

  it('deduplicates tags by id', async () => {
    const apiClient = api();
    const library = new FragmentLibrary(apiClient, workspace(), jobs());
    await library.createTag('dance');
    await library.createTag('dance');
    expect(library.tags).toHaveLength(1);
  });

  it('ignores an older refresh that settles after a newer one', async () => {
    const first = deferred<FragmentCatalogue>();
    const second = deferred<FragmentCatalogue>();
    const apiClient = api();
    vi.mocked(apiClient.loadFragments)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const library = new FragmentLibrary(apiClient, workspace(), jobs());
    const older = library.refresh();
    const newer = library.refresh();
    second.resolve(catalogue({ ...segment, title: 'new' }));
    await newer;
    first.reject(new Error('old failure'));
    await older;
    expect(library.catalogue?.fragments[0]?.segment.title).toBe('new');
    expect(library.error).toBeNull();
    expect(library.loading).toBe(false);
  });

  it('ignores refresh results after disposal', async () => {
    const pending = deferred<FragmentCatalogue>();
    const apiClient = api();
    vi.mocked(apiClient.loadFragments).mockReturnValueOnce(pending.promise);
    const library = new FragmentLibrary(apiClient, workspace(), jobs());
    const refresh = library.refresh();
    library.dispose();
    pending.resolve(catalogue());
    await refresh;
    expect(library.catalogue).toBeNull();
  });

  it('polls while fragment previews are being generated', async () => {
    vi.useFakeTimers();
    try {
      const apiClient = api();
      vi.mocked(apiClient.loadFragments)
        .mockResolvedValueOnce({
          ...catalogue(),
          fragments: [
            { ...catalogue().fragments[0]!, thumbnailState: 'generating' },
          ],
        })
        .mockResolvedValueOnce(catalogue());
      const library = new FragmentLibrary(apiClient, workspace(), jobs());
      await library.refresh();
      await vi.advanceTimersByTimeAsync(1_000);
      expect(apiClient.loadFragments).toHaveBeenCalledTimes(2);
      library.dispose();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not poll after preview generation reaches failed', async () => {
    vi.useFakeTimers();
    try {
      const apiClient = api();
      vi.mocked(apiClient.loadFragments).mockResolvedValue({
        ...catalogue(),
        fragments: [{ ...catalogue().fragments[0]!, thumbnailState: 'failed' }],
      });
      const library = new FragmentLibrary(apiClient, workspace(), jobs());
      await library.refresh();
      await vi.advanceTimersByTimeAsync(5_000);
      expect(apiClient.loadFragments).toHaveBeenCalledTimes(1);
      library.dispose();
    } finally {
      vi.useRealTimers();
    }
  });
});
