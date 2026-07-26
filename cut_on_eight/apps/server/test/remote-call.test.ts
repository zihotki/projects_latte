import { describe, expect, it } from 'vitest';
import {
  RemoteCallError,
  createRemoteCallPolicy,
} from '../src/resilience/remote-call.js';

function testPolicy() {
  return createRemoteCallPolicy({
    maxAttempts: 3,
    initialDelayMs: 1,
    maxDelayMs: 2,
    timeoutMs: 100,
  });
}

describe('remote call resilience', () => {
  it('retries a transient failure and then succeeds', async () => {
    let attempts = 0;

    await expect(
      testPolicy().execute(async () => {
        attempts += 1;
        if (attempts === 1) {
          throw new RemoteCallError(503, 'temporarily unavailable');
        }
        return 'ready';
      }),
    ).resolves.toBe('ready');
    expect(attempts).toBe(2);
  });

  it('does not retry a permanent client failure', async () => {
    let attempts = 0;

    await expect(
      testPolicy().execute(async () => {
        attempts += 1;
        throw new RemoteCallError(400, 'bad request');
      }),
    ).rejects.toMatchObject({ status: 400 });
    expect(attempts).toBe(1);
  });

  it('stops an in-flight operation when aborted', async () => {
    const controller = new AbortController();
    const call = testPolicy().execute(
      (signal) =>
        new Promise<void>((_resolve, reject) => {
          signal.addEventListener('abort', () => reject(signal.reason), {
            once: true,
          });
        }),
      controller.signal,
    );

    controller.abort(new Error('cancelled'));

    await expect(call).rejects.toThrow();
  });
});
