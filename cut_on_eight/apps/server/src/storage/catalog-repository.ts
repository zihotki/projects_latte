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
  readonly schemaVersion: 1;
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
    !hasOnlyKeys(value, ['schemaVersion', 'before', 'after']) ||
    value.schemaVersion !== 1
  ) {
    throw new Error('Catalog transaction is invalid');
  }

  return {
    schemaVersion: 1,
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
  ) {
    this.library = library;
    this.workspace = workspace;
  }

  async commit(
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

    await this.recover();
    const before = {
      library: await this.library.read(),
      workspace: await this.workspace.read(),
    };
    const transaction = validateCatalogTransaction(
      { schemaVersion: 1, before, after },
      this.layout,
    );

    await this.layout.assertNoSymlinkComponents(
      this.layout.catalogTransactionFile,
    );
    await writeJsonAtomic(this.layout.catalogTransactionFile, transaction);

    try {
      await this.library.save(after.library);
      await this.workspace.save(after.workspace);
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

    await this.removeJournal();
  }

  async recover(): Promise<boolean> {
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

    await this.restore(transaction.before);
    await this.removeJournal();
    return true;
  }

  private async removeJournal(): Promise<void> {
    await this.layout.assertNoSymlinkComponents(
      this.layout.catalogTransactionFile,
    );
    await unlink(this.layout.catalogTransactionFile);
  }

  private async restore(before: CatalogDocuments): Promise<void> {
    await this.library.save(before.library);
    await this.workspace.save(before.workspace);
  }
}
