import { unlink } from 'node:fs/promises';
import { readJsonValidated, writeJsonAtomic } from './atomic-json.js';
import {
  LibraryRepository,
  type LibraryDocument,
  validateLibraryDocument,
} from './library-repository.js';
import type { StorageLayout } from './layout.js';
import { InvalidRepositoryDocumentError } from './repository-errors.js';
import {
  WorkspaceRepository,
  type WorkspaceDocument,
  validateWorkspaceDocument,
} from './workspace-repository.js';

interface Repository<T> {
  read(): Promise<T>;
  save(document: T): Promise<void>;
}

interface CatalogDocuments {
  readonly library: LibraryDocument;
  readonly workspace: WorkspaceDocument;
}

export interface CatalogTransactionDocument {
  readonly after: CatalogDocuments;
  readonly before: CatalogDocuments;
  readonly phase: 'prepared' | 'committed';
  readonly schemaVersion: 1;
}

type RemoveJournal = (path: string) => Promise<void>;

let catalogOperationQueue: Promise<void> = Promise.resolve();

function enqueueCatalogOperation<T>(operation: () => Promise<T>): Promise<T> {
  const result = catalogOperationQueue.then(operation);
  catalogOperationQueue = result.then(
    () => undefined,
    () => undefined,
  );
  return result;
}

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

function validateCatalogDocuments(
  value: unknown,
  layout: StorageLayout,
): CatalogDocuments {
  if (!isRecord(value) || !hasOnlyKeys(value, ['library', 'workspace'])) {
    throw new Error('Catalog transaction documents are invalid');
  }

  return {
    library: validateLibraryDocument(value.library, layout),
    workspace: validateWorkspaceDocument(value.workspace),
  };
}

function validateCatalogTransaction(
  value: unknown,
  layout: StorageLayout,
): CatalogTransactionDocument {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, ['schemaVersion', 'phase', 'before', 'after']) ||
    value.schemaVersion !== 1 ||
    (value.phase !== 'prepared' && value.phase !== 'committed')
  ) {
    throw new Error('Catalog transaction is invalid');
  }

  return {
    schemaVersion: 1,
    phase: value.phase,
    before: validateCatalogDocuments(value.before, layout),
    after: validateCatalogDocuments(value.after, layout),
  };
}

export class CatalogRepository {
  private readonly library: Repository<LibraryDocument>;
  private readonly workspace: Repository<WorkspaceDocument>;

  constructor(
    private readonly layout: StorageLayout,
    library: Repository<LibraryDocument> = new LibraryRepository(layout),
    workspace: Repository<WorkspaceDocument> = new WorkspaceRepository(layout),
    private readonly removeJournalFile: RemoveJournal = unlink,
  ) {
    this.library = library;
    this.workspace = workspace;
  }

  async commit(
    libraryAfter: LibraryDocument,
    workspaceAfter: WorkspaceDocument,
  ): Promise<void> {
    return enqueueCatalogOperation(() =>
      this.commitUnlocked(libraryAfter, workspaceAfter),
    );
  }

  async recover(): Promise<boolean> {
    return enqueueCatalogOperation(() => this.recoverUnlocked());
  }

  private async commitUnlocked(
    libraryAfter: LibraryDocument,
    workspaceAfter: WorkspaceDocument,
  ): Promise<void> {
    let after: CatalogDocuments;

    try {
      after = {
        library: validateLibraryDocument(libraryAfter, this.layout),
        workspace: validateWorkspaceDocument(workspaceAfter),
      };
    } catch (error) {
      throw new InvalidRepositoryDocumentError('catalog', error);
    }

    await this.recoverUnlocked();
    const before = {
      library: await this.library.read(),
      workspace: await this.workspace.read(),
    };
    const transaction = validateCatalogTransaction(
      { schemaVersion: 1, phase: 'prepared', before, after },
      this.layout,
    );

    await this.writeJournal(transaction);

    try {
      await this.library.save(after.library);
      await this.workspace.save(after.workspace);
      await this.writeJournal({ ...transaction, phase: 'committed' });
    } catch (error) {
      try {
        await this.restore(before);
        await this.removeJournal();
      } catch (rollbackError) {
        throw new AggregateError(
          [error, rollbackError],
          'Catalog commit and rollback both failed',
          { cause: rollbackError },
        );
      }

      throw error;
    }

    try {
      await this.removeJournal();
    } catch {
      // The committed journal is deterministic recovery metadata. Cleanup is
      // best-effort after the catalog update has durably succeeded.
    }
  }

  private async recoverUnlocked(): Promise<boolean> {
    await this.layout.assertNoSymlinkComponents(
      this.layout.catalogTransactionFile,
    );
    const transaction = await readJsonValidated(
      this.layout.catalogTransactionFile,
      (value) => validateCatalogTransaction(value, this.layout),
    );

    if (transaction === undefined) {
      return false;
    }

    await this.restore(
      transaction.phase === 'prepared' ? transaction.before : transaction.after,
    );
    await this.removeJournal();
    return true;
  }

  private async removeJournal(): Promise<void> {
    await this.layout.assertNoSymlinkComponents(
      this.layout.catalogTransactionFile,
    );
    await this.removeJournalFile(this.layout.catalogTransactionFile);
  }

  private async writeJournal(
    transaction: CatalogTransactionDocument,
  ): Promise<void> {
    await this.layout.assertNoSymlinkComponents(
      this.layout.catalogTransactionFile,
    );
    await writeJsonAtomic(this.layout.catalogTransactionFile, transaction);
  }

  private async restore(documents: CatalogDocuments): Promise<void> {
    await this.library.save(documents.library);
    await this.workspace.save(documents.workspace);
  }
}
