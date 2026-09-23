import { describe, expect, it } from 'vitest';
import type { ThumbnailManifestV1 } from '@cut-on-eight/legacy-contracts';
import { selectVideoFragmentPreviews } from './video-fragment-previews.js';

const manifest: ThumbnailManifestV1 = {
  schemaVersion: 1,
  durationSeconds: 100,
  thumbnail: [160, 90],
  pages: [['sprite-aaaaaaaaaaaaaaaaaaaaaaaa-0.webp', 1760, 450]],
  samples: Array.from(
    { length: 11 },
    (_, index) => [index * 10, 0, index * 160, 0, 160, 90] as const,
  ),
  generatorVersion: 'overview-webp-v2',
  sourceFingerprint: 'bundle-a',
};

describe('video fragment previews', () => {
  it('selects spaced frames inside a normal fragment', () => {
    const frames = selectVideoFragmentPreviews(manifest, 10, 90);
    expect(frames).toHaveLength(5);
    expect(
      frames.every(
        ({ sampleSeconds }) => sampleSeconds >= 10 && sampleSeconds <= 90,
      ),
    ).toBe(true);
    expect(new Set(frames.map(({ x }) => x)).size).toBe(5);
  });

  it('uses the nearest frame for a short end-of-video fragment', () => {
    const frames = selectVideoFragmentPreviews(manifest, 98, 99);
    expect(frames.map(({ sampleSeconds }) => sampleSeconds)).toEqual([100]);
  });

  it('returns no frames while the bundle is missing', () => {
    expect(selectVideoFragmentPreviews(null, 10, 20)).toEqual([]);
  });
});
