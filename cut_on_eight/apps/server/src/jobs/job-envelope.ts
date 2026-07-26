import {
  context,
  propagation,
  SpanStatusCode,
  trace,
  type Span,
} from '@opentelemetry/api';
import type { Job } from 'pg-boss';

export interface JobEnvelope<T> {
  readonly payload: T;
  readonly traceContext: Record<string, string>;
}

export function envelope<T>(payload: T): JobEnvelope<T> {
  const traceContext: Record<string, string> = {};
  propagation.inject(context.active(), traceContext);
  return { payload, traceContext };
}

export async function inJobSpan<T>(
  name: string,
  job: Job<JobEnvelope<T>>,
  operation: (payload: T, span: Span) => Promise<void>,
): Promise<void> {
  const parent = propagation.extract(context.active(), job.data.traceContext);
  return context.with(parent, async () => {
    const span = trace
      .getTracer('cut-on-eight-worker')
      .startSpan(`job ${name}`);
    try {
      await operation(job.data.payload, span);
      span.setStatus({ code: SpanStatusCode.OK });
    } catch (error) {
      span.recordException(error instanceof Error ? error : String(error));
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}
