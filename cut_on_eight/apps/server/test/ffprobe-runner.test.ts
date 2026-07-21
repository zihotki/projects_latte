import { describe, expect, it } from 'vitest';
import {
  FfprobeRunner,
  ProbeError,
  parseProbeOutput,
} from '../src/jobs/ffprobe-runner.js';

const validOutput = JSON.stringify({
  streams: [
    {
      codec_type: 'video',
      width: 1920,
      height: 1080,
      avg_frame_rate: '30000/1001',
    },
    { codec_type: 'audio' },
  ],
  format: { duration: '12.625' },
});

describe('FFprobe runner', () => {
  it('uses the configured executable with fixed arguments and parses metadata', async () => {
    const calls: Array<{ executable: string; arguments_: readonly string[] }> =
      [];
    const runner = new FfprobeRunner(
      '/opt/tools/ffprobe',
      async (executable, arguments_) => {
        calls.push({ executable, arguments_ });
        return { stdout: validOutput, stderr: '' };
      },
    );

    await expect(runner.inspect('/managed/Dance.mp4')).resolves.toEqual({
      durationSeconds: 12.625,
      width: 1920,
      height: 1080,
      frameRate: '30000/1001',
      hasAudio: true,
    });
    expect(calls).toEqual([
      {
        executable: '/opt/tools/ffprobe',
        arguments_: [
          '-v',
          'error',
          '-print_format',
          'json',
          '-show_format',
          '-show_streams',
          '/managed/Dance.mp4',
        ],
      },
    ]);
  });

  it('rejects malformed JSON and incomplete video metadata safely', () => {
    expect(() => parseProbeOutput('{')).toThrowError(
      expect.objectContaining({ code: 'ffprobe_invalid_output' }),
    );
    expect(() =>
      parseProbeOutput(JSON.stringify({ streams: [], format: {} })),
    ).toThrowError(expect.objectContaining({ code: 'ffprobe_invalid_output' }));
  });

  it('preserves the typed missing-executable failure', async () => {
    const runner = new FfprobeRunner('missing-ffprobe', async () => {
      throw new ProbeError(
        'ffprobe_missing',
        'FFprobe is not installed or cannot be found.',
        true,
      );
    });

    await expect(runner.inspect('/managed/Dance.mp4')).rejects.toMatchObject({
      code: 'ffprobe_missing',
      retryable: true,
    });
    await expect(runner.isAvailable()).resolves.toBe(false);
  });
});
