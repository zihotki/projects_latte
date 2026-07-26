import { describe, expect, it, vi } from 'vitest';
import { createPhase4Queues } from '../src/jobs/boss.js';
import { jobNames } from '../src/jobs/job-contracts.js';

describe('phase 4 queues', () => {
  it('creates and reconciles every queue with the desired policy', async () => {
    const createQueue = vi.fn(async () => undefined);
    const updateQueue = vi.fn(async () => undefined);

    await createPhase4Queues({
      createQueue,
      updateQueue,
    } as unknown as Parameters<typeof createPhase4Queues>[0]);

    const options = {
      retryLimit: 5,
      retryDelay: 2,
      retryBackoff: true,
    };
    for (const name of Object.values(jobNames)) {
      expect(createQueue).toHaveBeenCalledWith(name, options);
      expect(updateQueue).toHaveBeenCalledWith(name, options);

      const createCall = createQueue.mock.calls.findIndex(
        ([queueName]) => queueName === name,
      );
      const updateCall = updateQueue.mock.calls.findIndex(
        ([queueName]) => queueName === name,
      );
      expect(createQueue.mock.invocationCallOrder[createCall]).toBeLessThan(
        updateQueue.mock.invocationCallOrder[updateCall]!,
      );
    }
  });
});
