import { EventEmitter } from 'node:events';
import { describe, expect, it, vi } from 'vitest';
import {
  createBoundedFfmpegProcessRunner,
  createFfmpegSpriteArguments,
  FfmpegError,
  webpPagesFromIvf,
} from '../src/jobs/ffmpeg-runner.js';
import {
  createSamplingPlan,
  parseWebpDimensions,
} from '../src/thumbnails/thumbnail-manifest.js';

class FakeProcess extends EventEmitter {
  readonly stderr = new EventEmitter();
  readonly kill = vi.fn(() => true);
}

describe('FFmpeg runner', () => {
  it('constructs fixed VP8 sprite-bundle arguments without a WebP encoder dependency', () => {
    const arguments_ = createFfmpegSpriteArguments(
      {
        sourcePath: '/managed/name; touch nope.mp4',
        destinationDirectory: '/managed/staging',
        plan: createSamplingPlan(20),
      },
      '/managed/staging/.sprites.ivf',
    );

    expect(arguments_).toContain('/managed/name; touch nope.mp4');
    expect(arguments_.at(-1)).toBe('/managed/staging/.sprites.ivf');
    expect(arguments_.join(' ')).toContain('tile=20x20:nb_frames=400');
    expect(arguments_).toContain('libvpx');
    expect(arguments_).not.toContain('libwebp');
  });

  it('wraps every complete IVF keyframe as a standalone WebP page', () => {
    const pages = webpPagesFromIvf(ivf([vp8(3200, 1800), vp8(3200, 1800)]), 2);

    expect(pages).toHaveLength(2);
    expect(pages.map(parseWebpDimensions)).toEqual([
      { width: 3200, height: 1800 },
      { width: 3200, height: 1800 },
    ]);
    expect(() => webpPagesFromIvf(ivf([vp8(3200, 1800)]), 2)).toThrow(
      expect.objectContaining({ code: 'ffmpeg_invalid_output' }),
    );
  });

  it('maps a missing executable without invoking a shell', async () => {
    const child = new FakeProcess();
    let options: unknown;
    const run = createBoundedFfmpegProcessRunner(
      100,
      100,
      (_exe, _args, value) => {
        options = value;
        queueMicrotask(() =>
          child.emit(
            'error',
            Object.assign(new Error('missing'), { code: 'ENOENT' }),
          ),
        );
        return child;
      },
    );

    await expect(run('missing-ffmpeg', ['-version'])).rejects.toMatchObject({
      code: 'ffmpeg_missing',
      retryable: true,
    });
    expect(options).toMatchObject({ shell: false });
  });

  it('kills a timed-out process and bounds diagnostics', async () => {
    const timedOut = new FakeProcess();
    const timeoutRun = createBoundedFfmpegProcessRunner(1, 100, () => timedOut);
    await expect(timeoutRun('ffmpeg', [])).rejects.toMatchObject({
      code: 'ffmpeg_timeout',
    });
    expect(timedOut.kill).toHaveBeenCalledWith('SIGKILL');

    const noisy = new FakeProcess();
    const outputRun = createBoundedFfmpegProcessRunner(100, 3, () => noisy);
    const result = outputRun('ffmpeg', []);
    noisy.stderr.emit('data', Buffer.from('noisy'));
    await expect(result).rejects.toEqual(
      expect.objectContaining<FfmpegError>({ code: 'ffmpeg_output_too_large' }),
    );
    expect(noisy.kill).toHaveBeenCalledWith('SIGKILL');
  });

  it('kills active FFmpeg work when shutdown aborts it', async () => {
    const child = new FakeProcess();
    const controller = new AbortController();
    const run = createBoundedFfmpegProcessRunner(100, 100, () => child);
    const result = run('ffmpeg', [], controller.signal);

    controller.abort();

    await expect(result).rejects.toMatchObject({
      code: 'ffmpeg_aborted',
      retryable: true,
    });
    expect(child.kill).toHaveBeenCalledWith('SIGKILL');
  });
});

function vp8(width: number, height: number): Buffer {
  const payload = Buffer.alloc(10);
  payload.writeUIntLE(0x2a019d, 3, 3);
  payload.writeUInt16LE(width, 6);
  payload.writeUInt16LE(height, 8);
  return payload;
}

function ivf(frames: readonly Buffer[]): Buffer {
  const header = Buffer.alloc(32);
  header.write('DKIF', 0, 'ascii');
  header.writeUInt16LE(32, 6);
  header.write('VP80', 8, 'ascii');
  header.writeUInt16LE(3200, 12);
  header.writeUInt16LE(1800, 14);
  header.writeUInt32LE(frames.length, 24);
  return Buffer.concat([
    header,
    ...frames.flatMap((frame, index) => {
      const frameHeader = Buffer.alloc(12);
      frameHeader.writeUInt32LE(frame.length, 0);
      frameHeader.writeBigUInt64LE(BigInt(index), 4);
      return [frameHeader, frame];
    }),
  ]);
}
