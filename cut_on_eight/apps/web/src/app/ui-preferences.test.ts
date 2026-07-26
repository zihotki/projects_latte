import type { WorkspaceSnapshot } from '../domain/editor-model.js';
import { describe, expect, it } from 'vitest';
import {
  UiPreferences,
  type PreferenceStorage,
} from './ui-preferences.svelte.js';

function snapshot(activeProjectId: string | null): WorkspaceSnapshot {
  return { activeProjectId, openProjects: [], library: [] };
}

describe('UiPreferences', () => {
  it('uses a saved valid view and persists changes', () => {
    const values = new Map([['cut-on-eight.active-view', 'fragments']]);
    const storage: PreferenceStorage = {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => void values.set(key, value),
    };
    const preferences = new UiPreferences(storage);
    preferences.initialize(snapshot(null));
    expect(preferences.activeView).toBe('fragments');
    preferences.changeView('editor');
    expect(values.get('cut-on-eight.active-view')).toBe('editor');
  });

  it('falls back according to whether a project is active', () => {
    const preferences = new UiPreferences(null);
    preferences.initialize(snapshot(null));
    expect(preferences.activeView).toBe('library');
    preferences.initialize(snapshot('project'));
    expect(preferences.activeView).toBe('editor');
  });

  it('keeps working when storage throws', () => {
    const preferences = new UiPreferences({
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {
        throw new Error('denied');
      },
    });
    expect(() => preferences.initialize(snapshot(null))).not.toThrow();
    expect(() => preferences.changeView('fragments')).not.toThrow();
    expect(preferences.activeView).toBe('fragments');
  });

  it('tracks panel and boundary modes', () => {
    const preferences = new UiPreferences(null);
    preferences.setSegmentPanelCollapsed(true);
    preferences.setBoundaryMode('project', true);
    expect(preferences.segmentPanelCollapsed).toBe(true);
    expect(preferences.boundaryEditingProjectId).toBe('project');
  });
});
