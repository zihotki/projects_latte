import type { JobSnapshot } from '@cut-on-eight/legacy-contracts';
import { countJobs } from '../lib/job-events.js';

export type BackendState = 'checking' | 'ready' | 'unavailable';

export interface AppStatusInput {
  readonly backendState: BackendState;
  readonly ffprobeState: BackendState;
  readonly importing: boolean;
  readonly busy: boolean;
  readonly jobs: JobSnapshot | null;
  readonly generalError: string | null;
  readonly saveErrors: Readonly<Record<string, string>>;
}

export interface AppStatusSnapshot {
  readonly state: 'ready' | 'working' | 'attention';
  readonly label: 'Ready' | 'Working' | 'Attention';
  readonly jobsLabel: string;
  readonly jobDataWarning: string | null;
}

export function deriveAppStatus(input: AppStatusInput): AppStatusSnapshot {
  const counts = countJobs(input.jobs);
  const jobDataWarning =
    input.jobs !== null && input.jobs.errors.length > 0
      ? `${input.jobs.errors.length} inspection job record${input.jobs.errors.length === 1 ? ' is' : 's are'} unreadable and were left unchanged.`
      : null;
  const jobsLabel =
    counts === null
      ? 'checking'
      : `${counts.queued} queued · ${counts.running} running · ${counts.completed} done · ${counts.failed} failed`;
  const attention =
    input.backendState === 'unavailable' ||
    input.ffprobeState === 'unavailable' ||
    (counts?.failed ?? 0) > 0 ||
    input.generalError !== null ||
    Object.keys(input.saveErrors).length > 0;
  const working =
    input.backendState === 'checking' ||
    input.ffprobeState === 'checking' ||
    input.importing ||
    input.busy ||
    (counts?.queued ?? 0) + (counts?.running ?? 0) > 0;
  const state = attention ? 'attention' : working ? 'working' : 'ready';
  return {
    state,
    label:
      state === 'attention'
        ? 'Attention'
        : state === 'working'
          ? 'Working'
          : 'Ready',
    jobsLabel,
    jobDataWarning,
  };
}
