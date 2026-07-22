import { jobRecordSchema, thumbnailManifestV1Schema } from '../src/index.js';
import { describe, expect, it } from 'vitest';

const manifest = {
  schemaVersion: 1,
  generatorVersion: 'overview-v1',
  sourceFingerprint: 'sha256:source',
  durationSeconds: 12,
  thumbnail: [160, 90],
  pages: [['sprite-001.webp', 320, 180]],
  samples: [
    [0, 0, 0, 0, 160, 90],
    [2, 0, 160, 0, 160, 90],
    [12, 0, 0, 90, 160, 90],
  ],
} as const;

describe('compact thumbnail manifest', () => {
  it('accepts positional sprite pages and samples', () => {
    expect(thumbnailManifestV1Schema.parse(manifest)).toEqual(manifest);
  });

  it.each([
    { pages: [['../frame.webp', 320, 180]] },
    { pages: [['sprite-1.webp', 320, 180]] },
    { pages: [['sprite-001.png', 320, 180]] },
    { pages: [['sprite-001.webp', 320]] },
    { samples: [[0, 0, 0, 0, 160]] },
  ])('rejects malformed tuple data: %o', (override) => {
    expect(() =>
      thumbnailManifestV1Schema.parse({ ...manifest, ...override }),
    ).toThrow();
  });

  it.each([
    {
      samples: [
        [0, 0, 0, 0, 160, 90],
        [0, 0, 160, 0, 160, 90],
      ],
    },
    { samples: [[13, 0, 0, 0, 160, 90]] },
    { samples: [[0, 1, 0, 0, 160, 90]] },
    { samples: [[0, 0, 200, 0, 160, 90]] },
    { samples: [[0, 0, 0, 0, 161, 90]] },
  ])('rejects invalid sample geometry or timing: %o', (override) => {
    expect(() =>
      thumbnailManifestV1Schema.parse({ ...manifest, ...override }),
    ).toThrow();
  });
});

describe('thumbnail job contract', () => {
  const base = {
    schemaVersion: 1,
    id: '20000000-0000-4000-8000-000000000001',
    projectId: '10000000-0000-4000-8000-000000000001',
    state: 'queued',
    attempts: 0,
    maxAttempts: 3,
    createdAt: '2026-07-22T10:00:00.000Z',
    updatedAt: '2026-07-22T10:00:00.000Z',
    error: null,
  } as const;

  it('keeps existing inspection records valid', () => {
    expect(
      jobRecordSchema.parse({ ...base, type: 'inspect-source' }),
    ).toMatchObject({ type: 'inspect-source' });
  });

  it('requires the thumbnail generation identity', () => {
    const thumbnailJob = {
      ...base,
      type: 'generate-thumbnails',
      generatorVersion: 'overview-v1',
      sourceFingerprint: 'sha256:source',
    };

    expect(jobRecordSchema.parse(thumbnailJob)).toEqual(thumbnailJob);
    expect(() =>
      jobRecordSchema.parse({ ...base, type: 'generate-thumbnails' }),
    ).toThrow();
  });
});
