import { afterEach, describe, expect, it, vi } from 'vitest';
import { SaveController, type SaveStatus } from './save-controller.js';

afterEach(() => {
  vi.useRealTimers();
});

function deferred(): {
  promise: Promise<void>;
  resolve: () => void;
  reject: (error: Error) => void;
} {
  let resolve!: () => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<void>((accept, decline) => {
    resolve = accept;
    reject = decline;
  });
  return { promise, resolve, reject };
}

describe('SaveController', () => {
  it('debounces mutations for one second', async () => {
    vi.useFakeTimers();
    const save = vi.fn(async () => undefined);
    const controller = new SaveController({ save });

    controller.markDirty();
    await vi.advanceTimersByTimeAsync(600);
    controller.markDirty();
    await vi.advanceTimersByTimeAsync(999);
    expect(save).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(save).toHaveBeenCalledTimes(1);
    expect(controller.state).toBe('saved');
  });

  it('flushes one pending save immediately', async () => {
    vi.useFakeTimers();
    const save = vi.fn(async () => undefined);
    const controller = new SaveController({ save });

    controller.markDirty();
    await controller.flush();
    await vi.runAllTimersAsync();

    expect(save).toHaveBeenCalledTimes(1);
    expect(controller.state).toBe('saved');
  });

  it('schedules another save when mutation occurs during a save', async () => {
    vi.useFakeTimers();
    const first = deferred();
    const save = vi
      .fn()
      .mockImplementationOnce(() => first.promise)
      .mockResolvedValue(undefined);
    const controller = new SaveController({ save });

    controller.markDirty();
    const flush = controller.flush();
    controller.markDirty();
    first.resolve();
    await flush;

    expect(save).toHaveBeenCalledTimes(1);
    expect(controller.state).toBe('unsaved');
    await vi.advanceTimersByTimeAsync(1_000);
    expect(save).toHaveBeenCalledTimes(2);
    expect(controller.state).toBe('saved');
  });

  it('flushes a revision dirtied during an in-flight save without waiting for debounce', async () => {
    vi.useFakeTimers();
    const first = deferred();
    const second = deferred();
    const save = vi
      .fn()
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);
    const controller = new SaveController({ save });

    controller.markDirty();
    await vi.advanceTimersByTimeAsync(1_000);
    controller.markDirty();
    const flush = controller.flush();

    first.resolve();
    await vi.waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(controller.state).toBe('saving');

    second.resolve();
    await flush;
    expect(controller.state).toBe('saved');
  });

  it('reports failure and allows a later mutation to retry', async () => {
    vi.useFakeTimers();
    const save = vi
      .fn()
      .mockRejectedValueOnce(new Error('disk full'))
      .mockResolvedValue(undefined);
    const statuses: SaveStatus[] = [];
    const controller = new SaveController({
      save,
      onStatusChange: (status) => statuses.push(status),
    });

    controller.markDirty();
    await expect(controller.flush()).rejects.toThrow('disk full');
    expect(controller.state).toBe('failed');
    expect(controller.status.error).toBe('disk full');

    await controller.retry();
    expect(save).toHaveBeenCalledTimes(2);
    expect(controller.state).toBe('saved');
    expect(controller.status.error).toBeNull();
    expect(statuses).toContainEqual({ state: 'failed', error: 'disk full' });
  });

  it('cancels pending work without starting a save', async () => {
    vi.useFakeTimers();
    const save = vi.fn(async () => undefined);
    const controller = new SaveController({ save });

    controller.markDirty();
    controller.cancel();
    await vi.runAllTimersAsync();

    expect(save).not.toHaveBeenCalled();
  });
});
