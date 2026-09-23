import { afterEach, describe, expect, test, vi } from 'vitest';
import { ApiFailure, loadThumbnailManifest, thumbnailPageUrl } from './api.js';

afterEach(() => vi.unstubAllGlobals());

describe('video thumbnail API', () => {
  test('loads the video manifest and gives the timeline a stable cache identity', async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          schemaVersion: 1,
          profileVersion: 'overview-webp-v2',
          durationSeconds: 10,
          thumbnail: [160, 90],
          pages: [['sprite-0123456789abcdef01234567-1.webp', 160, 90]],
          samples: [[0, 0, 0, 0, 160, 90]],
        }),
        { headers: { etag: '"bundle-1"' } },
      ),
    );
    vi.stubGlobal('fetch', fetch);

    const manifest = await loadThumbnailManifest('video-1');

    expect(fetch).toHaveBeenCalledWith(
      '/thumbnail-cdn/v1/videos/video-1/manifest.json',
    );
    expect(manifest.generatorVersion).toBe('overview-webp-v2');
    expect(manifest.sourceFingerprint).toBe('"bundle-1"');
    expect(
      thumbnailPageUrl('video-1', manifest.pages[0]![0], 'bundle-1'),
    ).toContain('/thumbnail-cdn/v1/videos/video-1/');
  });

  test('treats a missing manifest as generation in progress', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(null, { status: 404 })),
    );
    await expect(loadThumbnailManifest('video-1')).rejects.toMatchObject({
      status: 404,
      code: 'thumbnail_not_ready',
    } satisfies Partial<ApiFailure>);
  });
});
