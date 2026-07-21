import { isAbsolute } from 'node:path';
import { readJsonValidated, writeJsonAtomic } from './atomic-json.js';
import type { StorageLayout } from './layout.js';
import { InvalidRepositoryDocumentError } from './repository-errors.js';

export interface ImportFingerprint {
  readonly modifiedMilliseconds: number;
  readonly realPath: string;
  readonly size: number;
}

export interface LibraryEntry {
  readonly fingerprint: ImportFingerprint;
  readonly id: string;
  readonly importedAt: string;
  readonly managedSourcePath: string;
}

export interface LibraryDocument {
  readonly entries: LibraryEntry[];
  readonly schemaVersion: 1;
}

const emptyLibrary = (): LibraryDocument => ({
  schemaVersion: 1,
  entries: [],
});

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actualKeys = Object.keys(value);
  return (
    actualKeys.length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

function isNonnegativeFinite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

function parseTimestamp(value: unknown): string {
  if (
    typeof value !== 'string' ||
    Number.isNaN(Date.parse(value)) ||
    new Date(value).toISOString() !== value
  ) {
    throw new Error('Import timestamp must be an ISO timestamp');
  }

  return value;
}

function parseEntry(value: unknown, layout: StorageLayout): LibraryEntry {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, [
      'id',
      'managedSourcePath',
      'fingerprint',
      'importedAt',
    ]) ||
    typeof value.id !== 'string' ||
    !uuidPattern.test(value.id) ||
    typeof value.managedSourcePath !== 'string' ||
    !isRecord(value.fingerprint) ||
    !hasOnlyKeys(value.fingerprint, [
      'realPath',
      'size',
      'modifiedMilliseconds',
    ]) ||
    typeof value.fingerprint.realPath !== 'string' ||
    !isAbsolute(value.fingerprint.realPath) ||
    !Number.isSafeInteger(value.fingerprint.size) ||
    !isNonnegativeFinite(value.fingerprint.size) ||
    !isNonnegativeFinite(value.fingerprint.modifiedMilliseconds)
  ) {
    throw new Error('Library entry is invalid');
  }

  layout.resolveManagedRelativePath(value.managedSourcePath);
  const expectedSourcePath = layout.forProject(
    value.id,
    value.managedSourcePath.split('/').at(-1) ?? '',
  ).relativeSource;

  if (value.managedSourcePath !== expectedSourcePath) {
    throw new Error('Managed source path does not match its project ID');
  }

  return {
    id: value.id,
    managedSourcePath: value.managedSourcePath,
    fingerprint: {
      realPath: value.fingerprint.realPath,
      size: value.fingerprint.size,
      modifiedMilliseconds: value.fingerprint.modifiedMilliseconds,
    },
    importedAt: parseTimestamp(value.importedAt),
  };
}

export function validateLibraryDocument(
  value: unknown,
  layout: StorageLayout,
): LibraryDocument {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, ['schemaVersion', 'entries']) ||
    value.schemaVersion !== 1 ||
    !Array.isArray(value.entries)
  ) {
    throw new Error('Library document is invalid');
  }

  const entries = value.entries.map((entry) => parseEntry(entry, layout));
  const ids = new Set(entries.map((entry) => entry.id));
  const managedPaths = new Set(entries.map((entry) => entry.managedSourcePath));

  if (ids.size !== entries.length || managedPaths.size !== entries.length) {
    throw new Error('Library entries must be unique');
  }

  return { schemaVersion: 1, entries };
}

export class LibraryRepository {
  constructor(private readonly layout: StorageLayout) {}

  async read(): Promise<LibraryDocument> {
    await this.layout.assertNoSymlinkComponents(this.layout.libraryFile);
    return (
      (await readJsonValidated(this.layout.libraryFile, (value) =>
        validateLibraryDocument(value, this.layout),
      )) ?? emptyLibrary()
    );
  }

  async save(document: LibraryDocument): Promise<void> {
    let validated: LibraryDocument;

    try {
      validated = validateLibraryDocument(document, this.layout);
    } catch (error) {
      throw new InvalidRepositoryDocumentError('library', error);
    }

    await this.read();
    await this.layout.assertNoSymlinkComponents(this.layout.libraryFile);
    await writeJsonAtomic(this.layout.libraryFile, validated);
  }
}
