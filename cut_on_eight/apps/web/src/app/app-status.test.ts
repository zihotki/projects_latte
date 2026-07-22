import { describe, expect, it } from 'vitest';
import { deriveAppStatus, type AppStatusInput } from './app-status.js';

const ready: AppStatusInput = {
  backendState: 'ready',
  ffprobeState: 'ready',
  importing: false,
  busy: false,
  jobs: { jobs: [], errors: [] },
  generalError: null,
  saveErrors: {},
};

describe('deriveAppStatus', () => {
  it('reports ready for an idle healthy app', () => {
    expect(deriveAppStatus(ready)).toMatchObject({
      state: 'ready',
      label: 'Ready',
      jobsLabel: '0 queued · 0 running · 0 done · 0 failed',
    });
  });

  it('reports working while an operation is active', () => {
    expect(deriveAppStatus({ ...ready, importing: true }).state).toBe(
      'working',
    );
  });

  it('gives failures precedence over working state', () => {
    expect(
      deriveAppStatus({
        ...ready,
        importing: true,
        generalError: 'failed',
      }).state,
    ).toBe('attention');
  });

  it('describes unreadable job records', () => {
    const status = deriveAppStatus({
      ...ready,
      jobs: {
        jobs: [],
        errors: [{ code: 'corrupt', message: 'bad', projectId: null }],
      },
    });
    expect(status.jobDataWarning).toContain('1 inspection job record is');
  });
});
