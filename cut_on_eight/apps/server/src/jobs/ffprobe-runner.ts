import { spawn } from 'node:child_process';

const INSPECT_ARGUMENTS = [
  '-v',
  'error',
  '-print_format',
  'json',
  '-show_format',
  '-show_streams',
] as const;
const MAX_OUTPUT_BYTES = 1024 * 1024;
const DEFAULT_TIMEOUT_MILLISECONDS = 30_000;

export interface ProbeResult {
  readonly durationSeconds: number;
  readonly frameRate: string;
  readonly hasAudio: boolean;
  readonly height: number;
  readonly width: number;
}

export interface ProbeRunner {
  inspect(sourcePath: string): Promise<ProbeResult>;
  isAvailable(): Promise<boolean>;
}

export class ProbeError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = 'ProbeError';
  }
}

interface ProcessResult {
  readonly stderr: string;
  readonly stdout: string;
}

type RunProcess = (
  executable: string,
  arguments_: readonly string[],
) => Promise<ProcessResult>;

function boundedProcessRunner(
  timeoutMilliseconds = DEFAULT_TIMEOUT_MILLISECONDS,
  maxOutputBytes = MAX_OUTPUT_BYTES,
): RunProcess {
  return (executable, arguments_) =>
    new Promise((resolve, reject) => {
      const child = spawn(executable, [...arguments_], {
        shell: false,
        stdio: ['ignore', 'pipe', 'pipe'],
      });
      const stdout: Buffer[] = [];
      const stderr: Buffer[] = [];
      let outputBytes = 0;
      let settled = false;

      const finish = (operation: () => void): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        operation();
      };
      const capture = (chunks: Buffer[], chunk: Buffer): void => {
        outputBytes += chunk.length;
        if (outputBytes > maxOutputBytes) {
          child.kill('SIGKILL');
          finish(() =>
            reject(
              new ProbeError(
                'ffprobe_output_too_large',
                'FFprobe produced too much output.',
                true,
              ),
            ),
          );
          return;
        }
        chunks.push(chunk);
      };

      child.stdout.on('data', (chunk: Buffer) => capture(stdout, chunk));
      child.stderr.on('data', (chunk: Buffer) => capture(stderr, chunk));
      child.once('error', (error: NodeJS.ErrnoException) => {
        finish(() => {
          if (error.code === 'ENOENT') {
            reject(
              new ProbeError(
                'ffprobe_missing',
                'FFprobe is not installed or cannot be found.',
                true,
              ),
            );
          } else {
            reject(
              new ProbeError(
                'ffprobe_failed',
                'FFprobe could not be started.',
                true,
              ),
            );
          }
        });
      });
      child.once('close', (code) => {
        finish(() => {
          const result = {
            stdout: Buffer.concat(stdout).toString('utf8'),
            stderr: Buffer.concat(stderr).toString('utf8'),
          };
          if (code === 0) resolve(result);
          else {
            reject(
              new ProbeError(
                'ffprobe_failed',
                'FFprobe could not inspect the managed source.',
                true,
              ),
            );
          }
        });
      });

      const timeout = setTimeout(() => {
        child.kill('SIGKILL');
        finish(() =>
          reject(
            new ProbeError(
              'ffprobe_timeout',
              'FFprobe did not finish in time.',
              true,
            ),
          ),
        );
      }, timeoutMilliseconds);
      timeout.unref();
    });
}

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function positiveNumber(value: unknown): number | undefined {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function positiveInteger(value: unknown): number | undefined {
  const parsed = positiveNumber(value);
  return parsed !== undefined && Number.isInteger(parsed) ? parsed : undefined;
}

export function parseProbeOutput(output: string): ProbeResult {
  let root: Record<string, unknown> | undefined;
  try {
    root = record(JSON.parse(output));
  } catch {
    // Mapped to the safe format error below.
  }

  const streams = Array.isArray(root?.streams) ? root.streams : [];
  const video = streams
    .map(record)
    .find((stream) => stream?.codec_type === 'video');
  const format = record(root?.format);
  const durationSeconds =
    positiveNumber(video?.duration) ?? positiveNumber(format?.duration);
  const width = positiveInteger(video?.width);
  const height = positiveInteger(video?.height);
  const frameRate = video?.avg_frame_rate;

  if (
    durationSeconds === undefined ||
    width === undefined ||
    height === undefined ||
    typeof frameRate !== 'string' ||
    !/^\d+\/\d+$/.test(frameRate) ||
    frameRate.endsWith('/0')
  ) {
    throw new ProbeError(
      'ffprobe_invalid_output',
      'FFprobe returned invalid source metadata.',
      false,
    );
  }

  return {
    durationSeconds,
    width,
    height,
    frameRate,
    hasAudio: streams.some((stream) => record(stream)?.codec_type === 'audio'),
  };
}

export class FfprobeRunner implements ProbeRunner {
  private availability: boolean | undefined;

  constructor(
    private readonly executable = 'ffprobe',
    private readonly run: RunProcess = boundedProcessRunner(),
  ) {}

  async inspect(sourcePath: string): Promise<ProbeResult> {
    try {
      const result = await this.run(this.executable, [
        ...INSPECT_ARGUMENTS,
        sourcePath,
      ]);
      this.availability = true;
      return parseProbeOutput(result.stdout);
    } catch (error) {
      if (error instanceof ProbeError && error.code === 'ffprobe_missing') {
        this.availability = false;
      }
      throw error;
    }
  }

  async isAvailable(): Promise<boolean> {
    if (this.availability !== undefined) return this.availability;
    try {
      await this.run(this.executable, ['-version']);
      this.availability = true;
    } catch {
      this.availability = false;
    }
    return this.availability;
  }
}
