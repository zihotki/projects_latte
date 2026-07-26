import {
  thumbnailManifestV1Schema,
  type ThumbnailManifestV1,
} from '@cut-on-eight/legacy-contracts';
import { lstat, readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';

export const thumbnailWidth = 160;
export const thumbnailHeight = 90;
export const spriteColumns = 20;
export const spriteRows = 20;
export const spriteCapacity = spriteColumns * spriteRows;

export interface SamplingPlan {
  readonly intervalSeconds: number;
  readonly pageCount: number;
  readonly sampleTimes: readonly number[];
}

export interface ThumbnailCompatibility {
  readonly durationSeconds: number;
  readonly generatorVersion: string;
  readonly sourceFingerprint: string;
}

export function createSamplingPlan(
  durationSeconds: number,
  targetIntervalSeconds = 2,
  maxSamples = 600,
): SamplingPlan {
  if (!Number.isFinite(durationSeconds) || durationSeconds <= 0) {
    throw new TypeError('Source duration must be positive and finite');
  }
  if (!Number.isFinite(targetIntervalSeconds) || targetIntervalSeconds <= 0) {
    throw new TypeError('Target interval must be positive and finite');
  }
  if (!Number.isSafeInteger(maxSamples) || maxSamples <= 0) {
    throw new TypeError('Maximum samples must be a positive integer');
  }

  const targetCount = Math.max(
    1,
    Math.ceil(durationSeconds / targetIntervalSeconds),
  );
  const sampleCount = Math.min(maxSamples, targetCount);
  const intervalSeconds = durationSeconds / sampleCount;
  const sampleTimes = Array.from(
    { length: sampleCount },
    (_, index) => index * intervalSeconds,
  );

  return {
    intervalSeconds,
    pageCount: Math.ceil(sampleCount / spriteCapacity),
    sampleTimes,
  };
}

export function createThumbnailManifest(
  compatibility: ThumbnailCompatibility,
  plan: SamplingPlan,
): ThumbnailManifestV1 {
  const pageWidth = thumbnailWidth * spriteColumns;
  const pageHeight = thumbnailHeight * spriteRows;
  return thumbnailManifestV1Schema.parse({
    schemaVersion: 1,
    ...compatibility,
    thumbnail: [thumbnailWidth, thumbnailHeight],
    pages: Array.from({ length: plan.pageCount }, (_, index) => [
      `sprite-${String(index + 1).padStart(3, '0')}.webp`,
      pageWidth,
      pageHeight,
    ]),
    samples: plan.sampleTimes.map((timeSeconds, index) => {
      const pageCell = index % spriteCapacity;
      return [
        timeSeconds,
        Math.floor(index / spriteCapacity),
        (pageCell % spriteColumns) * thumbnailWidth,
        Math.floor(pageCell / spriteColumns) * thumbnailHeight,
        thumbnailWidth,
        thumbnailHeight,
      ];
    }),
  });
}

export async function readCompatibleThumbnailManifest(
  destinationDirectory: string,
  expected: ThumbnailCompatibility,
): Promise<ThumbnailManifestV1 | undefined> {
  try {
    const directoryStatus = await lstat(destinationDirectory);
    if (!directoryStatus.isDirectory() || directoryStatus.isSymbolicLink()) {
      return undefined;
    }
    const manifestPath = join(destinationDirectory, 'manifest.json');
    const manifestStatus = await lstat(manifestPath);
    if (!manifestStatus.isFile() || manifestStatus.isSymbolicLink()) {
      return undefined;
    }
    const parsed = thumbnailManifestV1Schema.parse(
      JSON.parse(await readFile(manifestPath, 'utf8')),
    );
    if (
      parsed.generatorVersion !== expected.generatorVersion ||
      parsed.sourceFingerprint !== expected.sourceFingerprint ||
      Math.abs(parsed.durationSeconds - expected.durationSeconds) > 0.001
    ) {
      return undefined;
    }

    await Promise.all(
      parsed.pages.map(async ([fileName, width, height]) => {
        const pagePath = join(destinationDirectory, fileName);
        const status = await lstat(pagePath);
        if (!status.isFile() || status.isSymbolicLink()) {
          throw new Error('Sprite page is not a regular managed file');
        }
        const dimensions = parseWebpDimensions(await readFile(pagePath));
        if (dimensions.width !== width || dimensions.height !== height) {
          throw new Error('Sprite dimensions do not match the manifest');
        }
      }),
    );
    const expectedNames = new Set([
      'manifest.json',
      ...parsed.pages.map(([fileName]) => fileName),
    ]);
    const actualNames = await readdir(destinationDirectory);
    if (
      actualNames.length !== expectedNames.size ||
      actualNames.some((name) => !expectedNames.has(name))
    ) {
      return undefined;
    }
    return parsed;
  } catch {
    return undefined;
  }
}

export function parseWebpDimensions(bytes: Uint8Array): {
  readonly height: number;
  readonly width: number;
} {
  const buffer = Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (
    buffer.length < 30 ||
    buffer.toString('ascii', 0, 4) !== 'RIFF' ||
    buffer.toString('ascii', 8, 12) !== 'WEBP' ||
    buffer.readUInt32LE(4) + 8 !== buffer.length
  ) {
    throw new Error('Invalid WebP sprite');
  }

  let extendedDimensions:
    { readonly height: number; readonly width: number } | undefined;
  for (let offset = 12; offset + 8 <= buffer.length;) {
    const type = buffer.toString('ascii', offset, offset + 4);
    const size = buffer.readUInt32LE(offset + 4);
    const data = offset + 8;
    if (data + size > buffer.length) {
      throw new Error('Truncated WebP sprite');
    }

    if (type === 'VP8X' && size >= 10) {
      extendedDimensions = {
        width: 1 + buffer.readUIntLE(data + 4, 3),
        height: 1 + buffer.readUIntLE(data + 7, 3),
      };
    } else if (
      type === 'VP8 ' &&
      size >= 10 &&
      buffer.readUIntLE(data + 3, 3) === 0x2a019d
    ) {
      const dimensions = {
        width: buffer.readUInt16LE(data + 6) & 0x3fff,
        height: buffer.readUInt16LE(data + 8) & 0x3fff,
      };
      if (dimensions.width === 0 || dimensions.height === 0) {
        throw new Error('Invalid WebP sprite dimensions');
      }
      if (
        extendedDimensions !== undefined &&
        (extendedDimensions.width !== dimensions.width ||
          extendedDimensions.height !== dimensions.height)
      ) {
        throw new Error('WebP canvas and image dimensions do not match');
      }
      return extendedDimensions ?? dimensions;
    } else if (type === 'VP8L' && size >= 5 && buffer[data] === 0x2f) {
      const bits = buffer.readUInt32LE(data + 1);
      const dimensions = {
        width: 1 + (bits & 0x3fff),
        height: 1 + ((bits >>> 14) & 0x3fff),
      };
      if (
        extendedDimensions !== undefined &&
        (extendedDimensions.width !== dimensions.width ||
          extendedDimensions.height !== dimensions.height)
      ) {
        throw new Error('WebP canvas and image dimensions do not match');
      }
      return extendedDimensions ?? dimensions;
    }

    offset = data + size + (size % 2);
  }
  throw new Error('Unsupported WebP sprite');
}
