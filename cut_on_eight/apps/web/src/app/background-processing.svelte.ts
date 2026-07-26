import type {
  Capabilities,
  JobRecord,
  JobSnapshot,
  ThumbnailManifestV1,
} from '@cut-on-eight/legacy-contracts';
import type { BackendState } from './app-status.js';
import type { WorkspaceSnapshot } from '../domain/editor-model.js';
import {
  mergeJobRecord,
  mergeJobSnapshot,
  newestInspectionJob,
  newestThumbnailJob,
  type JobEventConnectionOptions,
} from '../lib/job-events.js';

export interface BackgroundApi {
  loadCapabilities?(): Promise<Capabilities>;
  loadThumbnailManifest?(projectId: string): Promise<ThumbnailManifestV1>;
  retryJob?(jobId: string): Promise<JobRecord>;
  connectJobEvents(options: JobEventConnectionOptions): () => void;
  loadWorkspace?(): Promise<WorkspaceSnapshot>;
  onWorkspace?(snapshot: WorkspaceSnapshot): void;
}

export class BackgroundProcessing {
  jobs = $state.raw<JobSnapshot | null>(null);
  ffprobeState = $state<BackendState>('checking');
  connectionWarning = $state<string | null>(null);
  retryingJobId = $state<string | null>(null);
  errorMessage = $state<string | null>(null);
  thumbnailManifests = $state.raw<Record<string, ThumbnailManifestV1>>({});
  thumbnailLoadErrors = $state<Record<string, string>>({});

  private readonly thumbnailRequestKeys = new Map<string, string>();
  private closeJobEvents: (() => void) | null = null;
  private pollTimer: ReturnType<typeof setTimeout> | null = null;
  private pollInFlight = false;
  private disposed = false;

  constructor(
    private readonly api: BackgroundApi,
    private readonly getActiveProjectId: () => string | null,
  ) {}

  start(): void {
    if (this.disposed) return;
    if (this.api.loadWorkspace !== undefined) {
      this.schedulePoll();
      return;
    }
    this.closeJobEvents?.();
    this.closeJobEvents = this.api.connectJobEvents({
      onSnapshot: (snapshot) => {
        if (this.disposed) return;
        this.jobs = mergeJobSnapshot(this.jobs, snapshot);
        this.requestThumbnails(this.getActiveProjectId());
      },
      onWarning: (warning) => {
        if (!this.disposed) this.connectionWarning = warning;
      },
    });
  }

  async loadToolCapabilities(): Promise<void> {
    try {
      if (this.api.loadCapabilities === undefined) {
        this.ffprobeState = 'ready';
        return;
      }
      const capabilities = await this.api.loadCapabilities();
      if (!this.disposed) {
        this.ffprobeState = capabilities.ffprobeAvailable
          ? 'ready'
          : 'unavailable';
      }
    } catch {
      if (!this.disposed) this.ffprobeState = 'unavailable';
    }
  }

  inspectionJobFor(projectId: string): JobRecord | null {
    return newestInspectionJob(this.jobs, projectId);
  }

  thumbnailJobFor(projectId: string): JobRecord | null {
    return newestThumbnailJob(this.jobs, projectId);
  }

  thumbnailManifestFor(projectId: string): ThumbnailManifestV1 | null {
    return this.thumbnailManifests[projectId] ?? null;
  }

  thumbnailStateFor(projectId: string): 'generating' | 'ready' | 'failed' {
    if (this.thumbnailManifestFor(projectId) !== null) return 'ready';
    const job = this.thumbnailJobFor(projectId);
    return job?.state === 'failed' ||
      this.thumbnailLoadErrors[projectId] !== undefined
      ? 'failed'
      : 'generating';
  }

  requestThumbnails(projectId: string | null): void {
    if (projectId === null) return;
    const job = this.thumbnailJobFor(projectId);
    if (job === null || job.state === 'completed') {
      void this.refreshThumbnailManifest(
        projectId,
        job === null ? 'no-job' : `${job.id}:${job.updatedAt}`,
      );
    }
  }

