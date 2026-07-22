import { describe, expect, it } from 'vitest';
import {
  catalogueMetadataSchema,
  fragmentCatalogueSchema,
  fragmentMutationSchema,
} from '../src/index.js';

const tagId = '10000000-0000-4000-8000-000000000001';
const projectId = '20000000-0000-4000-8000-000000000001';
const segmentId = '30000000-0000-4000-8000-000000000001';

describe('fragment catalogue contracts', () => {
  it('normalizes tag names and rejects normalized duplicates', () => {
    expect(
      catalogueMetadataSchema.parse({
        schemaVersion: 1,
        tags: [{ id: tagId, name: '  Salsa  ' }],
      }).tags[0]?.name,
    ).toBe('salsa');

    expect(
      catalogueMetadataSchema.safeParse({
        schemaVersion: 1,
        tags: [
          { id: tagId, name: 'salsa' },
          { id: '10000000-0000-4000-8000-000000000002', name: 'SALSA' },
        ],
      }).success,
    ).toBe(false);
  });

  it('validates a compact five-frame catalogue response', () => {
    const parsed = fragmentCatalogueSchema.parse({
      tags: [{ id: tagId, name: 'salsa' }],
      diagnostics: [],
      fragments: [
        {
          projectId,
          sourceFileName: 'dance.mp4',
          sourceDurationSeconds: 30,
          ordinal: 1,
          thumbnailState: 'ready',
          thumbnailJobId: null,
          frameStepSeconds: 1 / 30,
          frameStepApproximate: true,
          segment: {
            id: segmentId,
            startSeconds: 10,
            endSeconds: 15,
            exportSelected: true,
            title: 'Cross body',
            tagIds: [tagId],
          },
          previews: [
            {
              sampleSeconds: 10.5,
              pageFileName: 'sprite-000.webp',
              pageWidth: 960,
              pageHeight: 540,
              x: 0,
              y: 0,
              width: 192,
              height: 108,
              identity: 'generator:fingerprint',
            },
          ],
        },
      ],
    });

    expect(parsed.fragments[0]?.previews).toHaveLength(1);
  });

  it('trims nullable titles in mutation payloads', () => {
    expect(
      fragmentMutationSchema.parse({
        startSeconds: 1,
        endSeconds: 2,
        exportSelected: false,
        title: '  Shine  ',
        tagIds: [],
      }).title,
    ).toBe('Shine');
  });
});
