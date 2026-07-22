import type {
  ProjectDocument,
  ThumbnailManifestV1,
} from '@cut-on-eight/contracts';
import { randomUUID } from 'node:crypto';
import { mkdir, rename, rm } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { syncDirectory, writeJsonAtomic } from '../storage/atomic-json.js';
import type { FfmpegRunnerLike } from '../jobs/ffmpeg-runner.js';
import { FfmpegError } from '../jobs/ffmpeg-runner.js';
import {
  createSamplingPlan,
  createThumbnailManifest,
  readCompatibleThumbnailManifest,
  type ThumbnailCompatibility,
} from './thumbnail-manifest.js';

export interface ThumbnailIdentity {
  readonly generatorVersion: string;
  readonly sourceFingerprint: string;
}

export interface ThumbnailGenerator {
  generate(
    project: ProjectDocument,
    sourcePath: string,
    destinationDirectory: string,
    identity: ThumbnailIdentity,
    signal?: AbortSignal,
  ): Promise<ThumbnailManifestV1>;
}

export class ThumbnailGenerationError extends Error {
  readonly code = 'thumbnail_generation_failed';
  readonly retryable = true;

  constructor(message = 'Thumbnail sprites could not be generated safely.') {
    super(message);
    this.name = 'ThumbnailGenerationError';
  }
}

interface WorkerOperations {
  readonly removeDirectory: typeof rm;
  readonly renameDirectory: typeof rename;
  readonly syncDirectory: typeof syncDirectory;
}

const defaultOperations: WorkerOperations = {
  removeDirectory: rm,
  renameDirectory: rename,
  syncDirectory,
};

export class ThumbnailWorker implements ThumbnailGenerator {
  constructor(
    private readonly ffmpeg: FfmpegRunnerLike,
    private readonly operations: WorkerOperations = defaultOperations,
  ) {}

  async generate(
    project: ProjectDocument,
    sourcePath: string,
    destinationDirectory: string,
    identity: ThumbnailIdentity,
    signal?: AbortSignal,
  ): Promise<ThumbnailManifestV1> {
    const durationSeconds = project.source.durationSeconds;
    if (durationSeconds === null) {
      throw new ThumbnailGenerationError('The source has not been inspected.');
    }
    const compatibility: ThumbnailCompatibility = {
      ...identity,
      durationSeconds,
    };
    const existing = await readCompatibleThumbnailManifest(
      destinationDirectory,
      compatibility,
    );
    if (existing !== undefined) return existing;

    const parent = dirname(destinationDirectory);
    const token = randomUUID();
    const stagingDirectory = join(parent, `.thumbnails.${token}.staging`);
    const backupDirectory = join(parent, `.thumbnails.${token}.previous`);
    let previousMoved = false;
    let stagingPromoted = false;

    try {
      await mkdir(stagingDirectory, { recursive: false, mode: 0o700 });
      const plan = createSamplingPlan(durationSeconds);
      const manifest = createThumbnailManifest(compatibility, plan);
      await this.ffmpeg.generateSprites({
        destinationDirectory: stagingDirectory,
        plan,
        signal,
        sourcePath,
      });

      const validated = await this.validateGeneratedSet(
        stagingDirectory,
        manifest,
        compatibility,
      );
      await writeJsonAtomic(join(stagingDirectory, 'manifest.json'), validated);

      try {
        await this.operations.renameDirectory(
          destinationDirectory,
          backupDirectory,
        );
        previousMoved = true;
      } catch (error) {
        if (!isMissing(error)) throw error;
      }

      await this.operations.renameDirectory(
        stagingDirectory,
        destinationDirectory,
      );
      stagingPromoted = true;
      await this.operations.syncDirectory(parent);
      if (previousMoved) {
        await this.operations
          .removeDirectory(backupDirectory, {
            force: true,
            recursive: true,
          })
          .catch(() => undefined);
        previousMoved = false;
        await this.operations.syncDirectory(parent).catch(() => undefined);
      }
      return validated;
    } catch (error) {
      if (previousMoved) {
        if (stagingPromoted) {
          await this.operations
            .removeDirectory(destinationDirectory, {
              force: true,
              recursive: true,
            })
            .catch(() => undefined);
        }
        const restored = await this.operations
          .renameDirectory(backupDirectory, destinationDirectory)
          .then(
            () => true,
            () => false,
          );
        if (restored) {
          previousMoved = false;
          await this.operations.syncDirectory(parent).catch(() => undefined);
        }
      } else if (stagingPromoted) {
        await this.operations
          .removeDirectory(destinationDirectory, {
            force: true,
            recursive: true,
          })
          .catch(() => undefined);
      }
      if (error instanceof ThumbnailGenerationError) throw error;
      if (error instanceof FfmpegError) throw error;
      throw new ThumbnailGenerationError();
    } finally {
      await this.operations
        .removeDirectory(stagingDirectory, {
          force: true,
          recursive: true,
        })
        .catch(() => undefined);
      if (!previousMoved) {
        await this.operations
          .removeDirectory(backupDirectory, {
            force: true,
            recursive: true,
          })
          .catch(() => undefined);
      }
    }
  }

  private async validateGeneratedSet(
    stagingDirectory: string,
    manifest: ThumbnailManifestV1,
    compatibility: ThumbnailCompatibility,
  ): Promise<ThumbnailManifestV1> {
    await writeJsonAtomic(join(stagingDirectory, 'manifest.json'), manifest);
    const validated = await readCompatibleThumbnailManifest(
      stagingDirectory,
      compatibility,
    );
    await rm(join(stagingDirectory, 'manifest.json'), { force: true });
    if (validated === undefined) {
      throw new ThumbnailGenerationError(
        'FFmpeg produced an incomplete or invalid sprite set.',
      );
    }
    return validated;
  }
}

function isMissing(error: unknown): boolean {
  return (
    error instanceof Error &&
    'code' in error &&
    (error as NodeJS.ErrnoException).code === 'ENOENT'
  );
}
