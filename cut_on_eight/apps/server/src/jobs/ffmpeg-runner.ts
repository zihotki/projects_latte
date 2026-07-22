import { spawn } from 'node:child_process';
import type { EventEmitter } from 'node:events';
import { open, readFile, unlink } from 'node:fs/promises';
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

  async generateSprites(request: GenerateSpritesRequest): Promise<void> {
    const stagingBundle = join(request.destinationDirectory, '.sprites.ivf');
    try {
      await this.run(
        this.executable,
        createFfmpegSpriteArguments(request, stagingBundle),
        request.signal,
      );
      const pages = webpPagesFromIvf(
        await readFile(stagingBundle),
        request.plan.pageCount,
      );
      await Promise.all(
        pages.map((page, index) =>
          writeDurablePage(
            join(
              request.destinationDirectory,
              `sprite-${String(index + 1).padStart(3, '0')}.webp`,
            ),
            page,
          ),
        ),
      );
    } finally {
      await unlink(stagingBundle).catch(() => undefined);
    }
  }
}

export function createFfmpegSpriteArguments(
  request: GenerateSpritesRequest,
  stagingBundle: string,
): readonly string[] {
  const frameRate = 1 / request.plan.intervalSeconds;
  const filter = [
    `fps=${frameRate}`,
    `scale=${thumbnailWidth}:${thumbnailHeight}:force_original_aspect_ratio=decrease`,
    `pad=${thumbnailWidth}:${thumbnailHeight}:(ow-iw)/2:(oh-ih)/2`,
    `tile=${spriteColumns}x${spriteRows}:nb_frames=${spriteColumns * spriteRows}:padding=0:margin=0`,
  ].join(',');
  return [
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
    'libvpx',
    '-deadline',
    'good',
    '-cpu-used',
    '4',
    '-crf',
    '32',
    '-b:v',
    '0',
    '-g',
    '1',
    '-f',
    'ivf',
    stagingBundle,
  ];
}

export function webpPagesFromIvf(
  bytes: Uint8Array,
  expectedPages: number,
): readonly Buffer[] {
  const buffer = Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (
    buffer.length < 32 ||
    buffer.toString('ascii', 0, 4) !== 'DKIF' ||
    buffer.readUInt16LE(6) !== 32 ||
    buffer.toString('ascii', 8, 12) !== 'VP80'
  ) {
    throw invalidIvf();
  }

  const pages: Buffer[] = [];
  let offset = 32;
  while (offset < buffer.length) {
    if (offset + 12 > buffer.length) throw invalidIvf();
    const payloadSize = buffer.readUInt32LE(offset);
    const payloadStart = offset + 12;
    const payloadEnd = payloadStart + payloadSize;
    if (payloadSize < 10 || payloadEnd > buffer.length) throw invalidIvf();
    pages.push(wrapVp8AsWebp(buffer.subarray(payloadStart, payloadEnd)));
    offset = payloadEnd;
  }
  if (pages.length !== expectedPages) throw invalidIvf();
  return pages;
}

function wrapVp8AsWebp(payload: Buffer): Buffer {
  const padding = payload.length % 2;
  const result = Buffer.alloc(20 + payload.length + padding);
  result.write('RIFF', 0, 'ascii');
  result.writeUInt32LE(result.length - 8, 4);
  result.write('WEBPVP8 ', 8, 'ascii');
  result.writeUInt32LE(payload.length, 16);
  payload.copy(result, 20);
  return result;
}

function invalidIvf(): FfmpegError {
  return new FfmpegError(
    'ffmpeg_invalid_output',
    'FFmpeg produced an incomplete thumbnail sprite bundle.',
    true,
  );
}

async function writeDurablePage(path: string, bytes: Buffer): Promise<void> {
  const handle = await open(path, 'wx', 0o600);
  try {
    await handle.writeFile(bytes);
    await handle.sync();
  } finally {
    await handle.close();
  }
}
