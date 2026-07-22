import { lstat } from 'node:fs/promises';
import { isAbsolute, posix, relative, resolve, sep } from 'node:path';

export interface ProjectStoragePaths {
  readonly directory: string;
  readonly exportsDirectory: string;
  readonly jobsDirectory: string;
  readonly relativeDirectory: string;
  readonly relativeSource: string;
  readonly sidecar: string;
  readonly source: string;
  readonly thumbnailsDirectory: string;
}

export class UnsafeStoragePathError extends Error {
  readonly code = 'unsafe_storage_path';
  readonly filePath: string;

  constructor(filePath: string, message: string) {
    super(message);
    this.name = 'UnsafeStoragePathError';
    this.filePath = filePath;
  }
}

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function assertUuid(value: string, label: string): void {
  if (!uuidPattern.test(value)) {
    throw new Error(`${label} must be a UUID`);
  }
}

function assertFileName(fileName: string): void {
  if (
    fileName.length === 0 ||
    fileName === '.' ||
    fileName === '..' ||
    fileName.includes('\0') ||
    fileName.includes('/') ||
    fileName.includes('\\') ||
    !fileName.toLowerCase().endsWith('.mp4')
  ) {
    throw new Error('Source filename must be a path-free MP4 filename');
  }
}

function slugify(fileName: string): string {
  const withoutExtension = fileName.replace(/\.mp4$/i, '');
  const slug = withoutExtension
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
    .replace(/-+$/g, '');

  return slug || 'video';
}

export class StorageLayout {
  readonly dataRoot: string;
  readonly catalogTransactionFile: string;
  readonly catalogueMetadataFile: string;
  readonly libraryFile: string;
  readonly systemDirectory: string;
  readonly workspaceFile: string;

  constructor(dataRoot: string) {
    if (!isAbsolute(dataRoot)) {
      throw new Error('Storage data root must be an absolute path');
    }

    this.dataRoot = resolve(dataRoot);
    this.systemDirectory = resolve(this.dataRoot, '_system');
    this.catalogTransactionFile = resolve(
      this.systemDirectory,
      'catalog-transaction.json',
    );
    this.catalogueMetadataFile = resolve(
      this.systemDirectory,
      'catalogue-metadata.json',
    );
    this.libraryFile = resolve(this.systemDirectory, 'library.json');
    this.workspaceFile = resolve(this.systemDirectory, 'workspace.json');
  }

  forProject(projectId: string, sourceFileName: string): ProjectStoragePaths {
    assertUuid(projectId, 'Project ID');
    assertFileName(sourceFileName);

    const shortId = projectId.replaceAll('-', '').slice(0, 8).toLowerCase();
    const relativeDirectory = `${slugify(sourceFileName)}--${shortId}`;
    const relativeSource = posix.join(relativeDirectory, sourceFileName);
    const directory = this.resolveManagedRelativePath(relativeDirectory);
    const source = this.resolveManagedRelativePath(relativeSource);

    return {
      directory,
      exportsDirectory: resolve(directory, 'exports'),
      jobsDirectory: resolve(directory, 'jobs'),
      relativeDirectory,
      relativeSource,
      sidecar: `${source}.danceclips.json`,
      source,
      thumbnailsDirectory: resolve(directory, 'thumbnails'),
    };
  }

  jobFile(managedSourceRelativePath: string, jobId: string): string {
    assertUuid(jobId, 'Job ID');
    const source = this.resolveManagedRelativePath(managedSourceRelativePath);
    return resolve(source, '..', 'jobs', `${jobId}.json`);
  }

  sidecarFile(managedSourceRelativePath: string): string {
    return `${this.resolveManagedRelativePath(managedSourceRelativePath)}.danceclips.json`;
  }

  thumbnailsDirectory(managedSourceRelativePath: string): string {
    const source = this.resolveManagedRelativePath(managedSourceRelativePath);
    return resolve(source, '..', 'thumbnails');
  }

  async assertNoSymlinkComponents(target: string): Promise<void> {
    const absoluteTarget = resolve(target);
    const relativeTarget = relative(this.dataRoot, absoluteTarget);

    if (
      relativeTarget === '..' ||
      relativeTarget.startsWith(`..${sep}`) ||
      isAbsolute(relativeTarget)
    ) {
      throw new UnsafeStoragePathError(
        absoluteTarget,
        'Storage path escapes the data root',
      );
    }

    const components = relativeTarget === '' ? [] : relativeTarget.split(sep);
    let currentPath = this.dataRoot;

    for (const component of ['', ...components]) {
      if (component !== '') {
        currentPath = resolve(currentPath, component);
      }

      try {
        const status = await lstat(currentPath);

        if (status.isSymbolicLink()) {
          throw new UnsafeStoragePathError(
            currentPath,
            'Managed storage paths must not contain symbolic links',
          );
        }
      } catch (error) {
        if (
          error instanceof Error &&
          'code' in error &&
          (error as NodeJS.ErrnoException).code === 'ENOENT'
        ) {
          return;
        }

        throw error;
      }
    }
  }

  resolveManagedRelativePath(storedPath: string): string {
    if (
      storedPath.length === 0 ||
      isAbsolute(storedPath) ||
      storedPath.includes('\\') ||
      storedPath.split('/').includes('..')
    ) {
      throw new Error('Managed path must be a safe relative path');
    }

    const absolutePath = resolve(this.dataRoot, storedPath);
    const relativePath = relative(this.dataRoot, absolutePath);

    if (
      relativePath.length === 0 ||
      relativePath === '..' ||
      relativePath.startsWith(`..${sep}`) ||
      isAbsolute(relativePath)
    ) {
      throw new Error('Managed path escapes the data root');
    }

    return absolutePath;
  }
}
