import { createHash } from 'node:crypto';
import type { ImportFingerprint } from '../storage/library-repository.js';

export const thumbnailGeneratorVersion = 'thumbnail-overview-v1';

export interface ThumbnailJobIdentity {
  readonly generatorVersion: string;
  readonly sourceFingerprint: string;
}

export function thumbnailJobIdentity(
  fingerprint: ImportFingerprint,
): ThumbnailJobIdentity {
  const digest = createHash('sha256')
    .update(
      JSON.stringify([
        fingerprint.realPath,
        fingerprint.size,
        fingerprint.modifiedMilliseconds,
      ]),
    )
    .digest('hex');

  return {
    generatorVersion: thumbnailGeneratorVersion,
    sourceFingerprint: `sha256:${digest}`,
  };
}
