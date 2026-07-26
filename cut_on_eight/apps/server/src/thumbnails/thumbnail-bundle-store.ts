import { randomUUID } from 'node:crypto';
import { lstat, mkdir, readFile, rename, rm } from 'node:fs/promises';
import { join } from 'node:path';

const bundleName = /^[a-f0-9-]{36}$/;
const pageName = /^sprite-[a-f0-9]{24}-\d+\.webp$/;

export class ThumbnailBundleStore {
  constructor(private readonly root: string) {}

  async createStagingDirectory(): Promise<{ key: string; path: string }> {
    const key = randomUUID();
    const stagingRoot = join(this.root, 'staging');
    await mkdir(stagingRoot, { recursive: true, mode: 0o700 });
    const path = join(stagingRoot, key);
    await mkdir(path, { mode: 0o700 });
    return { key, path };
  }

  async publish(stagingKey: string): Promise<string> {
    assertBundleName(stagingKey);
    const bundlesRoot = join(this.root, 'bundles');
    await mkdir(bundlesRoot, { recursive: true, mode: 0o700 });
    await rename(
      join(this.root, 'staging', stagingKey),
      join(bundlesRoot, stagingKey),
    );
    return stagingKey;
  }

  async discardStaging(stagingKey: string): Promise<void> {
    assertBundleName(stagingKey);
    await rm(join(this.root, 'staging', stagingKey), {
      force: true,
      recursive: true,
    });
  }

  async readPage(storageKey: string, fileName: string): Promise<Buffer | null> {
    assertBundleName(storageKey);
    if (!pageName.test(fileName)) return null;
    const path = join(this.root, 'bundles', storageKey, fileName);
    try {
      const status = await lstat(path);
      if (!status.isFile() || status.isSymbolicLink()) return null;
      return await readFile(path);
    } catch (error) {
      if (isMissing(error)) return null;
      throw error;
    }
  }

  deleteLater(storageKey: string, delayMilliseconds = 60 * 60 * 1_000): void {
    assertBundleName(storageKey);
    const timer = setTimeout(() => {
      void rm(join(this.root, 'bundles', storageKey), {
        force: true,
        recursive: true,
      });
    }, delayMilliseconds);
    timer.unref();
  }
}

function assertBundleName(value: string): void {
  if (!bundleName.test(value)) throw new Error('Invalid thumbnail bundle key');
}

function isMissing(error: unknown): boolean {
  return (
    error instanceof Error &&
    'code' in error &&
    (error as NodeJS.ErrnoException).code === 'ENOENT'
  );
}
