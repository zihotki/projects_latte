import {
  projectDocumentSchema,
  type ProjectDocument,
} from '@cut-on-eight/contracts';
import { posix } from 'node:path';
import { readJsonValidated, writeJsonAtomic } from './atomic-json.js';
import type { StorageLayout } from './layout.js';
import { InvalidRepositoryDocumentError } from './repository-errors.js';

export class MissingProjectSidecarError extends Error {
  readonly code = 'missing_project_sidecar';

  constructor() {
    super('The managed project sidecar is missing');
    this.name = 'MissingProjectSidecarError';
  }
}

function emptyProject(
  projectId: string,
  managedSourceRelativePath: string,
): ProjectDocument {
  return projectDocumentSchema.parse({
    schemaVersion: 1,
    id: projectId,
    source: {
      fileName: posix.basename(managedSourceRelativePath),
      durationSeconds: null,
      width: null,
      height: null,
      frameRate: null,
      hasAudio: null,
    },
    settings: { pauseAfterCreation: false },
    playbackPositionSeconds: 0,
    selectedSegmentId: null,
    segments: [],
    metadata: { title: null, tags: [], notes: null },
  });
}

function parseProject(
  value: unknown,
  projectId: string,
  managedSourceRelativePath: string,
): ProjectDocument {
  const project = projectDocumentSchema.parse(value);

  if (
    project.id !== projectId ||
    project.source.fileName !== posix.basename(managedSourceRelativePath)
  ) {
    throw new Error('Project sidecar does not match its storage location');
  }

  return project;
}

export class ProjectRepository {
  constructor(private readonly layout: StorageLayout) {}

  async read(
    projectId: string,
    managedSourceRelativePath: string,
  ): Promise<ProjectDocument> {
    const sidecar = this.layout.sidecarFile(managedSourceRelativePath);
    await this.layout.assertNoSymlinkComponents(sidecar);
    return (
      (await readJsonValidated(sidecar, (value) =>
        parseProject(value, projectId, managedSourceRelativePath),
      )) ?? emptyProject(projectId, managedSourceRelativePath)
    );
  }

  async readRequired(
    projectId: string,
    managedSourceRelativePath: string,
  ): Promise<ProjectDocument> {
    const sidecar = this.layout.sidecarFile(managedSourceRelativePath);
    await this.layout.assertNoSymlinkComponents(sidecar);
    const project = await readJsonValidated(sidecar, (value) =>
      parseProject(value, projectId, managedSourceRelativePath),
    );

    if (project === undefined) {
      throw new MissingProjectSidecarError();
    }

    return project;
  }

  async save(
    projectId: string,
    managedSourceRelativePath: string,
    document: ProjectDocument,
  ): Promise<void> {
    const sidecar = this.layout.sidecarFile(managedSourceRelativePath);
    let validated: ProjectDocument;

    try {
      validated = parseProject(document, projectId, managedSourceRelativePath);
    } catch (error) {
      throw new InvalidRepositoryDocumentError('project', error);
    }

    await this.layout.assertNoSymlinkComponents(sidecar);
    await this.readExisting(sidecar, projectId, managedSourceRelativePath);
    await this.layout.assertNoSymlinkComponents(sidecar);
    await writeJsonAtomic(sidecar, validated);
  }

  private async readExisting(
    sidecar: string,
    projectId: string,
    managedSourceRelativePath: string,
  ): Promise<void> {
    await readJsonValidated(sidecar, (value) =>
      parseProject(value, projectId, managedSourceRelativePath),
    );
  }
}
