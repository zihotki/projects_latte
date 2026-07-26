import type { WorkspaceSnapshot } from '@cut-on-eight/legacy-contracts';
import { describe, expect, it, vi } from 'vitest';
import { AppModel } from './app-model.svelte.js';
import { BackgroundProcessing } from './background-processing.svelte.js';
import { FragmentLibrary } from './fragment-library.svelte.js';
import { UiPreferences } from './ui-preferences.svelte.js';
import { WorkspaceSession } from './workspace-session.svelte.js';

const emptyWorkspace: WorkspaceSnapshot = {
  activeProjectId: null,
  openProjects: [],
  library: [],
};

function createModel(
  options: {
    initialView?: string;
    loadWorkspace?: () => Promise<WorkspaceSnapshot>;
  } = {},
) {
  const workspace = new WorkspaceSession({
    loadWorkspace:
      options.loadWorkspace ?? vi.fn().mockResolvedValue(emptyWorkspace),
    selectImport: vi.fn(),
    openProject: vi.fn(),
    activateProject: vi.fn(),
    saveProject: vi.fn(),
    closeProject: vi.fn(),
    deleteProject: vi.fn(),
  });
  const close = vi.fn();
  const connectJobEvents = vi.fn().mockReturnValue(close);
  const background = new BackgroundProcessing(
    {
      loadCapabilities: vi.fn().mockResolvedValue({
        backendAvailable: true,
        ffprobeAvailable: true,
      }),
      loadThumbnailManifest: vi.fn(),
      retryJob: vi.fn(),
      connectJobEvents,
    },
    () => workspace.workspace?.activeProjectId ?? null,
  );
  const loadFragments = vi.fn().mockResolvedValue({
    fragments: [],
    tags: [],
    diagnostics: [],
  });
  const loadTags = vi.fn().mockResolvedValue([]);
  const fragments = new FragmentLibrary(
    {
      loadFragments,
      loadTags,
      createTag: vi.fn(),
      updateFragment: vi.fn(),
      deleteFragment: vi.fn(),
      restoreFragment: vi.fn(),
    },
    workspace,
    background,
  );
  const preferences = new UiPreferences({
    getItem: (key) =>
      key === 'cut-on-eight.active-view' ? (options.initialView ?? null) : null,
    setItem: vi.fn(),
  });
  return {
    app: new AppModel(workspace, background, fragments, preferences),
    close,
    connectJobEvents,
    loadFragments,
    loadTags,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => (resolve = done));
  return { promise, resolve };
}

describe('AppModel', () => {
  it('starts features and loads the restored fragment view', async () => {
    const { app, loadFragments, loadTags } = createModel({
      initialView: 'fragments',
    });
    await app.start();
    await Promise.resolve();
    expect(app.backendState).toBe('ready');
    expect(loadFragments).toHaveBeenCalledOnce();
    expect(loadTags).not.toHaveBeenCalled();
  });

  it('reports workspace initialization failure', async () => {
    const { app } = createModel({
      loadWorkspace: vi.fn().mockRejectedValue(new Error('offline')),
    });
    await app.start();
    expect(app.backendState).toBe('unavailable');
    expect(app.generalError).toContain('offline');
    expect(app.status.state).toBe('attention');
  });

  it('refreshes fragments when changing views', () => {
    const { app, loadFragments } = createModel();
    app.changeView('fragments');
    expect(loadFragments).toHaveBeenCalledOnce();
  });

  it('disposes feature resources', () => {
    const { app, close } = createModel();
    app.background.start();
    app.dispose();
    app.dispose();
    expect(close).toHaveBeenCalledOnce();
  });

  it('does not start background work when disposed during initialization', async () => {
    const pending = deferred<WorkspaceSnapshot>();
    const { app, connectJobEvents } = createModel({
      loadWorkspace: () => pending.promise,
    });
    const started = app.start();
    app.dispose();
    pending.resolve(emptyWorkspace);
    await started;
    expect(connectJobEvents).not.toHaveBeenCalled();
  });
});
