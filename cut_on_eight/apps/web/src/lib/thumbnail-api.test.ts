import { afterEach, describe, expect, test, vi } from 'vitest';
import {
  ApiFailure,
  loadFragments,
  loadThumbnailManifest,
  thumbnailPageUrl,
} from './api.js';

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

  test('uses video bundle frames on fragment cards', async () => {
    const videoId = '00000000-0000-4000-8000-000000000111';
    const fragmentId = '00000000-0000-4000-8000-000000000112';
    const fetch = vi.fn(async (url: string) => {
      if (url === '/api/fragments') {
        return new Response(
          JSON.stringify([
            {
              id: fragmentId,
              videoId,
              startUs: 1_000_000,
              endUs: 4_000_000,
              title: 'Turn',
              description: null,
              exportSelected: false,
              revision: 1,
              tags: [],
              previewState: 'pending',
              preview: null,
            },
          ]),
        );
      }
      if (url === '/api/videos') {
        return new Response(
          JSON.stringify([
            {
              id: videoId,
              title: 'Practice',
              description: null,
              originalFileName: 'practice.mp4',
              durationUs: 10_000_000,
              width: 320,
              height: 180,
              frameRateNumerator: null,
              frameRateDenominator: null,
              frameRateReliability: 'approximate',
              hasAudio: false,
              status: 'ready',
              revision: 1,
              tags: [],
            },
          ]),
        );
      }
      if (url === '/api/tags') return new Response('[]');
      return new Response(
        JSON.stringify({
          schemaVersion: 1,
          profileVersion: 'overview-webp-v2',
          durationSeconds: 10,
          thumbnail: [160, 90],
          pages: [['sprite-0123456789abcdef01234567-0.webp', 480, 90]],
          samples: [
            [0, 0, 0, 0, 160, 90],
            [2, 0, 160, 0, 160, 90],
            [5, 0, 320, 0, 160, 90],
          ],
        }),
      );
    });
    vi.stubGlobal('fetch', fetch);

    const catalogue = await loadFragments();

    expect(
      catalogue.fragments[0]?.previews.map(
        ({ sampleSeconds }) => sampleSeconds,
      ),
    ).toEqual([2]);
    expect(catalogue.fragments[0]?.previews[0]?.href).toContain(
      '/thumbnail-cdn/v1/videos/',
    );
    expect(catalogue.fragments[0]?.thumbnailState).toBe('ready');
  });
});
