import { randomUUID } from 'node:crypto';
import { mkdir, open, readFile, rename, unlink } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import type { FileHandle } from 'node:fs/promises';

export class CorruptPersistedDataError extends Error {
  readonly code = 'corrupt_persisted_data';
  readonly filePath: string;

  constructor(filePath: string, cause: unknown) {
    super(`Persisted data is invalid: ${filePath}`, { cause });
    this.name = 'CorruptPersistedDataError';
    this.filePath = filePath;
  }
}

function isMissingFile(error: unknown): boolean {
  return (
    error instanceof Error &&
    'code' in error &&
    (error as NodeJS.ErrnoException).code === 'ENOENT'
  );
}

export async function readJsonValidated<T>(
  target: string,
  validate: (value: unknown) => T,
): Promise<T | undefined> {
  let contents: string;

  try {
    contents = await readFile(target, 'utf8');
  } catch (error) {
    if (isMissingFile(error)) {
      return undefined;
    }

    throw error;
  }

  try {
    return validate(JSON.parse(contents));
  } catch (error) {
    if (error instanceof CorruptPersistedDataError) {
      throw error;
    }

    throw new CorruptPersistedDataError(target, error);
  }
}

export async function writeJsonAtomic(
  target: string,
  value: unknown,
): Promise<void> {
  const serialized = JSON.stringify(value, null, 2);

  if (serialized === undefined) {
    throw new TypeError('Atomic JSON value must be serializable');
  }

  const directory = dirname(target);
  const temporaryPath = join(
    directory,
    `.${basename(target)}.${process.pid}.${randomUUID()}.tmp`,
  );
  let temporaryCreated = false;
  let handle: FileHandle | undefined;

  await mkdir(directory, { recursive: true });

  try {
    handle = await open(temporaryPath, 'wx', 0o600);
    temporaryCreated = true;
    await handle.writeFile(`${serialized}\n`, 'utf8');
    await handle.sync();
    await handle.close();
    handle = undefined;
    await rename(temporaryPath, target);
    temporaryCreated = false;
  } catch (error) {
    await handle?.close().catch(() => undefined);

    if (temporaryCreated) {
      await unlink(temporaryPath).catch(() => undefined);
    }

    throw error;
  }
}
