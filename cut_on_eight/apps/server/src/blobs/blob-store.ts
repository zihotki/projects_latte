import type { BlobKey } from './blob-key.js';

export interface StagedBlob {
  readonly key: BlobKey;
  readonly size: number;
  readonly sha256: string;
}

export interface BlobRange {
  readonly stream: NodeJS.ReadableStream;
  readonly size: number;
  readonly start: number;
  readonly endInclusive: number;
}

export interface BlobStore {
  writeStaged(
    source: AsyncIterable<Uint8Array>,
    signal?: AbortSignal,
  ): Promise<StagedBlob>;
  publish(staged: StagedBlob, destination: BlobKey): Promise<void>;
  openRange(
    key: BlobKey,
    range?: { start: number; endInclusive: number },
  ): Promise<BlobRange>;
  stat(key: BlobKey): Promise<{ size: number }>;
  delete(key: BlobKey): Promise<void>;
}

export interface LocalMediaFiles {
  withLocalPath<T>(
    key: BlobKey,
    operation: (path: string) => Promise<T>,
  ): Promise<T>;
}
