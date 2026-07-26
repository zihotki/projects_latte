import { basename, posix } from 'node:path';

declare const blobKeyBrand: unique symbol;
export type BlobKey = string & { readonly [blobKeyBrand]: true };

const approvedRoots = new Set(['incoming', 'videos']);

export function blobKey(value: string): BlobKey {
  if (
    value.length === 0 ||
    value.includes('\0') ||
    value.includes('\\') ||
    value.startsWith('/') ||
    posix.isAbsolute(value)
  ) {
    throw new Error('Invalid blob key');
  }
  const segments = value.split('/');
  if (
    !approvedRoots.has(segments[0] ?? '') ||
    segments.some(
      (segment) => segment === '' || segment === '.' || segment === '..',
    )
  ) {
    throw new Error('Invalid blob key');
  }
  return value as BlobKey;
}

export function safeFileName(value: string): string {
  const normalized = basename(value.replaceAll('\\', '/'))
    .normalize('NFKC')
    .replaceAll(/[^a-zA-Z0-9._-]/g, '_')
    .replaceAll(/_+/g, '_');
  if (normalized === '' || normalized === '.' || normalized === '..') {
    return 'video.mp4';
  }
  return normalized.slice(0, 180);
}

export const sourceBlobKey = (videoId: string, originalName: string): BlobKey =>
  blobKey(`videos/${videoId}/source/${safeFileName(originalName)}`);

export const previewBlobKey = (
  videoId: string,
  fragmentId: string,
  revision: number,
): BlobKey =>
  blobKey(
    `videos/${videoId}/fragments/${fragmentId}/preview-r${revision}.webp`,
  );
