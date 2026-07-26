import { createHash } from 'node:crypto';
import { readFile, readdir, rename } from 'node:fs/promises';
import { join } from 'node:path';
import type { FfmpegRunnerLike } from '../jobs/ffmpeg-runner.js';
import { createSamplingPlan } from './thumbnail-manifest.js';
import { ThumbnailBundleStore } from './thumbnail-bundle-store.js';
import {
  createVideoThumbnailManifest,
  type VideoThumbnailManifest,
} from './video-thumbnail-manifest.js';
import { writeJsonAtomic } from '../storage/atomic-json.js';

export interface GeneratedVideoThumbnailBundle {
  readonly manifest: VideoThumbnailManifest;
  readonly storageKey: string;
}

export class VideoThumbnailGenerator {
  constructor(
    private readonly ffmpeg: FfmpegRunnerLike,
    private readonly bundles: ThumbnailBundleStore,
  ) {}

  async generate(input: {
    durationSeconds: number;
    signal?: AbortSignal;
    sourcePath: string;
  }): Promise<GeneratedVideoThumbnailBundle> {
    const staging = await this.bundles.createStagingDirectory();
    try {
      const plan = createSamplingPlan(input.durationSeconds);
      await this.ffmpeg.generateSprites({
        destinationDirectory: staging.path,
        plan,
        signal: input.signal,
        sourcePath: input.sourcePath,
      });
      const pageNames = await fingerprintPages(staging.path, plan.pageCount);
      const manifest = createVideoThumbnailManifest(
        input.durationSeconds,
        plan,
        pageNames,
      );
      await writeJsonAtomic(join(staging.path, 'manifest.json'), manifest);
      return {
        manifest,
        storageKey: await this.bundles.publish(staging.key),
      };
    } catch (error) {
      await this.bundles.discardStaging(staging.key).catch(() => undefined);
      throw error;
    }
  }
}

async function fingerprintPages(
  directory: string,
  expectedCount: number,
): Promise<string[]> {
  const entries = (await readdir(directory))
    .filter((name) => /^sprite-\d+\.webp$/.test(name))
    .sort();
  if (entries.length !== expectedCount) {
    throw new Error('FFmpeg produced an incomplete thumbnail sprite bundle');
  }
  return Promise.all(
    entries.map(async (name, index) => {
      const bytes = await readFile(join(directory, name));
      const hash = createHash('sha256')
        .update(bytes)
        .digest('hex')
        .slice(0, 24);
      const fingerprinted = `sprite-${hash}-${index + 1}.webp`;
      await rename(join(directory, name), join(directory, fingerprinted));
      return fingerprinted;
    }),
  );
}
