import type { ActiveView, EditorMode } from '../components/EditorShell.svelte';
import { activateProject, closeProject } from '../lib/api.js';
import {
  createTag,
  deleteFragment,
  deleteProject,
  loadCapabilities,
  loadFragments,
  loadTags,
  loadThumbnailManifest,
  loadWorkspace,
  openProject,
  restoreFragment,
  retryJob,
  saveProject,
  selectImport,
  updateFragment,
} from '../lib/api.js';
import { connectJobEvents } from '../lib/job-events.js';
import {
  deriveAppStatus,
  type AppStatusSnapshot,
  type BackendState,
} from './app-status.js';
import {
  BackgroundProcessing,
  type BackgroundApi,
} from './background-processing.svelte.js';
import {
  FragmentLibrary,
  type FragmentApi,
} from './fragment-library.svelte.js';
import {
  browserPreferenceStorage,
  UiPreferences,
} from './ui-preferences.svelte.js';
import {
  WorkspaceSession,
  type WorkspaceApi,
} from './workspace-session.svelte.js';

export class AppModel {
  backendState = $state<BackendState>('checking');
  private startRevision = 0;
  private disposed = false;

  constructor(
    readonly workspace: WorkspaceSession,
    readonly background: BackgroundProcessing,
    readonly fragments: FragmentLibrary,
    readonly preferences: UiPreferences,
  ) {}

  get status(): AppStatusSnapshot {
    return deriveAppStatus({
      backendState: this.backendState,
      ffprobeState: this.background.ffprobeState,
      importing: this.workspace.importing,
      busy: this.workspace.busyProjectId !== null,
      jobs: this.background.jobs,
      generalError: this.generalError,
      saveErrors: this.workspace.saveErrors,
    });
  }

  get editorMode(): EditorMode {
    return this.preferences.editorMode(this.workspace.activeProject);
  }

  get generalError(): string | null {
    return this.workspace.errorMessage ?? this.background.errorMessage;
  }

  async start(): Promise<void> {
    if (this.disposed) return;
    const revision = ++this.startRevision;
    try {
      const snapshot = await this.workspace.initialize();
      if (!this.isCurrentStart(revision)) return;
      this.preferences.initialize(snapshot);
      this.backendState = 'ready';
      void this.background.loadToolCapabilities();
      this.background.start();
      if (this.preferences.activeView === 'fragments') {
        void this.fragments.refresh();
      } else {
        void this.fragments.refreshTags();
      }
    } catch {
      if (this.isCurrentStart(revision)) this.backendState = 'unavailable';
    }
  }

  changeView(view: ActiveView): void {
    this.preferences.changeView(view);
    if (view === 'fragments') void this.fragments.refresh();
  }

  clearGeneralError(): void {
    this.workspace.clearError();
    this.background.clearError();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.startRevision += 1;
    this.fragments.dispose();
    this.background.dispose();
    this.workspace.dispose();
  }

  private isCurrentStart(revision: number): boolean {
    return !this.disposed && revision === this.startRevision;
  }
}

export function createAppModel(): AppModel {
  const preferences = new UiPreferences(browserPreferenceStorage());
  const collaboration: { background: BackgroundProcessing | null } = {
    background: null,
  };
  const workspaceApi: WorkspaceApi = {
    loadWorkspace,
    selectImport,
    openProject,
    activateProject,
    saveProject,
    closeProject,
    deleteProject,
  };
  const workspace = new WorkspaceSession(workspaceApi, {
    onWorkspaceApplied: (snapshot) =>
      collaboration.background?.requestThumbnails(snapshot.activeProjectId),
    onImportOutcome: (outcome) => {
      if (outcome !== 'cancelled') preferences.changeView('editor');
      void collaboration.background?.loadToolCapabilities();
    },
    onProjectOpened: () => preferences.changeView('editor'),
  });
  const backgroundApi: BackgroundApi = {
    loadCapabilities,
    loadThumbnailManifest,
    retryJob,
    connectJobEvents,
  };
  const background = new BackgroundProcessing(
    backgroundApi,
    () => workspace.workspace?.activeProjectId ?? null,
  );
  collaboration.background = background;
  const fragmentApi: FragmentApi = {
    loadFragments,
    loadTags,
    createTag,
    updateFragment,
    deleteFragment,
    restoreFragment,
  };
  const fragments = new FragmentLibrary(fragmentApi, workspace, background);
  return new AppModel(workspace, background, fragments, preferences);
}
