import { EventEmitter } from 'node:events';
import { dirname } from 'node:path';
import {
  jobSnapshotSchema,
  type JobRecord,
  type JobSnapshot,
} from '@cut-on-eight/legacy-contracts';
import type { LibraryRepository } from '../storage/library-repository.js';
import type { StorageLayout } from '../storage/layout.js';
import type { JobRepository } from './job-repository.js';
import {
  ProbeError,
  type ProbeResult,
  type ProbeRunner,
} from './ffprobe-runner.js';
import { FfmpegError } from './ffmpeg-runner.js';
import { thumbnailJobIdentity } from './thumbnail-job.js';
import type { ProjectDocument } from '@cut-on-eight/legacy-contracts';
import {
  ThumbnailGenerationError,
  type ThumbnailGenerator,
} from '../thumbnails/thumbnail-worker.js';

type MetadataUpdater = (
  projectId: string,
  metadata: ProbeResult,
) => Promise<void>;
type ThumbnailJobReconciler = () => Promise<
  readonly JobSnapshot['errors'][number][]
>;
interface ThumbnailContext {
  readonly destinationDirectory: string;
  readonly project: ProjectDocument;
  readonly sourcePath: string;
}
type ThumbnailContextLoader = (projectId: string) => Promise<ThumbnailContext>;

export class JobQueue {
  private activeProjectId: string | undefined;
  private activeThumbnailAbort: AbortController | undefined;
  private recoveryErrors: JobSnapshot['errors'] = [];
  private readonly events = new EventEmitter();
  private readonly blockedProjectIds = new Set<string>();
  private readonly operations = new Set<Promise<unknown>>();
  private reconciliation: Promise<
    readonly JobSnapshot['errors'][number][]
  > | null = null;
  private shuttingDown = false;
  private snapshotValue: JobSnapshot = { jobs: [], errors: [] };
  private worker: Promise<void> | undefined;

  constructor(
    private readonly layout: StorageLayout,
    private readonly library: LibraryRepository,
    private readonly repository: JobRepository,
    private readonly probe: ProbeRunner,
    private readonly updateMetadata: MetadataUpdater,
    private readonly reconcileThumbnailJobs: ThumbnailJobReconciler = async () => [],
    private readonly thumbnailGenerator?: ThumbnailGenerator,
    private readonly loadThumbnailContext?: ThumbnailContextLoader,
  ) {}

  async recover(errors: JobSnapshot['errors'] = []): Promise<void> {
    this.recoveryErrors = [...errors];
    const library = await this.library.read();
    this.setSnapshot(
      this.withRecoveryErrors(
        await this.repository.recoverRunning(library.entries),
      ),
    );
    this.startWorker();
  }

  async enqueueInspection(projectId: string): Promise<JobRecord> {
    const library = await this.library.read();
    const entry = library.entries.find(
      (candidate) => candidate.id === projectId,
    );
    if (entry === undefined) throw new Error('job_project_not_found');
    if (this.blockedProjectIds.has(projectId)) {
      throw new Error('job_project_blocked');
    }
    const source = this.layout.resolveManagedRelativePath(
      entry.managedSourcePath,
    );
    return this.trackOperation(async () => {
      const job = await this.repository.createQueuedInspection(
        projectId,
        dirname(source),
      );
      await this.refresh();
      return job;
    });
  }

  async refresh(): Promise<JobSnapshot> {
    if (this.blockedProjectIds.size === 0) {
      const reconciliation =
        this.reconciliation ??
        this.trackOperation(() => this.reconcileThumbnailJobs());
      this.reconciliation = reconciliation;
      try {
        this.recoveryErrors = [...(await reconciliation)];
      } finally {
        if (this.reconciliation === reconciliation) this.reconciliation = null;
      }
    }
    const library = await this.library.read();
    this.setSnapshot(
      this.withRecoveryErrors(await this.repository.list(library.entries)),
    );
    this.startWorker();
    return this.snapshot();
  }

