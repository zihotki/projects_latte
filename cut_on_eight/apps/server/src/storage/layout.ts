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
  readonly libraryFile: string;
  readonly systemDirectory: string;
  readonly workspaceFile: string;

  constructor(dataRoot: string) {
    if (!isAbsolute(dataRoot)) {
      throw new Error('Storage data root must be an absolute path');
    }

    this.dataRoot = resolve(dataRoot);
    this.systemDirectory = resolve(this.dataRoot, '_system');
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
