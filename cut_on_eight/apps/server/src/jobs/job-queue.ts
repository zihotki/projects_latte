import { EventEmitter } from 'node:events';
import { dirname } from 'node:path';
import {
  jobSnapshotSchema,
  type JobRecord,
  type JobSnapshot,
} from '@cut-on-eight/contracts';
import type { LibraryRepository } from '../storage/library-repository.js';
import type { StorageLayout } from '../storage/layout.js';
import type { JobRepository } from './job-repository.js';
import {
  ProbeError,
  type ProbeResult,
  type ProbeRunner,
} from './ffprobe-runner.js';
import { thumbnailJobIdentity } from './thumbnail-job.js';

type MetadataUpdater = (
  projectId: string,
  metadata: ProbeResult,
) => Promise<void>;
type ThumbnailJobReconciler = () => Promise<
  readonly JobSnapshot['errors'][number][]
>;

export class JobQueue {
  private recoveryErrors: JobSnapshot['errors'] = [];
  private readonly events = new EventEmitter();
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
    const source = this.layout.resolveManagedRelativePath(
      entry.managedSourcePath,
    );
    const job = await this.repository.createQueuedInspection(
      projectId,
      dirname(source),
    );
    await this.refresh();
    return job;
  }

  async refresh(): Promise<JobSnapshot> {
    this.recoveryErrors = [...(await this.reconcileThumbnailJobs())];
    const library = await this.library.read();
    this.setSnapshot(
      this.withRecoveryErrors(await this.repository.list(library.entries)),
    );
    this.startWorker();
    return this.snapshot();
  }

  async retry(jobId: string): Promise<JobRecord> {
    const library = await this.library.read();
    const job = await this.repository.retry(library.entries, jobId);
    await this.refresh();
    return job;
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
    await this.waitForIdle();
  }

  private startWorker(): void {
    if (
      this.worker !== undefined ||
      this.shuttingDown ||
      !this.snapshotValue.jobs.some(
        (job) => job.type === 'inspect-source' && job.state === 'queued',
      )
    ) {
      return;
    }
    const worker = this.runWorker();
    this.worker = worker;
    void worker.then(
      () => {
        if (this.worker === worker) this.worker = undefined;
        if (
          this.snapshotValue.jobs.some(
            (job) => job.type === 'inspect-source' && job.state === 'queued',
          )
        ) {
          this.startWorker();
        }
      },
      () => {
        if (this.worker === worker) this.worker = undefined;
        this.setSnapshot({
          ...this.snapshotValue,
          errors: [
            ...this.snapshotValue.errors,
            {
              code: 'job_queue_failed',
              message: 'The inspection queue could not continue.',
              projectId: null,
            },
          ],
        });
      },
    );
  }

  private async runWorker(): Promise<void> {
    while (true) {
      if (this.shuttingDown) return;

      const library = await this.library.read();
      const current = await this.repository.list(library.entries);
      this.setSnapshot(this.withRecoveryErrors(current));
      const queued = current.jobs.find(
        (job) => job.type === 'inspect-source' && job.state === 'queued',
      );
      if (queued === undefined) return;

      const running = await this.repository.markRunning(
        library.entries,
        queued,
      );
      await this.publishFresh();
      let completedEntry: (typeof library.entries)[number] | undefined;
      try {
        const entry = library.entries.find(
          (candidate) => candidate.id === running.projectId,
        );
        if (entry === undefined) throw new Error('job_project_not_found');
        const source = this.layout.resolveManagedRelativePath(
          entry.managedSourcePath,
        );
        await this.layout.assertNoSymlinkComponents(source);
        const metadata = await this.probe.inspect(source);
        await this.updateMetadata(running.projectId, metadata);
        await this.repository.markCompleted(library.entries, running);
        completedEntry = entry;
      } catch (error) {
        await this.repository.markFailed(
          library.entries,
          running,
          this.safeFailure(error),
        );
      }
      await this.publishFresh();

      if (completedEntry !== undefined) {
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
    }
  }

  private safeFailure(error: unknown): {
    code: string;
    message: string;
    retryable: boolean;
  } {
    if (error instanceof ProbeError) {
      return {
        code: error.code,
        message: error.message,
        retryable: error.retryable,
      };
    }
    return {
      code: 'inspection_failed',
      message: 'The managed source could not be inspected.',
      retryable: true,
    };
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