  async retry(jobId: string): Promise<JobRecord> {
    const library = await this.library.read();
    const current = await this.repository.list(library.entries);
    const existing = current.jobs.find((job) => job.id === jobId);
    if (
      existing !== undefined &&
      this.blockedProjectIds.has(existing.projectId)
    ) {
      throw new Error('job_project_blocked');
    }
    return this.trackOperation(async () => {
      const job = await this.repository.retry(library.entries, jobId);
      await this.refresh();
      return job;
    });
  }

  snapshot(): JobSnapshot {
    return jobSnapshotSchema.parse(this.snapshotValue);
  }

  subscribe(listener: (snapshot: JobSnapshot) => void): () => void {
    this.events.on('jobs', listener);
    return () => this.events.off('jobs', listener);
  }

  isProbeAvailable(): Promise<boolean> {
    return this.probe.isAvailable();
  }

  async waitForIdle(): Promise<void> {
    while (this.worker !== undefined) await this.worker;
  }

  async shutdown(): Promise<void> {
    this.shuttingDown = true;
    this.activeThumbnailAbort?.abort();
    await this.waitForIdle();
  }

  async stopProject(projectId: string): Promise<void> {
    this.blockedProjectIds.add(projectId);
    if (this.activeProjectId === projectId) this.activeThumbnailAbort?.abort();
    await this.waitForOperations();
    await this.waitForIdle();
  }

  resumeProject(projectId: string): void {
    this.blockedProjectIds.delete(projectId);
    this.startWorker();
  }

  private startWorker(): void {
    if (
      this.worker !== undefined ||
      this.shuttingDown ||
      !this.snapshotValue.jobs.some((job) => this.canRun(job))
    ) {
      return;
    }
    const worker = this.runWorker();
    this.worker = worker;
    void worker.then(
      () => {
        this.activeProjectId = undefined;
        if (this.worker === worker) this.worker = undefined;
        if (this.snapshotValue.jobs.some((job) => this.canRun(job))) {
          this.startWorker();
        }
      },
      () => {
        this.activeProjectId = undefined;
        if (this.worker === worker) this.worker = undefined;
        this.setSnapshot({
          ...this.snapshotValue,
          errors: [
            ...this.snapshotValue.errors,
            {
              code: 'job_queue_failed',
              message: 'The background queue could not continue.',
              projectId: null,
            },
          ],
        });
      },
    );
  }

  private trackOperation<T>(operation: () => Promise<T>): Promise<T> {
    const promise = operation();
    this.operations.add(promise);
    void promise.then(
      () => this.operations.delete(promise),
      () => this.operations.delete(promise),
    );
    return promise;
  }

  private async waitForOperations(): Promise<void> {
    while (this.operations.size > 0) {
      const results = await Promise.allSettled([...this.operations]);
      const failed = results.find(
        (result): result is PromiseRejectedResult =>
          result.status === 'rejected',
      );
      if (failed !== undefined) throw failed.reason;
    }
  }

