import { EventEmitter } from 'node:events';
import { describe, expect, it, vi } from 'vitest';
import {
  createBoundedFfmpegProcessRunner,
  FfmpegError,
  FfmpegRunner,
} from '../src/jobs/ffmpeg-runner.js';
import { createSamplingPlan } from '../src/thumbnails/thumbnail-manifest.js';

class FakeProcess extends EventEmitter {
  readonly stderr = new EventEmitter();
  readonly kill = vi.fn(() => true);
}

describe('FFmpeg runner', () => {
  it('constructs fixed shell-free sprite arguments', async () => {
    const calls: Array<{ executable: string; arguments_: readonly string[] }> =
      [];
    const runner = new FfmpegRunner(
      '/opt/ffmpeg',
      async (executable, arguments_) => {
        calls.push({ executable, arguments_ });
      },
    );

    await runner.generateSprites({
      sourcePath: '/managed/name; touch nope.mp4',
      destinationDirectory: '/managed/staging',
      plan: createSamplingPlan(20),
    });

    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ executable: '/opt/ffmpeg' });
    expect(calls[0]!.arguments_).toContain('/managed/name; touch nope.mp4');
    expect(calls[0]!.arguments_.at(-1)).toBe(
      '/managed/staging/sprite-%03d.webp',
    );
    expect(calls[0]!.arguments_.join(' ')).toContain(
      'tile=20x20:nb_frames=400',
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
