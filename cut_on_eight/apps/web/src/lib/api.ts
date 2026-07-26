import {
  createTagRequestSchema,
  deletedFragmentSchema,
  editorVideoSchema,
  fragmentListSchema,
  fragmentPatchRequestSchema,
  fragmentSchema,
  problemDetailsSchema,
  restoreFragmentRequestSchema,
  tagListSchema,
  tagSchema,
  uploadAcceptedSchema,
  videoListSchema,
  workspaceSchema,
  type FragmentDto,
  type VideoSummaryDto,
} from '@cut-on-eight/api-contracts';
import {
  jobSnapshotSchema,
  type JobSnapshot,
} from '@cut-on-eight/legacy-contracts';
import type {
  DeletedFragment,
  FragmentCatalogue,
  FragmentMutation,
  FragmentSummary,
  TagDefinition,
} from '../domain/catalogue-model.js';
import type {
  ProjectDocument,
  Segment,
  WorkspaceSnapshot,
} from '../domain/editor-model.js';
import {
  toEditorSaveRequest,
  toProjectDocument,
  toSeconds,
  toWorkspaceSnapshot,
} from '../domain/editor-mappers.js';

export class ApiFailure extends Error {
  readonly status: number;
  readonly code: string;
  readonly errors?: Record<string, string[]>;

  constructor(input: {
    status: number;
    code: string;
    message: string;
    errors?: Record<string, string[]>;
  }) {
    super(input.message);
    this.name = 'ApiFailure';
    this.status = input.status;
    this.code = input.code;
    this.errors = input.errors;
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
      status: 503,
      code: 'backend_unavailable',
      message: 'The local backend is unavailable.',
    });
  }
  let body: unknown;
  try {
    body = response.status === 204 ? null : await response.json();
  } catch {
    throw invalidResponse();
  }
  if (!response.ok) {
    const problem = problemDetailsSchema.safeParse(body);
    if (problem.success) {
      throw new ApiFailure({
        status: problem.data.status,
        code: problem.data.code,
        message: problem.data.detail,
        errors: problem.data.errors,
      });
    }
    throw invalidResponse();
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) throw invalidResponse();
  return parsed.data;
}

function invalidResponse(): ApiFailure {
  return new ApiFailure({
    status: 502,
    code: 'invalid_server_response',
    message: 'The local backend returned an invalid response.',
  });
}

const jsonHeaders = { 'content-type': 'application/json' };

export async function loadWorkspace(): Promise<WorkspaceSnapshot> {
  return toWorkspaceSnapshot(await request('/api/workspace', workspaceSchema));
}

export async function importVideo(file: File): Promise<WorkspaceSnapshot> {
  const form = new FormData();
  form.set('source', file, file.name);
  const accepted = await request('/api/videos', uploadAcceptedSchema, {
    method: 'POST',
    body: form,
  });
  return toWorkspaceSnapshot(accepted.workspace);
}

export async function openProject(
  projectId: string,
): Promise<WorkspaceSnapshot> {
  return toWorkspaceSnapshot(
    await request(
      `/api/videos/${encodeURIComponent(projectId)}/open`,
      workspaceSchema,
      { method: 'POST' },
    ),
  );
}

export async function activateProject(
  projectId: string,
): Promise<WorkspaceSnapshot> {
  return toWorkspaceSnapshot(
    await request(
      `/api/videos/${encodeURIComponent(projectId)}/activate`,
      workspaceSchema,
      { method: 'POST' },
    ),
  );
}

export async function saveProject(
  project: ProjectDocument,
): Promise<ProjectDocument> {
  const dto = await request(
    `/api/videos/${encodeURIComponent(project.id)}/editor`,
    editorVideoSchema,
    {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(toEditorSaveRequest(project)),
    },
  );
  return toProjectDocument(dto);
}

export async function closeProject(
  project: ProjectDocument,
): Promise<WorkspaceSnapshot> {
  return toWorkspaceSnapshot(
    await request(
      `/api/videos/${encodeURIComponent(project.id)}/close`,
      workspaceSchema,
      { method: 'POST' },
    ),
  );
}

export async function deleteProject(
  projectId: string,
  expectedRevision: number,
): Promise<WorkspaceSnapshot> {
  return toWorkspaceSnapshot(
    await request(
      `/api/videos/${encodeURIComponent(projectId)}`,
      workspaceSchema,
      {
        method: 'DELETE',
        headers: jsonHeaders,
        body: JSON.stringify({ expectedRevision }),
      },
    ),
  );
}

export async function loadFragments(): Promise<FragmentCatalogue> {
  const [fragments, videos, tags] = await Promise.all([
    request('/api/fragments', fragmentListSchema),
    request('/api/videos', videoListSchema),
    request('/api/tags', tagListSchema),
  ]);
  return {
    fragments: fragments.map((fragment, index) =>
      toFragmentSummary(fragment, videos, index + 1),
    ),
    tags,
    diagnostics: [],
  };
}

