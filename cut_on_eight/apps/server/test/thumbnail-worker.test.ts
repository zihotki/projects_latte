import type { ProjectDocument } from '@cut-on-eight/legacy-contracts';
import {
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { FfmpegRunnerLike } from '../src/jobs/ffmpeg-runner.js';
import {
  createSamplingPlan,
  createThumbnailManifest,
} from '../src/thumbnails/thumbnail-manifest.js';
import {
  ThumbnailGenerationError,
  ThumbnailWorker,
} from '../src/thumbnails/thumbnail-worker.js';

const roots: string[] = [];
const identity = {
  generatorVersion: 'thumbnail-overview-v1',
  sourceFingerprint: `sha256:${'a'.repeat(64)}`,
};

function project(durationSeconds = 20): ProjectDocument {
  return {
    schemaVersion: 3,
    id: '10000000-0000-4000-8000-000000000001',
    source: {
      fileName: 'Dance.mp4',
      durationSeconds,
      width: 1280,
      height: 720,
      frameRateNumerator: 30,
      frameRateDenominator: 1,
      frameRateReliability: 'reliable',
      hasAudio: true,
      inspectedAt: '2026-07-21T10:00:00.000Z',
      inspectorVersion: 'ffprobe-v1',
    },
    editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
    settings: { pauseAfterCreation: false },
    playbackPositionSeconds: 0,
    selectedSegmentId: null,
    segments: [],
    metadata: { title: null, tags: [], notes: null },
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

function fakeRunner(
  options: { corrupt?: boolean; partial?: boolean; truncated?: boolean } = {},
): FfmpegRunnerLike {
  return {
    generateSprites: vi.fn(async ({ destinationDirectory, plan }) => {
      const manifest = createThumbnailManifest(
        { ...identity, durationSeconds: 20 },
        plan,
      );
      const pages = options.partial
        ? manifest.pages.slice(0, -1)
        : manifest.pages;
      await Promise.all(
        pages.map(([name, width, height]) =>
          writeFile(
            join(destinationDirectory, name),
            options.truncated
              ? webp(width, height).subarray(0, 30)
              : webp(options.corrupt ? width - 1 : width, height),
          ),
        ),
      );
    }),
  };
}

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true, force: true })),
  );
});

async function fixture(): Promise<{ root: string; destination: string }> {
  const root = await mkdtemp(join(tmpdir(), 'cut-on-eight-thumbnails-'));
  roots.push(root);
  return { root, destination: join(root, 'thumbnails') };
}

describe('thumbnail sampling and worker', () => {
  it('bounds short and one-hour sampling plans with endpoints in range', () => {
    expect(createSamplingPlan(1).sampleTimes).toEqual([0]);
    const long = createSamplingPlan(3600);
    expect(long.sampleTimes).toHaveLength(600);
    expect(long.sampleTimes[0]).toBe(0);
    expect(long.sampleTimes.at(-1)).toBeLessThan(3600);
    expect(long.pageCount).toBe(2);
  });

  it('promotes bounded sprite pages and keeps sampled frames out of final storage', async () => {
    const { root, destination } = await fixture();
    await new ThumbnailWorker(fakeRunner()).generate(
      project(),
      join(root, 'Dance.mp4'),
      destination,
      identity,
    );

    expect((await readdir(destination)).sort()).toEqual([
      'manifest.json',
      'sprite-001.webp',
    ]);
    const manifest = JSON.parse(
      await readFile(join(destination, 'manifest.json'), 'utf8'),
    ) as { samples: unknown[] };
    expect(manifest.samples).toHaveLength(10);
  });

  it.each([{ partial: true }, { corrupt: true }, { truncated: true }])(
    'rejects incomplete or corrupt output and preserves the previous set: %j',
    async (options) => {
      const { root, destination } = await fixture();
      await new ThumbnailWorker(fakeRunner()).generate(
        project(),
        join(root, 'Dance.mp4'),
        destination,
        identity,
      );
      const previous = await readFile(join(destination, 'manifest.json'));
      await expect(
        new ThumbnailWorker(fakeRunner(options)).generate(
          project(1200),
          join(root, 'Dance.mp4'),
          destination,
          { ...identity, sourceFingerprint: `sha256:${'b'.repeat(64)}` },
        ),
      ).rejects.toBeInstanceOf(ThumbnailGenerationError);
      expect(await readFile(join(destination, 'manifest.json'))).toEqual(
        previous,
      );
    },
  );

  it('restores the previous complete set when the post-promotion sync fails', async () => {
    const { root, destination } = await fixture();
    await new ThumbnailWorker(fakeRunner()).generate(
      project(),
      join(root, 'Dance.mp4'),
      destination,
      identity,
    );
    const previous = await readFile(join(destination, 'manifest.json'));
    const worker = new ThumbnailWorker(fakeRunner(), {
      removeDirectory: rm,
      renameDirectory: rename,
      syncDirectory: async () => {
        throw Object.assign(new Error('sync failed'), { code: 'EIO' });
      },
    });

    await expect(
      worker.generate(project(21), join(root, 'Dance.mp4'), destination, {
        ...identity,
        sourceFingerprint: `sha256:${'c'.repeat(64)}`,
      }),
    ).rejects.toMatchObject({
      code: 'thumbnail_generation_failed',
      retryable: true,
    });
    expect(await readFile(join(destination, 'manifest.json'))).toEqual(
      previous,
    );
  });

  it('reuses a valid compatible set without invoking FFmpeg', async () => {
    const { root, destination } = await fixture();
    await new ThumbnailWorker(fakeRunner()).generate(
      project(),
      join(root, 'Dance.mp4'),
      destination,
      identity,
    );
    const runner = fakeRunner();
    await new ThumbnailWorker(runner).generate(
      project(),
      join(root, 'Dance.mp4'),
      destination,
      identity,
    );
    expect(runner.generateSprites).not.toHaveBeenCalled();
  });
});
