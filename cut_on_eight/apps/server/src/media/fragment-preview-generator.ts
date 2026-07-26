import { spawn } from 'node:child_process';
import type { BlobStore, StagedBlob } from '../blobs/blob-store.js';
import { webpPagesFromIvf } from '../jobs/ffmpeg-runner.js';

export interface GeneratedPreview {
  readonly sampleUs: number[];
  readonly columns: number;
  readonly rows: 1;
  readonly frameWidth: number;
  readonly frameHeight: number;
  readonly staged: StagedBlob;
}

export class FragmentPreviewGenerator {
  constructor(
    private readonly blobs: BlobStore,
    private readonly executable = 'ffmpeg',
  ) {}

  async generate(input: {
    sourcePath: string;
    startUs: number;
    endUs: number;
  }): Promise<GeneratedPreview> {
    const sampleUs = sampleTimes(input.startUs, input.endUs);
    const filter = previewFilter(sampleUs);
    const child = spawn(
      this.executable,
      [
        '-hide_banner',
        '-loglevel',
        'error',
        '-nostdin',
        '-i',
        input.sourcePath,
        '-filter_complex',
        filter,
        '-map',
        '[sheet]',
        '-frames:v',
        '1',
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
        '-f',
        'ivf',
        'pipe:1',
      ],
      { shell: false, stdio: ['ignore', 'pipe', 'pipe'] },
    );
    const stderr: Buffer[] = [];
    child.stderr.on('data', (chunk: Buffer) => {
      if (stderr.reduce((sum, item) => sum + item.length, 0) < 256 * 1024) {
        stderr.push(chunk);
      }
    });
    const processDone = new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        child.kill('SIGKILL');
        reject(new Error('FFmpeg preview generation timed out'));
      }, 120_000);
      timer.unref();
      child.once('error', reject);
      child.once('close', (code) => {
        clearTimeout(timer);
        if (code === 0) resolve();
        else
          reject(
            new Error(
              `FFmpeg preview generation failed: ${Buffer.concat(stderr).toString('utf8').slice(0, 500)}`,
            ),
          );
      });
    });
    const output = collect(child.stdout);
    const [, ivf] = await Promise.all([processDone, output]);
    const webp = webpPagesFromIvf(ivf, 1)[0];
    if (webp === undefined) throw new Error('FFmpeg produced no preview');
    const staged = await this.blobs.writeStaged(
      (async function* () {
        yield webp;
      })(),
    );
    return {
      sampleUs,
      columns: sampleUs.length,
      rows: 1,
      frameWidth: 320,
      frameHeight: 180,
      staged,
    };
  }
}

async function collect(source: AsyncIterable<Uint8Array>): Promise<Buffer> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of source) {
    size += chunk.byteLength;
    if (size > 16 * 1024 * 1024) {
      throw new Error('FFmpeg preview output is too large');
    }
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}

export function sampleTimes(startUs: number, endUs: number): number[] {
  const duration = endUs - startUs;
  return [
    ...new Set(
      [0.1, 0.3, 0.5, 0.7, 0.9].map((ratio) =>
        Math.min(
          endUs - 1,
          startUs + Math.max(0, Math.round(duration * ratio)),
        ),
      ),
    ),
  ];
}

function previewFilter(sampleUs: readonly number[]): string {
  const outputs = sampleUs.map((_, index) => `[v${index}]`).join('');
  const filters = sampleUs.map((time, index) => {
    const seconds = time / 1_000_000;
    return `[v${index}]trim=start=${seconds}:duration=0.04,setpts=PTS-STARTPTS,scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2[f${index}]`;
  });
  const frames = sampleUs.map((_, index) => `[f${index}]`).join('');
  return [
    `[0:v]split=${sampleUs.length}${outputs}`,
    ...filters,
    `${frames}hstack=inputs=${sampleUs.length}[sheet]`,
  ].join(';');
}
