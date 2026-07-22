import {
  apiErrorSchema,
  capabilitiesSchema,
  importSelectionResponseSchema,
  jobRecordSchema,
  jobSnapshotSchema,
  projectDocumentSchema,
  thumbnailManifestV1Schema,
  workspaceSnapshotSchema,
  type ApiError,
  type Capabilities,
  type ImportSelectionResponse,
  type JobRecord,
  type JobSnapshot,
  type ProjectDocument,
  type ThumbnailManifestV1,
  type WorkspaceSnapshot,
} from '@cut-on-eight/contracts';

export class ApiFailure extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly details?: Readonly<Record<string, unknown>>;

  constructor(error: ApiError['error']) {
    super(error.message);
    this.name = 'ApiFailure';
    this.code = error.code;
    this.retryable = error.retryable;
    this.details = error.details;
  }
}

interface ResponseSchema<T> {
  safeParse(value: unknown): { success: true; data: T } | { success: false };
}

async function request<T>(
  path: string,
  schema: ResponseSchema<T>,
  init?: RequestInit,
): Promise<T> {
  let response: Response;

  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiFailure({
      code: 'backend_unavailable',
      message: 'The local backend is unavailable.',
      retryable: true,
    });
  }

  let body: unknown;

  try {
    body = await response.json();
  } catch {
    throw invalidResponse();
  }

  if (!response.ok) {
    const parsedError = apiErrorSchema.safeParse(body);
    throw parsedError.success
      ? new ApiFailure(parsedError.data.error)
      : invalidResponse();
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw invalidResponse();
  }

  return parsed.data;
}

function invalidResponse(): ApiFailure {
  return new ApiFailure({
    code: 'invalid_server_response',
    message: 'The local backend returned an invalid response.',
    retryable: true,
  });
}

const jsonHeaders = { 'content-type': 'application/json' };

export function loadWorkspace(): Promise<WorkspaceSnapshot> {
  return request('/api/workspace', workspaceSnapshotSchema);
}

export function selectImport(): Promise<ImportSelectionResponse> {
  return request('/api/imports/select', importSelectionResponseSchema, {
    method: 'POST',
  });
}

export function openProject(projectId: string): Promise<WorkspaceSnapshot> {
  return request(
    `/api/projects/${encodeURIComponent(projectId)}/open`,
    workspaceSnapshotSchema,
    { method: 'POST' },
  );
}

export function activateProject(projectId: string): Promise<WorkspaceSnapshot> {
  return request(
    `/api/projects/${encodeURIComponent(projectId)}/activate`,
    workspaceSnapshotSchema,
    { method: 'POST' },
  );
}

export function saveProject(
  project: ProjectDocument,
): Promise<ProjectDocument> {
  return request(
    `/api/projects/${encodeURIComponent(project.id)}`,
    projectDocumentSchema,
    {
      method: 'PUT',
      headers: jsonHeaders,
      body: JSON.stringify(project),
    },
  );
}

export function closeProject(
  project: ProjectDocument,
): Promise<WorkspaceSnapshot> {
  return request(
    `/api/projects/${encodeURIComponent(project.id)}/close`,
    workspaceSnapshotSchema,
    {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(project),
    },
  );
}

export function loadJobs(): Promise<JobSnapshot> {
  return request('/api/jobs', jobSnapshotSchema);
}

export function loadCapabilities(): Promise<Capabilities> {
  return request('/api/capabilities', capabilitiesSchema);
}

export function retryJob(jobId: string): Promise<JobRecord> {
  return request(
    `/api/jobs/${encodeURIComponent(jobId)}/retry`,
    jobRecordSchema,
    {
      method: 'POST',
    },
  );
}

export function sourceUrl(projectId: string): string {
  return `/api/sources/${encodeURIComponent(projectId)}/content`;
}

export function loadThumbnailManifest(
  projectId: string,
): Promise<ThumbnailManifestV1> {
  return request(
    `/api/projects/${encodeURIComponent(projectId)}/thumbnails/manifest`,
    thumbnailManifestV1Schema,
  );
}

export function thumbnailPageUrl(
  projectId: string,
  fileName: string,
  immutableIdentity: string,
): string {
  return `/api/projects/${encodeURIComponent(projectId)}/thumbnails/${encodeURIComponent(fileName)}?identity=${encodeURIComponent(immutableIdentity)}`;
}
