import {
  createTagRequestSchema,
  deletedFragmentSchema,
  editorVideoSchema,
  fragmentListSchema,
  fragmentPatchRequestSchema,
  fragmentSearchResponseSchema,
  fragmentSchema,
  problemDetailsSchema,
  processingSnapshotSchema,
  restoreFragmentRequestSchema,
  tagListSchema,
  tagSchema,
  uploadAcceptedSchema,
  videoListSchema,
  videoThumbnailManifestSchema,
  workspaceSchema,
  type FragmentDto,
  type FragmentSearchQuery,
  type FragmentSearchResponse,
  type ProcessingSnapshotDto,
  type VideoSummaryDto,
  type VideoThumbnailManifestDto,
} from '@cut-on-eight/api-contracts';
import {
  jobSnapshotSchema,
  type JobSnapshot,
  type ThumbnailManifestV1,
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
import { selectVideoFragmentPreviews } from '../domain/video-fragment-previews.js';

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

export async function loadProcessing(): Promise<ProcessingSnapshotDto> {
  return request('/api/processing', processingSnapshotSchema);
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
  const videoIds = [...new Set(fragments.map(({ videoId }) => videoId))];
  const manifests = new Map(
    await Promise.all(
      videoIds.map(
        async (videoId) =>
          [videoId, await loadCachedVideoThumbnailManifest(videoId)] as const,
      ),
    ),
  );
  return {
    fragments: fragments.map((fragment, index) =>
      toFragmentSummary(
        fragment,
        videos,
        index + 1,
        manifests.get(fragment.videoId) ?? null,
      ),
    ),
    tags,
    diagnostics: [],
  };
}

export function loadTags(): Promise<TagDefinition[]> {
  return request('/api/tags', tagListSchema);
}

export function searchFragments(
  input: FragmentSearchQuery,
  signal?: AbortSignal,
): Promise<FragmentSearchResponse> {
  const query = new URLSearchParams({ q: input.q, limit: String(input.limit) });
  for (const tagId of input.tagIds) query.append('tagIds', tagId);
  for (const collectionId of input.collectionIds)
    query.append('collectionIds', collectionId);
  for (const videoId of input.videoIds) query.append('videoIds', videoId);
  return request(
    `/api/search/fragments?${query}`,
    fragmentSearchResponseSchema,
    {
      signal,
    },
  );
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
  return `/thumbnail-cdn/v1/videos/${encodeURIComponent(projectId)}/${encodeURIComponent(fileName)}?identity=${encodeURIComponent(immutableIdentity)}`;
}

export async function loadThumbnailManifest(
  videoId: string,
): Promise<ThumbnailManifestV1> {
  let response: Response;
  try {
    response = await fetch(
      `/thumbnail-cdn/v1/videos/${encodeURIComponent(videoId)}/manifest.json`,
    );
  } catch {
    throw new ApiFailure({
      status: 503,
      code: 'thumbnail_unavailable',
      message: 'Thumbnail service is unavailable.',
    });
  }
  if (response.status === 404) {
    throw new ApiFailure({
      status: 404,
      code: 'thumbnail_not_ready',
      message: 'Thumbnails are not ready.',
    });
  }
  if (!response.ok) throw invalidResponse();
  const body: unknown = await response.json().catch(() => null);
  const parsed = videoThumbnailManifestSchema.safeParse(body);
  if (!parsed.success) throw invalidResponse();
  return toTimelineManifest(parsed.data, response.headers.get('etag'));
}

const readyManifests = new Map<
  string,
  {
    manifest: ThumbnailManifestV1;
    expiresAt: number;
  }
>();
const pendingManifests = new Map<string, Promise<ThumbnailManifestV1 | null>>();

export function loadCachedVideoThumbnailManifest(
  videoId: string,
): Promise<ThumbnailManifestV1 | null> {
  const cached = readyManifests.get(videoId);
  if (cached !== undefined && cached.expiresAt > Date.now()) {
    return Promise.resolve(cached.manifest);
  }
  const pending = pendingManifests.get(videoId);
  if (pending !== undefined) return pending;
  const request = loadThumbnailManifest(videoId)
    .then((manifest) => {
      readyManifests.set(videoId, {
        manifest,
        expiresAt: Date.now() + 30_000,
      });
      return manifest;
    })
    .catch(() => null)
    .finally(() => pendingManifests.delete(videoId));
  pendingManifests.set(videoId, request);
  return request;
}

function toTimelineManifest(
  manifest: VideoThumbnailManifestDto,
  etag: string | null,
): ThumbnailManifestV1 {
  return {
    ...manifest,
    generatorVersion: manifest.profileVersion,
    sourceFingerprint: etag ?? manifest.profileVersion,
  };
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
  manifest: ThumbnailManifestV1 | null,
): FragmentSummary {
  const video = videos.find(({ id }) => id === fragment.videoId);
  const previews = selectVideoFragmentPreviews(
    manifest,
    toSeconds(fragment.startUs),
    toSeconds(fragment.endUs),
  );
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
    previews: previews.map((preview) => ({
      ...preview,
      href: thumbnailPageUrl(
        fragment.videoId,
        preview.pageFileName,
        preview.identity,
      ),
    })),
    thumbnailState: manifest === null ? 'generating' : 'ready',
    thumbnailJobId: null,
    frameStepSeconds:
      video?.frameRateNumerator && video.frameRateDenominator
        ? video.frameRateDenominator / video.frameRateNumerator
        : 1 / 30,
    frameStepApproximate: video?.frameRateReliability !== 'reliable',
  };
}
