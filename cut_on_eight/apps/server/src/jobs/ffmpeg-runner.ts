import { spawn } from 'node:child_process';
import type { EventEmitter } from 'node:events';
import { join } from 'node:path';
import {
  spriteColumns,
  spriteRows,
  thumbnailHeight,
  thumbnailWidth,
  type SamplingPlan,
} from '../thumbnails/thumbnail-manifest.js';

const DEFAULT_TIMEOUT_MILLISECONDS = 10 * 60_000;
const MAX_STDERR_BYTES = 256 * 1024;

export interface GenerateSpritesRequest {
  readonly destinationDirectory: string;
  readonly plan: SamplingPlan;
  readonly signal?: AbortSignal;
  readonly sourcePath: string;
}

export interface FfmpegRunnerLike {
  generateSprites(request: GenerateSpritesRequest): Promise<void>;
}

export class FfmpegError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = 'FfmpegError';
  }
}

type RunProcess = (
  executable: string,
  arguments_: readonly string[],
  signal?: AbortSignal,
) => Promise<void>;

export function createBoundedFfmpegProcessRunner(
  timeoutMilliseconds = DEFAULT_TIMEOUT_MILLISECONDS,
  maxStderrBytes = MAX_STDERR_BYTES,
  spawnProcess: SpawnProcess = (executable, arguments_, options) =>
    spawn(executable, arguments_, options),
): RunProcess {
  return (executable, arguments_, signal) =>
    new Promise((resolve, reject) => {
      if (signal?.aborted === true) {
        reject(abortedError());
        return;
      }
      const child = spawnProcess(executable, [...arguments_], {
        shell: false,
        stdio: ['ignore', 'ignore', 'pipe'],
      });
      let stderrBytes = 0;
      let settled = false;
      const abort = (): void => {
        child.kill('SIGKILL');
        finish(() => reject(abortedError()));
      };
      const finish = (operation: () => void): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        signal?.removeEventListener('abort', abort);
        operation();
      };

      child.stderr.on('data', (chunk: Buffer) => {
        stderrBytes += chunk.length;
        if (stderrBytes <= maxStderrBytes) return;
        child.kill('SIGKILL');
        finish(() =>
          reject(
            new FfmpegError(
              'ffmpeg_output_too_large',
              'FFmpeg produced too much diagnostic output.',
              true,
            ),
          ),
        );
      });
      child.once('error', (error: NodeJS.ErrnoException) => {
        finish(() =>
          reject(
            error.code === 'ENOENT'
              ? new FfmpegError(
                  'ffmpeg_missing',
                  'FFmpeg is not installed or cannot be found.',
                  true,
                )
              : new FfmpegError(
                  'ffmpeg_failed',
                  'FFmpeg could not be started.',
                  true,
                ),
          ),
        );
      });
      child.once('close', (code) => {
        finish(() =>
          code === 0
            ? resolve()
            : reject(
                new FfmpegError(
                  'ffmpeg_failed',
                  'FFmpeg could not generate thumbnail sprites.',
                  true,
                ),
              ),
        );
      });

      const timeout = setTimeout(() => {
        child.kill('SIGKILL');
        finish(() =>
          reject(
            new FfmpegError(
              'ffmpeg_timeout',
              'FFmpeg did not finish thumbnail generation in time.',
              true,
            ),
          ),
        );
      }, timeoutMilliseconds);
      timeout.unref();
      signal?.addEventListener('abort', abort, { once: true });
    });
}

function abortedError(): FfmpegError {
  return new FfmpegError(
    'ffmpeg_aborted',
    'FFmpeg thumbnail generation was paused for shutdown.',
    true,
  );
}

interface SpawnedProcess extends EventEmitter {
  readonly stderr: EventEmitter;
  kill(signal: NodeJS.Signals): boolean;
}

type SpawnProcess = (
  executable: string,
  arguments_: readonly string[],
  options: {
    shell: false;
    stdio: ['ignore', 'ignore', 'pipe'];
  },
) => SpawnedProcess;

export class FfmpegRunner implements FfmpegRunnerLike {
  constructor(
    private readonly executable = 'ffmpeg',
    private readonly run: RunProcess = createBoundedFfmpegProcessRunner(),
  ) {}

  generateSprites(request: GenerateSpritesRequest): Promise<void> {
    const frameRate = 1 / request.plan.intervalSeconds;
    const filter = [
      `fps=${frameRate}`,
      `scale=${thumbnailWidth}:${thumbnailHeight}:force_original_aspect_ratio=decrease`,
      `pad=${thumbnailWidth}:${thumbnailHeight}:(ow-iw)/2:(oh-ih)/2`,
      `tile=${spriteColumns}x${spriteRows}:nb_frames=${spriteColumns * spriteRows}:padding=0:margin=0`,
    ].join(',');
    return this.run(
      this.executable,
      [
        '-hide_banner',
        '-loglevel',
        'error',
        '-nostdin',
        '-y',
        '-i',
        request.sourcePath,
        '-an',
        '-vf',
        filter,
        '-frames:v',
        String(request.plan.pageCount),
        '-c:v',
        'libwebp',
        '-lossless',
        '0',
        '-quality',
        '72',
        join(request.destinationDirectory, 'sprite-%03d.webp'),
      ],
      request.signal,
    );
  }
}
