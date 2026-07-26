import {
  ConsecutiveBreaker,
  ExponentialBackoff,
  TimeoutStrategy,
  bulkhead,
  circuitBreaker,
  handleWhen,
  retry,
  timeout,
  wrap,
} from 'cockatiel';
import { resilienceEvents } from '../observability/telemetry.js';

export interface ResilientCall {
  execute<T>(
    operation: (signal: AbortSignal) => Promise<T>,
    signal?: AbortSignal,
  ): Promise<T>;
}

export class RemoteCallError extends Error {
  constructor(
    readonly status: number | null,
    message: string,
  ) {
    super(message);
    this.name = 'RemoteCallError';
  }
}

export interface RemoteCallPolicyOptions {
  readonly maxAttempts?: number;
  readonly initialDelayMs?: number;
  readonly maxDelayMs?: number;
  readonly timeoutMs?: number;
  readonly breakerFailures?: number;
  readonly halfOpenAfterMs?: number;
  readonly concurrentRequests?: number;
  readonly queuedRequests?: number;
}

export function createRemoteCallPolicy(
  options: RemoteCallPolicyOptions = {},
): ResilientCall {
  const handled = handleWhen(
    (error) =>
      error instanceof RemoteCallError &&
      (error.status === null || [429, 502, 503, 504].includes(error.status)),
  );
  const retryPolicy = retry(handled, {
    maxAttempts: options.maxAttempts ?? 3,
    backoff: new ExponentialBackoff({
      initialDelay: options.initialDelayMs ?? 100,
      maxDelay: options.maxDelayMs ?? 1_000,
    }),
  });
  const breakerPolicy = circuitBreaker(handled, {
    breaker: new ConsecutiveBreaker(options.breakerFailures ?? 5),
    halfOpenAfter: options.halfOpenAfterMs ?? 15_000,
  });
  const bulkheadPolicy = bulkhead(
    options.concurrentRequests ?? 8,
    options.queuedRequests ?? 32,
  );

  retryPolicy.onRetry(() =>
    resilienceEvents.add(1, { event: 'retry', policy: 'remote_call' }),
  );
  retryPolicy.onGiveUp(() =>
    resilienceEvents.add(1, { event: 'give_up', policy: 'remote_call' }),
  );
  breakerPolicy.onBreak(() =>
    resilienceEvents.add(1, { event: 'circuit_open', policy: 'remote_call' }),
  );
  breakerPolicy.onReset(() =>
    resilienceEvents.add(1, { event: 'circuit_reset', policy: 'remote_call' }),
  );
  bulkheadPolicy.onReject(() =>
    resilienceEvents.add(1, {
      event: 'bulkhead_reject',
      policy: 'remote_call',
    }),
  );

  const policy = wrap(
    retryPolicy,
    breakerPolicy,
    timeout(options.timeoutMs ?? 3_000, TimeoutStrategy.Aggressive),
    bulkheadPolicy,
  );

  return {
    async execute<T>(
      operation: (signal: AbortSignal) => Promise<T>,
      signal?: AbortSignal,
    ): Promise<T> {
      return policy.execute(
        ({ signal: policySignal }) => operation(policySignal),
        signal,
      );
    },
  };
}
