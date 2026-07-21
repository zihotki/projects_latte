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
      r_frame_rate: '60000/2002',
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
      frameRateNumerator: 30_000,
      frameRateDenominator: 1_001,
      frameRateReliability: 'reliable',
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

  it('marks mismatched or absent reported frame rates as approximate', () => {
    const output = JSON.parse(validOutput) as {
      streams: Array<Record<string, unknown>>;
    };
    output.streams[0]!.r_frame_rate = '30/1';
    expect(parseProbeOutput(JSON.stringify(output))).toMatchObject({
      frameRateNumerator: 30_000,
      frameRateDenominator: 1_001,
      frameRateReliability: 'approximate',
    });

    delete output.streams[0]!.r_frame_rate;
    expect(parseProbeOutput(JSON.stringify(output))).toMatchObject({
      frameRateReliability: 'approximate',
    });
  });

  it.each([undefined, '0/0', 'unknown'])(
    'keeps usable metadata with missing or invalid average frame rate %s',
    (averageFrameRate) => {
      const output = JSON.parse(validOutput) as {
        streams: Array<Record<string, unknown>>;
      };
      if (averageFrameRate === undefined) {
        delete output.streams[0]!.avg_frame_rate;
      } else {
        output.streams[0]!.avg_frame_rate = averageFrameRate;
      }

      expect(parseProbeOutput(JSON.stringify(output))).toMatchObject({
        durationSeconds: 12.625,
        width: 1920,
        height: 1080,
        frameRateNumerator: null,
        frameRateDenominator: null,
        frameRateReliability: 'approximate',
      });
    },
  );

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