export function loadTags(): Promise<TagDefinition[]> {
  return request('/api/tags', tagListSchema);
}

export function createTag(name: string): Promise<TagDefinition> {
  return request('/api/tags', tagSchema, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(createTagRequestSchema.parse({ name })),
  });
}

export async function updateFragment(
  _projectId: string,
  fragmentId: string,
  mutation: FragmentMutation,
  expectedRevision: number,
): Promise<Segment> {
  const dto = await request(
    `/api/fragments/${encodeURIComponent(fragmentId)}`,
    fragmentSchema,
    {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(
        fragmentPatchRequestSchema.parse({
          expectedRevision,
          startUs: Math.round(mutation.startSeconds * 1_000_000),
          endUs: Math.round(mutation.endSeconds * 1_000_000),
          title: mutation.title,
          description: mutation.description ?? null,
          exportSelected: mutation.exportSelected,
          tagIds: mutation.tagIds,
        }),
      ),
    },
  );
  return toSegment(dto);
}

export async function deleteFragment(
  projectId: string,
  fragment: Segment,
  index: number,
): Promise<DeletedFragment> {
  const dto = await request(
    `/api/fragments/${encodeURIComponent(fragment.id)}`,
    deletedFragmentSchema,
    {
      method: 'DELETE',
      headers: jsonHeaders,
      body: JSON.stringify({ expectedRevision: fragment.revision ?? 0 }),
    },
  );
  return {
    projectId,
    index,
    fragment: toSegment(dto.fragment),
    undoToken: dto.undoToken,
    undoUntil: dto.undoUntil,
  };
}

export async function restoreFragment(
  deleted: DeletedFragment,
): Promise<Segment> {
  return toSegment(
    await request(
      `/api/fragments/${encodeURIComponent(deleted.fragment.id)}/restore`,
      fragmentSchema,
      {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify(
          restoreFragmentRequestSchema.parse({ undoToken: deleted.undoToken }),
        ),
      },
    ),
  );
}

export function thumbnailPageUrl(
  projectId: string,
  fileName: string,
  immutableIdentity: string,
): string {
  return `/api/projects/${encodeURIComponent(projectId)}/thumbnails/${encodeURIComponent(fileName)}?identity=${encodeURIComponent(immutableIdentity)}`;
}

/** Legacy event client compatibility; Phase 4 uses processing-record polling. */
export function loadJobs(): Promise<JobSnapshot> {
  return request('/api/jobs', jobSnapshotSchema);
}

function toSegment(fragment: FragmentDto): Segment {
  return {
    id: fragment.id,
    startSeconds: toSeconds(fragment.startUs),
    endSeconds: toSeconds(fragment.endUs),
    exportSelected: fragment.exportSelected,
    title: fragment.title,
    description: fragment.description,
    tagIds: fragment.tags.map(({ id }) => id),
    revision: fragment.revision,
  };
}

function toFragmentSummary(
  fragment: FragmentDto,
  videos: readonly VideoSummaryDto[],
  ordinal: number,
): FragmentSummary {
  const video = videos.find(({ id }) => id === fragment.videoId);
  const preview = fragment.preview;
  return {
    projectId: fragment.videoId,
    sourceFileName: video?.originalFileName ?? 'Video',
    sourceHref: `/api/videos/${encodeURIComponent(fragment.videoId)}/source`,
    sourceDurationSeconds:
      video?.durationUs === null || video?.durationUs === undefined
        ? null
        : toSeconds(video.durationUs),
    ordinal,
    segment: toSegment(fragment),
    previews:
      preview === null
        ? []
        : preview.sampleUs.map((sampleUs, index) => ({
            href: preview.href,
            sampleSeconds: toSeconds(sampleUs),
            pageFileName: `preview-r${preview.revision}.webp`,
            pageWidth: preview.frameWidth * preview.columns,
            pageHeight: preview.frameHeight * preview.rows,
            x: preview.frameWidth * index,
            y: 0,
            width: preview.frameWidth,
            height: preview.frameHeight,
            identity: `${preview.assetId}:${preview.revision}`,
          })),
    thumbnailState:
      fragment.previewState === 'ready'
        ? 'ready'
        : fragment.previewState === 'failed'
          ? 'failed'
          : 'generating',
    thumbnailJobId: null,
    frameStepSeconds:
      video?.frameRateNumerator && video.frameRateDenominator
        ? video.frameRateDenominator / video.frameRateNumerator
        : 1 / 30,
    frameStepApproximate: video?.frameRateReliability !== 'reliable',
  };
}
