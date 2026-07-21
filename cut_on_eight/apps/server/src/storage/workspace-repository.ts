import { readJsonValidated, writeJsonAtomic } from './atomic-json.js';
import type { StorageLayout } from './layout.js';
import { InvalidRepositoryDocumentError } from './repository-errors.js';

export interface WorkspaceDocument {
  readonly activeProjectId: string | null;
  readonly openProjectIds: string[];
  readonly schemaVersion: 1;
}

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const emptyWorkspace = (): WorkspaceDocument => ({
  schemaVersion: 1,
  openProjectIds: [],
  activeProjectId: null,
});

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function validateWorkspaceDocument(value: unknown): WorkspaceDocument {
  if (
    !isRecord(value) ||
    Object.keys(value).length !== 3 ||
    !Object.hasOwn(value, 'schemaVersion') ||
    !Object.hasOwn(value, 'openProjectIds') ||
    !Object.hasOwn(value, 'activeProjectId') ||
    value.schemaVersion !== 1 ||
    !Array.isArray(value.openProjectIds) ||
    !value.openProjectIds.every(
      (id) => typeof id === 'string' && uuidPattern.test(id),
    ) ||
    !(
      value.activeProjectId === null ||
      (typeof value.activeProjectId === 'string' &&
        uuidPattern.test(value.activeProjectId))
    )
  ) {
    throw new Error('Workspace document is invalid');
  }

  const openProjectIds = [...value.openProjectIds] as string[];
  const uniqueIds = new Set(openProjectIds);

  if (uniqueIds.size !== openProjectIds.length) {
    throw new Error('Open project IDs must be unique');
  }

  if (
    (openProjectIds.length === 0 && value.activeProjectId !== null) ||
    (openProjectIds.length > 0 &&
      (value.activeProjectId === null || !uniqueIds.has(value.activeProjectId)))
  ) {
    throw new Error('Active project must identify an open project');
  }

  return {
    schemaVersion: 1,
    openProjectIds,
    activeProjectId: value.activeProjectId,
  };
}

export class WorkspaceRepository {
  constructor(private readonly layout: StorageLayout) {}

  async read(): Promise<WorkspaceDocument> {
    await this.layout.assertNoSymlinkComponents(this.layout.workspaceFile);
    return (
      (await readJsonValidated(
        this.layout.workspaceFile,
        validateWorkspaceDocument,
      )) ?? emptyWorkspace()
    );
  }

  async save(document: WorkspaceDocument): Promise<void> {
    let validated: WorkspaceDocument;

    try {
      validated = validateWorkspaceDocument(document);
    } catch (error) {
      throw new InvalidRepositoryDocumentError('workspace', error);
    }

    await this.read();
    await this.layout.assertNoSymlinkComponents(this.layout.workspaceFile);
    await writeJsonAtomic(this.layout.workspaceFile, validated);
  }
}
