import { describe, expect, it } from 'vitest';
import type { FragmentSummary } from '../domain/catalogue-model.js';
import { filterFragments, fragmentLabel } from './fragment-catalogue.js';

const fragment = {
  projectId: '10000000-0000-4000-8000-000000000001',
  sourceFileName: 'Salsa Night.mp4',
  sourceDurationSeconds: 30,
  ordinal: 2,
  thumbnailState: 'unavailable',
  thumbnailJobId: null,
  frameStepSeconds: 1 / 30,
  frameStepApproximate: true,
  previews: [],
  segment: {
    id: '20000000-0000-4000-8000-000000000001',
    startSeconds: 3,
    endSeconds: 7,
    exportSelected: true,
    title: null,
    tagIds: ['30000000-0000-4000-8000-000000000001'],
  },
} satisfies FragmentSummary;

describe('fragment catalogue helpers', () => {
  it('uses a stable fallback label', () => {
    expect(fragmentLabel(fragment)).toBe('Fragment 2 · Salsa Night.mp4');
  });

  it('matches text case-insensitively and requires every selected tag', () => {
    expect(
      filterFragments([fragment], {
        query: 'SALSA',
        projectId: fragment.projectId,
        tagIds: new Set(fragment.segment.tagIds),
      }),
    ).toEqual([fragment]);
    expect(
      filterFragments([fragment], {
        query: '',
        projectId: null,
        tagIds: new Set(['30000000-0000-4000-8000-000000000099']),
      }),
    ).toEqual([]);
  });
});
