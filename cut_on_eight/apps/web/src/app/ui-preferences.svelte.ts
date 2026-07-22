import type {
  ProjectDocument,
  WorkspaceSnapshot,
} from '@cut-on-eight/contracts';
import type { ActiveView, EditorMode } from '../components/EditorShell.svelte';

const ACTIVE_VIEW_KEY = 'cut-on-eight.active-view';
const SEGMENT_PANEL_KEY = 'cut-on-eight.segment-panel-collapsed';

export interface PreferenceStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export class UiPreferences {
  activeView = $state<ActiveView>('library');
  segmentPanelCollapsed = $state(false);
  boundaryEditingProjectId = $state<string | null>(null);

  constructor(private readonly storage: PreferenceStorage | null) {}

  initialize(snapshot: Pick<WorkspaceSnapshot, 'activeProjectId'>): void {
    this.activeView =
      this.readActiveView() ??
      (snapshot.activeProjectId === null ? 'library' : 'editor');
    this.segmentPanelCollapsed = this.read(SEGMENT_PANEL_KEY) === 'true';
  }

  changeView(view: ActiveView): void {
    this.activeView = view;
    this.write(ACTIVE_VIEW_KEY, view);
  }

  setSegmentPanelCollapsed(collapsed: boolean): void {
    this.segmentPanelCollapsed = collapsed;
    this.write(SEGMENT_PANEL_KEY, String(collapsed));
  }

  setBoundaryMode(projectId: string, focused: boolean): void {
    this.boundaryEditingProjectId = focused ? projectId : null;
  }

  editorMode(activeProject: ProjectDocument | null): EditorMode {
    if (
      activeProject !== null &&
      this.boundaryEditingProjectId === activeProject.id
    ) {
      return 'boundary';
    }
    return activeProject?.selectedSegmentId === null || activeProject === null
      ? 'video'
      : 'segment';
  }

  private readActiveView(): ActiveView | null {
    const value = this.read(ACTIVE_VIEW_KEY);
    return value === 'editor' || value === 'library' || value === 'fragments'
      ? value
      : null;
  }

  private read(key: string): string | null {
    try {
      return this.storage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }

  private write(key: string, value: string): void {
    try {
      this.storage?.setItem(key, value);
    } catch {
      // Browser storage is optional; in-memory preferences remain usable.
    }
  }
}

export function browserPreferenceStorage(): PreferenceStorage | null {
  return typeof localStorage === 'undefined' ? null : localStorage;
}
