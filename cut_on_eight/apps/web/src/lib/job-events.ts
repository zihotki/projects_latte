import {
  jobSnapshotSchema,
  type JobRecord,
  type JobSnapshot,
} from '@cut-on-eight/legacy-contracts';
import { loadJobs } from './api.js';

export interface JobCounts {
  queued: number;
  running: number;
  completed: number;
  failed: number;
}

export interface JobEventConnectionOptions {
  onSnapshot: (snapshot: JobSnapshot) => void;
  onWarning: (warning: string | null) => void;
  loadInitial?: () => Promise<JobSnapshot>;
  createEventSource?: (url: string) => EventSource;
}

const stateProgressRank: Record<JobRecord['state'], number> = {
  queued: 0,
  running: 1,
  completed: 2,
  failed: 2,
};

export function parseJobSnapshot(data: string): JobSnapshot | null {
  try {
    const parsed = jobSnapshotSchema.safeParse(JSON.parse(data));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

export function countJobs(snapshot: JobSnapshot | null): JobCounts | null {
  if (snapshot === null) return null;

  const counts: JobCounts = {
    queued: 0,
    running: 0,
    completed: 0,
    failed: 0,
  };
  for (const job of snapshot.jobs) counts[job.state] += 1;
  return counts;
}

export function newestInspectionJob(
  snapshot: JobSnapshot | null,
  projectId: string,
): JobRecord | null {
  let newest: JobRecord | null = null;
  for (const job of snapshot?.jobs ?? []) {
    if (job.projectId !== projectId || job.type !== 'inspect-source') continue;
    if (newest === null || compareJobCreation(job, newest) >= 0) {
      newest = job;
    }
  }
  return newest;
}

export function newestThumbnailJob(
  snapshot: JobSnapshot | null,
  projectId: string,
): JobRecord | null {
  let newest: JobRecord | null = null;
  for (const job of snapshot?.jobs ?? []) {
    if (job.projectId !== projectId || job.type !== 'generate-thumbnails') {
      continue;
    }
    if (newest === null || compareJobCreation(job, newest) >= 0) newest = job;
  }
  return newest;
}

function compareJobCreation(left: JobRecord, right: JobRecord): number {
  const createdDifference =
    Date.parse(left.createdAt) - Date.parse(right.createdAt);
  if (createdDifference !== 0) return createdDifference;

  const updatedDifference =
    Date.parse(left.updatedAt) - Date.parse(right.updatedAt);
  return updatedDifference !== 0
    ? updatedDifference
    : left.id.localeCompare(right.id);
}

export function mergeJobRecord(
  snapshot: JobSnapshot,
  update: JobRecord,
): JobSnapshot {
  return mergeJobSnapshot(snapshot, { jobs: [update], errors: [] });
}

export function mergeJobSnapshot(
  current: JobSnapshot | null,
  incoming: JobSnapshot,
): JobSnapshot {
  if (current === null) return incoming;

  let changed = false;
  const incomingById = new Map(incoming.jobs.map((job) => [job.id, job]));
  const jobs = current.jobs.map((job) => {
    const update = incomingById.get(job.id);
    if (update === undefined) return job;

    incomingById.delete(job.id);
    if (compareJobVersion(update, job) <= 0) return job;

    changed = true;
    return update;
  });

  if (incomingById.size > 0) changed = true;
  jobs.push(...incomingById.values());

  const errors = [...current.errors];
  const knownErrors = new Set(errors.map(jobErrorKey));
  for (const error of incoming.errors) {
    const key = jobErrorKey(error);
    if (knownErrors.has(key)) continue;
    changed = true;
    knownErrors.add(key);
    errors.push(error);
  }

  if (!changed) return current;

  return {
    jobs,
    errors,
  };
}

function compareJobVersion(left: JobRecord, right: JobRecord): number {
  const updatedDifference =
    Date.parse(left.updatedAt) - Date.parse(right.updatedAt);
  if (updatedDifference !== 0) return updatedDifference;

  const attemptDifference = left.attempts - right.attempts;
  if (attemptDifference !== 0) return attemptDifference;

  // Legacy records can share a millisecond. Within one attempt, the durable
  // lifecycle only advances queued -> running -> terminal. Retry cycles need a
  // strictly newer updatedAt because terminal -> queued is otherwise ambiguous.
  return stateProgressRank[left.state] - stateProgressRank[right.state];
}

function jobErrorKey(error: JobSnapshot['errors'][number]): string {
  return `${error.code}\u0000${error.projectId ?? ''}\u0000${error.message}`;
}

export function connectJobEvents(
  options: JobEventConnectionOptions,
): () => void {
  let closed = false;
  let source: EventSource | null = null;
  const loadInitial = options.loadInitial ?? loadJobs;
  const createEventSource =
    options.createEventSource ?? ((url: string) => new EventSource(url));

  void loadInitial()
    .then((snapshot) => {
      if (!closed) options.onSnapshot(jobSnapshotSchema.parse(snapshot));
    })
    .catch(() => {
      if (!closed) {
        options.onWarning(
          'The initial job snapshot could not be loaded. Waiting for live status.',
        );
      }
    })
    .finally(() => {
      if (closed) return;

      try {
        source = createEventSource('/api/events');
      } catch {
        options.onWarning(
          'Live job status is unavailable. The last known status is shown.',
        );
        return;
      }

      source.onopen = () => {
        if (!closed) options.onWarning(null);
      };
      source.onerror = () => {
        if (closed) return;
        options.onWarning(
          'Live job updates are reconnecting. The last known status is shown.',
        );
      };
      source.addEventListener('jobs', (event) => {
        if (closed) return;
        const snapshot = parseJobSnapshot((event as MessageEvent).data);
        if (snapshot === null) {
          options.onWarning(
            'A live job update was invalid. The last known status is shown.',
          );
          return;
        }
        options.onSnapshot(snapshot);
        options.onWarning(null);
      });
    });

  return () => {
    closed = true;
    source?.close();
    source = null;
  };
}
