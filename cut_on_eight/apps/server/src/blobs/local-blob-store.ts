import { createHash } from 'node:crypto';
import { createReadStream, createWriteStream, type WriteStream } from 'node:fs';
import { mkdir, open, rename, stat as fsStat, unlink } from 'node:fs/promises';
import { dirname, resolve, sep } from 'node:path';
import { v7 as uuidv7 } from 'uuid';
import { blobKey, type BlobKey } from './blob-key.js';
import type {
  BlobRange,
  BlobStore,
  LocalMediaFiles,
  StagedBlob,
} from './blob-store.js';

export class LocalBlobStore implements BlobStore, LocalMediaFiles {
  private readonly root: string;

  constructor(root: string) {
    this.root = resolve(root);
  }

  async writeStaged(
    source: AsyncIterable<Uint8Array>,
    signal?: AbortSignal,
  ): Promise<StagedBlob> {
    const key = blobKey(`incoming/${uuidv7()}.part`);
    const path = this.pathFor(key);
    await mkdir(dirname(path), { recursive: true });
    const handle = await open(path, 'wx');
    const hash = createHash('sha256');
    let size = 0;
    let stream: WriteStream | undefined;
    try {
      stream = createWriteStream('', { fd: handle.fd, autoClose: false });
      for await (const chunk of source) {
        signal?.throwIfAborted();
        hash.update(chunk);
        size += chunk.byteLength;
        if (!stream.write(chunk)) {
          await new Promise<void>((resolveDrain, reject) => {
            stream!.once('drain', resolveDrain);
            stream!.once('error', reject);
          });
        }
      }
      await new Promise<void>((resolveEnd, reject) => {
        stream!.end(resolveEnd);
        stream!.once('error', reject);
      });
      await handle.sync();
      return { key, size, sha256: hash.digest('hex') };
    } catch (error) {
      stream?.destroy();
      await unlink(path).catch(() => undefined);
      throw error;
    } finally {
      await handle.close().catch(() => undefined);
    }
  }

  async publish(staged: StagedBlob, destination: BlobKey): Promise<void> {
    if (!staged.key.startsWith('incoming/')) {
      throw new Error('Only staged blobs can be published');
    }
    const source = this.pathFor(staged.key);
    const target = this.pathFor(destination);
    await mkdir(dirname(target), { recursive: true });
    const reservation = await open(target, 'wx');
    await reservation.close();
    try {
      await rename(source, target);
    } catch (error) {
      await unlink(target).catch(() => undefined);
      throw error;
    }
  }

  async openRange(
    key: BlobKey,
    range?: { start: number; endInclusive: number },
  ): Promise<BlobRange> {
    const path = this.pathFor(key);
    const { size } = await fsStat(path);
    const start = range?.start ?? 0;
    const endInclusive = range?.endInclusive ?? size - 1;
    if (
      !Number.isSafeInteger(start) ||
      !Number.isSafeInteger(endInclusive) ||
      start < 0 ||
      endInclusive < start ||
      endInclusive >= size
    ) {
      throw new RangeError('Blob range is unsatisfiable');
    }
    return {
      stream: createReadStream(path, { start, end: endInclusive }),
      size,
      start,
      endInclusive,
    };
  }

  async stat(key: BlobKey): Promise<{ size: number }> {
    const { size } = await fsStat(this.pathFor(key));
    return { size };
  }

  async delete(key: BlobKey): Promise<void> {
    await unlink(this.pathFor(key)).catch((error: NodeJS.ErrnoException) => {
      if (error.code !== 'ENOENT') throw error;
    });
  }

  async withLocalPath<T>(
    key: BlobKey,
    operation: (path: string) => Promise<T>,
  ): Promise<T> {
    return operation(this.pathFor(key));
  }

  private pathFor(key: BlobKey): string {
    const path = resolve(this.root, ...key.split('/'));
    if (!path.startsWith(`${this.root}${sep}`)) {
      throw new Error('Blob key escapes the data root');
    }
    return path;
  }
}