  async refreshThumbnailManifest(
    projectId: string,
    requestKey: string,
  ): Promise<void> {
    if (this.thumbnailRequestKeys.get(projectId) === requestKey) return;
    this.thumbnailRequestKeys.set(projectId, requestKey);
    try {
      if (this.api.loadThumbnailManifest === undefined) return;
      const manifest = await this.api.loadThumbnailManifest(projectId);
      if (
        this.disposed ||
        this.thumbnailRequestKeys.get(projectId) !== requestKey
      ) {
        return;
      }
      this.thumbnailManifests = {
        ...this.thumbnailManifests,
        [projectId]: manifest,
      };
      this.clearThumbnailError(projectId);
    } catch (error) {
      if (
        this.disposed ||
        this.thumbnailRequestKeys.get(projectId) !== requestKey
      ) {
        return;
      }
      const next = { ...this.thumbnailManifests };
      delete next[projectId];
      this.thumbnailManifests = next;
      if (hasErrorCode(error, 'thumbnail_not_ready')) return;
      this.thumbnailLoadErrors = {
        ...this.thumbnailLoadErrors,
        [projectId]: describeError(error, 'Thumbnails unavailable'),
      };
    }
  }

  async retryThumbnails(projectId: string): Promise<void> {
    if (this.retryingJobId !== null) return;
    const job = this.thumbnailJobFor(projectId);
    if (job?.state === 'failed') {
      await this.retryInspection(job);
      return;
    }
    this.thumbnailRequestKeys.delete(projectId);
    this.clearThumbnailError(projectId);
    await this.refreshThumbnailManifest(projectId, `manual:${Date.now()}`);
  }

  async retryInspection(job: JobRecord): Promise<void> {
    if (this.retryingJobId !== null) return;
    this.retryingJobId = job.id;
    this.errorMessage = null;
    try {
      if (this.api.retryJob === undefined) return;
      const updated = await this.api.retryJob(job.id);
      this.mergeRetriedJob(updated);
    } catch (error) {
      this.errorMessage = describeError(error, 'Could not retry inspection');
    } finally {
      this.retryingJobId = null;
    }
  }

  async retryJobById(jobId: string): Promise<void> {
    if (this.retryingJobId !== null) return;
    this.retryingJobId = jobId;
    try {
      if (this.api.retryJob === undefined) return;
      this.mergeRetriedJob(await this.api.retryJob(jobId));
    } finally {
      this.retryingJobId = null;
    }
  }

  thumbnailPageLoadFailed(projectId: string): void {
    const next = { ...this.thumbnailManifests };
    delete next[projectId];
    this.thumbnailManifests = next;
    this.thumbnailLoadErrors = {
      ...this.thumbnailLoadErrors,
      [projectId]: 'Thumbnail sprites could not be loaded.',
    };
  }

  clearError(): void {
    this.errorMessage = null;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.closeJobEvents?.();
    this.closeJobEvents = null;
    if (this.pollTimer !== null) clearTimeout(this.pollTimer);
    this.pollTimer = null;
    this.thumbnailRequestKeys.clear();
  }

  private mergeRetriedJob(job: JobRecord): void {
    this.jobs =
      this.jobs === null
        ? { jobs: [job], errors: [] }
        : mergeJobRecord(this.jobs, job);
  }

  private clearThumbnailError(projectId: string): void {
    const next = { ...this.thumbnailLoadErrors };
    delete next[projectId];
    this.thumbnailLoadErrors = next;
  }

  private schedulePoll(): void {
    if (
      this.disposed ||
      this.api.loadWorkspace === undefined ||
      this.pollTimer !== null ||
      this.pollInFlight
    ) {
      return;
    }
    this.pollTimer = setTimeout(async () => {
      this.pollTimer = null;
      this.pollInFlight = true;
      let processing = true;
      try {
        const workspace = await this.api.loadWorkspace!();
        if (this.disposed) return;
        processing = workspace.library.some((video) =>
          ['receiving', 'queued', 'processing', 'deleting'].includes(
            video.status ?? '',
          ),
        );
        this.api.onWorkspace?.(workspace);
      } catch {
        // Keep polling after a transient local backend failure.
      } finally {
        this.pollInFlight = false;
        if (!this.disposed && processing) this.schedulePoll();
      }
    }, 1_000);
  }
}

function hasErrorCode(error: unknown, code: string): boolean {
  return (
    error instanceof Error &&
    'code' in error &&
    (error as Error & { code: unknown }).code === code
  );
}

function describeError(error: unknown, action: string): string {
  return error instanceof Error
    ? `${action}: ${error.message}`
    : `${action}: unknown error`;
}
