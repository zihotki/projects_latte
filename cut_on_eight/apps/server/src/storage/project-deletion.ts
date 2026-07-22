import { readdir, rename, rm } from 'node:fs/promises';
import { dirname, posix, resolve } from 'node:path';
import type { CatalogRepository } from './catalog-repository.js';
import type {
  LibraryDocument,
  LibraryEntry,
  LibraryRepository,
} from './library-repository.js';
import type { StorageLayout } from './layout.js';
import type {
  WorkspaceDocument,
  WorkspaceRepository,
} from './workspace-repository.js';

const tombstonePrefix = '.deleting-';

function withoutProject(
  library: LibraryDocument,
  projectId: string,
): LibraryDocument {
  return {
    ...library,
    entries: library.entries.filter((entry) => entry.id !== projectId),
  };
}

function withoutOpenProject(
  workspace: WorkspaceDocument,
  projectId: string,
): WorkspaceDocument {
  const openProjectIds = workspace.openProjectIds.filter(
    (id) => id !== projectId,
  );
  return {
    ...workspace,
    openProjectIds,
    activeProjectId:
      workspace.activeProjectId === projectId
        ? (openProjectIds.at(-1) ?? null)
        : workspace.activeProjectId,
  };
}

export class ProjectDeletion {
  constructor(
    private readonly layout: StorageLayout,
    private readonly library: LibraryRepository,
    private readonly workspace: WorkspaceRepository,
    private readonly catalog: CatalogRepository,
  ) {}

  async delete(entry: LibraryEntry): Promise<void> {
    const [library, workspace] = await Promise.all([
      this.library.read(),
      this.workspace.read(),
    ]);
    if (!library.entries.some((candidate) => candidate.id === entry.id)) return;

    const directory = dirname(
      this.layout.resolveManagedRelativePath(entry.managedSourcePath),
    );
    const relativeDirectory = posix.dirname(entry.managedSourcePath);
    const tombstone = resolve(
      this.layout.dataRoot,
      `${tombstonePrefix}${relativeDirectory}`,
    );
    await this.layout.assertNoSymlinkComponents(directory);
    await this.layout.assertNoSymlinkComponents(tombstone);
    await rename(directory, tombstone);

    try {
      await this.catalog.commit(
        withoutProject(library, entry.id),
        withoutOpenProject(workspace, entry.id),
      );
    } catch (error) {
      await rename(tombstone, directory);
      throw error;
    }

    void rm(tombstone, { recursive: true, force: true }).catch(() => undefined);
  }

  async recover(): Promise<void> {
    await this.catalog.recover();
    const library = await this.library.read();
    const indexedDirectories = new Set(
      library.entries.map((entry) => posix.dirname(entry.managedSourcePath)),
    );
    let names: string[];
    try {
      names = await readdir(this.layout.dataRoot);
    } catch (error) {
      if (error instanceof Error && 'code' in error && error.code === 'ENOENT')
        return;
      throw error;
    }

    for (const name of names.filter((candidate) =>
      candidate.startsWith(tombstonePrefix),
    )) {
      const relativeDirectory = name.slice(tombstonePrefix.length);
      const tombstone = resolve(this.layout.dataRoot, name);
      await this.layout.assertNoSymlinkComponents(tombstone);
      if (indexedDirectories.has(relativeDirectory)) {
        await rename(
          tombstone,
          this.layout.resolveManagedRelativePath(relativeDirectory),
        );
      } else {
        await rm(tombstone, { recursive: true, force: true });
      }
    }
  }
}
