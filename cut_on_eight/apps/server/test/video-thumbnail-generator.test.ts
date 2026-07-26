import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import type { FfmpegRunnerLike } from '../src/jobs/ffmpeg-runner.js';
import { ThumbnailBundleStore } from '../src/thumbnails/thumbnail-bundle-store.js';
import { VideoThumbnailGenerator } from '../src/thumbnails/video-thumbnail-generator.js';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true, force: true })),
  );
});

describe('VideoThumbnailGenerator', () => {
  it('publishes an opaque bundle with fingerprinted WebP pages', async () => {
    const root = await mkdtemp(
      join(tmpdir(), 'cut-on-eight-video-thumbnails-'),
    );
    roots.push(root);
    const bundles = new ThumbnailBundleStore(root);
    const generator = new VideoThumbnailGenerator(fakeRunner(), bundles);

    const result = await generator.generate({
      durationSeconds: 20,
      sourcePath: join(root, 'source.mp4'),
    });

    expect(result.storageKey).toMatch(/^[a-f0-9-]{36}$/);
    expect(result.manifest.pages).toHaveLength(1);
    const [name] = result.manifest.pages[0]!;
    expect(name).toMatch(/^sprite-[a-f0-9]{24}-1\.webp$/);
    expect(await bundles.readPage(result.storageKey, name)).toEqual(
      webp(3200, 1800),
    );
  });
});

function fakeRunner(): FfmpegRunnerLike {
  return {
    async generateSprites({ destinationDirectory }): Promise<void> {
      await writeFile(
        join(destinationDirectory, 'sprite-001.webp'),
        webp(3200, 1800),
      );
    },
  };
}

function webp(width: number, height: number): Buffer {
  const bytes = Buffer.alloc(48);
  bytes.write('RIFF', 0, 'ascii');
  bytes.writeUInt32LE(40, 4);
  bytes.write('WEBPVP8X', 8, 'ascii');
  bytes.writeUInt32LE(10, 16);
  bytes.writeUIntLE(width - 1, 24, 3);
  bytes.writeUIntLE(height - 1, 27, 3);
  bytes.write('VP8 ', 30, 'ascii');
  bytes.writeUInt32LE(10, 34);
  bytes.writeUIntLE(0x2a019d, 41, 3);
  bytes.writeUInt16LE(width, 44);
  bytes.writeUInt16LE(height, 46);
  return bytes;
}
