import type {
  ProjectDocument,
  WorkspaceSnapshot,
} from '../domain/editor-model.js';
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
const videoId = '10000000-0000-4000-8000-000000000001';
const fragmentId = '20000000-0000-4000-8000-000000000001';

function openWorkspace(
  selectedSegmentId: string | null = null,
): WorkspaceSnapshot {
  const project: ProjectDocument = {
    schemaVersion: 3,
    id: videoId,
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
    selectedSegmentId,
    segments: [
      {
        id: fragmentId,
        startSeconds: 1,
        endSeconds: 3,
        title: null,
        tagIds: [],
        exportSelected: true,
      },
    ],
    settings: { pauseAfterCreation: false },
    metadata: { title: null, tags: [], notes: null },
    editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
  };
  return { activeProjectId: videoId, openProjects: [project], library: [] };
}

function createModel(
  options: {
    initialView?: string;
    loadWorkspace?: () => Promise<WorkspaceSnapshot>;
    openProject?: () => Promise<WorkspaceSnapshot>;
  } = {},
) {
  const workspace = new WorkspaceSession({
    loadWorkspace:
      options.loadWorkspace ?? vi.fn().mockResolvedValue(emptyWorkspace),
    selectImport: vi.fn(),
    openProject: options.openProject ?? vi.fn(),
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
  it('opens a search result in the editor and selects its fragment', async () => {
    const { app } = createModel({
      initialView: 'search',
      openProject: vi.fn().mockResolvedValue(openWorkspace()),
    });
    await app.start();
    await app.openSearchResult(videoId, fragmentId);
    expect(app.workspace.activeProject?.selectedSegmentId).toBe(fragmentId);
    expect(app.preferences.activeView).toBe('editor');
  });

  it('opens a video but clears a missing search fragment', async () => {
    const { app } = createModel({
      initialView: 'search',
      openProject: vi.fn().mockResolvedValue(openWorkspace(fragmentId)),
    });
    await app.start();
    await app.openSearchResult(videoId, 'missing');
    expect(app.workspace.activeProject?.selectedSegmentId).toBeNull();
    expect(app.preferences.activeView).toBe('editor');
  });

  it('keeps the current view if a video cannot be opened', async () => {
    const { app } = createModel({
      initialView: 'search',
      openProject: vi.fn().mockRejectedValue(new Error('offline')),
    });
    await app.start();
    await app.openSearchResult(videoId, fragmentId);
    expect(app.preferences.activeView).toBe('search');
    expect(app.workspace.activeProject).toBeNull();
  });

  it('moves to the editor after opening a video from the library', async () => {
    const { app } = createModel({
      initialView: 'library',
      openProject: vi.fn().mockResolvedValue(openWorkspace()),
    });
    await app.start();
    await app.openLibraryVideo(videoId);
    expect(app.preferences.activeView).toBe('editor');
  });
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
