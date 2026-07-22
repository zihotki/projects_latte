import type { ThumbnailManifestV1 } from '@cut-on-eight/contracts';
import { describe, expect, it, vi } from 'vitest';
import { thumbnailPageUrl } from './api.js';
import {
  drawVisibleThumbnails,
  ThumbnailImageCache,
  visibleThumbnailPageIndexes,
} from './thumbnail-renderer.js';

const manifest: ThumbnailManifestV1 = {
  schemaVersion: 1,
  generatorVersion: 'overview-v1',
  sourceFingerprint: 'fingerprint-a',
  durationSeconds: 8,
  thumbnail: [160, 90],
  pages: [
    ['sprite-001.webp', 320, 90],
    ['sprite-002.webp', 320, 90],
  ],
  samples: [
    [0, 0, 0, 0, 160, 90],
    [2, 0, 160, 0, 160, 90],
    [4, 1, 0, 0, 160, 90],
    [6, 1, 160, 0, 160, 90],
  ],
};

function scale(startSeconds = 2, endSeconds = 6) {
  return {
    visibleRange: () => ({ startSeconds, endSeconds }),
    timeToPixel: (seconds: number) => (seconds - startSeconds) * 10,
  };
}

describe('thumbnail renderer', () => {
  it('changes immutable sprite URLs with the manifest identity', () => {
    const first = thumbnailPageUrl('project', 'sprite-001.webp', 'v1:first');
    const second = thumbnailPageUrl('project', 'sprite-001.webp', 'v2:second');
    expect(first).not.toBe(second);
    expect(first).toContain('?identity=v1%3Afirst');
  });

  it('draws only intersecting cells with manifest source rectangles', () => {
    const context = { drawImage: vi.fn() };
    const firstPage = { id: 'first' };
    const secondPage = { id: 'second' };

    const result = drawVisibleThumbnails(
      context,
      manifest,
      new Map([
        [0, firstPage],
        [1, secondPage],
      ]),
      scale(2.5, 5.5),
      { width: 30, height: 64 },
    );

    expect(result).toEqual({ drawn: 2, skipped: 2 });
    expect(context.drawImage).toHaveBeenNthCalledWith(
      1,
      firstPage,
      160,
      0,
      160,
      90,
      -5,
      0,
      20,
      64,
    );
    expect(context.drawImage).toHaveBeenNthCalledWith(
      2,
      secondPage,
      0,
      0,
      160,
      90,
      15,
      0,
      20,
      64,
    );
  });

  it('leaves unavailable visible pages undrawn', () => {
    const context = { drawImage: vi.fn() };
    const result = drawVisibleThumbnails(
      context,
      manifest,
      new Map(),
      scale(),
      { width: 40, height: 64 },
    );
    expect(result).toEqual({ drawn: 0, skipped: 4 });
    expect(context.drawImage).not.toHaveBeenCalled();
  });

  it('identifies only pages needed for the viewport', () => {
    expect(visibleThumbnailPageIndexes(manifest, scale(0, 1.9))).toEqual([0]);
    expect(visibleThumbnailPageIndexes(manifest, scale(4.1, 7))).toEqual([1]);
  });

  it('discards stale image loads after the active project changes', async () => {
    let resolveFirst!: (image: { id: string }) => void;
    const first = new Promise<{ id: string }>((resolve) => {
      resolveFirst = resolve;
    });
    const cache = new ThumbnailImageCache<{ id: string }>((url) =>
      url.includes('first') ? first : Promise.resolve({ id: 'second' }),
    );
    const firstLoad = cache.loadVisible(
      'first-project',
      manifest,
      [0],
      (fileName) => `/first/${fileName}`,
    );
    const secondLoad = cache.loadVisible(
      'second-project',
      manifest,
      [1],
      (fileName) => `/second/${fileName}`,
    );

    await expect(secondLoad).resolves.toEqual({
      failed: 0,
      images: new Map([[1, { id: 'second' }]]),
    });
    resolveFirst({ id: 'first' });
    await expect(firstLoad).resolves.toBeNull();
  });

  it('caches one image load per project, manifest, and visible page', async () => {
    const createImage = vi.fn(async (url: string) => ({ url }));
    const cache = new ThumbnailImageCache(createImage);
    const load = () =>
      cache.loadVisible('project', manifest, [0, 1], (fileName) => fileName);

    await load();
    await load();

    expect(createImage).toHaveBeenCalledTimes(2);
    expect(createImage).toHaveBeenCalledWith('sprite-001.webp');
    expect(createImage).toHaveBeenCalledWith('sprite-002.webp');
  });

  it('reports unavailable visible pages while keeping the neutral result', async () => {
    const cache = new ThumbnailImageCache(async () => {
      throw new Error('page unavailable');
    });

    await expect(
      cache.loadVisible('project', manifest, [0], (fileName) => fileName),
    ).resolves.toEqual({ failed: 1, images: new Map() });
  });
});