  private async runWorker(): Promise<void> {
    while (true) {
      if (this.shuttingDown) return;

      const library = await this.library.read();
      const current = await this.repository.list(library.entries);
      this.setSnapshot(this.withRecoveryErrors(current));
      const queued = current.jobs.find((job) => this.canRun(job));
      if (queued === undefined) return;

      this.activeProjectId = queued.projectId;
      const running = await this.repository.markRunning(
        library.entries,
        queued,
      );
      await this.publishFresh();
      let completedEntry: (typeof library.entries)[number] | undefined;
      let pausedForShutdown = false;
      let thumbnailAbort: AbortController | undefined;
      try {
        const entry = library.entries.find(
          (candidate) => candidate.id === running.projectId,
        );
        if (entry === undefined) throw new Error('job_project_not_found');
        if (running.type === 'inspect-source') {
          const source = this.layout.resolveManagedRelativePath(
            entry.managedSourcePath,
          );
          await this.layout.assertNoSymlinkComponents(source);
          const metadata = await this.probe.inspect(source);
          await this.updateMetadata(running.projectId, metadata);
          completedEntry = entry;
        } else {
          if (
            this.thumbnailGenerator === undefined ||
            this.loadThumbnailContext === undefined
          ) {
            throw new ThumbnailGenerationError(
              'Thumbnail generation is not configured.',
            );
          }
          const context = await this.loadThumbnailContext(running.projectId);
          await this.layout.assertNoSymlinkComponents(context.sourcePath);
          await this.layout.assertNoSymlinkComponents(
            context.destinationDirectory,
          );
          thumbnailAbort = new AbortController();
          this.activeThumbnailAbort = thumbnailAbort;
          if (this.shuttingDown) thumbnailAbort.abort();
          await this.thumbnailGenerator.generate(
            context.project,
            context.sourcePath,
            context.destinationDirectory,
            {
              generatorVersion: running.generatorVersion,
              sourceFingerprint: running.sourceFingerprint,
            },
            thumbnailAbort.signal,
          );
        }
        await this.repository.markCompleted(library.entries, running);
      } catch (error) {
        pausedForShutdown =
          running.type === 'generate-thumbnails' &&
          this.shuttingDown &&
          thumbnailAbort?.signal.aborted === true;
        if (!pausedForShutdown) {
          await this.repository.markFailed(
            library.entries,
            running,
            this.safeFailure(running.type, error),
          );
        }
      } finally {
        if (this.activeThumbnailAbort === thumbnailAbort) {
          this.activeThumbnailAbort = undefined;
        }
      }
      await this.publishFresh();
      if (pausedForShutdown) return;

      if (
        completedEntry !== undefined &&
        !this.blockedProjectIds.has(running.projectId)
      ) {
        try {
          const source = this.layout.resolveManagedRelativePath(
            completedEntry.managedSourcePath,
          );
          await this.repository.ensureThumbnailJob(
            running.projectId,
            dirname(source),
            thumbnailJobIdentity(completedEntry.fingerprint),
          );
          await this.publishFresh();
        } catch {
          this.setSnapshot({
            ...this.snapshotValue,
            errors: [
              ...this.snapshotValue.errors,
              {
                code: 'thumbnail_queue_failed',
                message: 'Thumbnail generation could not be queued.',
                projectId: running.projectId,
              },
            ],
          });
        }
      }
      this.activeProjectId = undefined;
    }
  }

  private safeFailure(
    jobType: JobRecord['type'],
    error: unknown,
  ): {
    code: string;
    message: string;
    retryable: boolean;
  } {
    if (jobType === 'inspect-source' && error instanceof ProbeError) {
      return {
        code: error.code,
        message: error.message,
        retryable: error.retryable,
      };
    }
    if (
      jobType === 'generate-thumbnails' &&
      (error instanceof FfmpegError ||
        error instanceof ThumbnailGenerationError)
    ) {
      return {
        code: error.code,
        message: error.message,
        retryable: error.retryable,
      };
    }
    return {
      code:
        jobType === 'inspect-source'
          ? 'inspection_failed'
          : 'thumbnail_generation_failed',
      message:
        jobType === 'inspect-source'
          ? 'The managed source could not be inspected.'
          : 'Thumbnail sprites could not be generated safely.',
      retryable: true,
    };
  }

  private canRun(job: JobRecord): boolean {
    return (
      job.state === 'queued' &&
      !this.blockedProjectIds.has(job.projectId) &&
      (job.type === 'inspect-source' || this.thumbnailGenerator !== undefined)
    );
  }

  private async publishFresh(): Promise<void> {
    const library = await this.library.read();
    this.setSnapshot(
      this.withRecoveryErrors(await this.repository.list(library.entries)),
    );
  }

  private withRecoveryErrors(value: JobSnapshot): JobSnapshot {
    return {
      ...value,
      errors: [...value.errors, ...this.recoveryErrors],
    };
  }

  private setSnapshot(value: JobSnapshot): void {
    this.snapshotValue = jobSnapshotSchema.parse(value);
    this.events.emit('jobs', this.snapshot());
  }
}
