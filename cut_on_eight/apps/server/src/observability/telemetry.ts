import { metrics, trace } from '@opentelemetry/api';
export { shutdownTelemetry } from './instrumentation.js';

export const tracer = trace.getTracer('cut-on-eight');
export const meter = metrics.getMeter('cut-on-eight');
export const jobDuration = meter.createHistogram('cut_on_eight.job.duration');
export const searchDuration = meter.createHistogram(
  'cut_on_eight.search.duration',
);
export const resilienceEvents = meter.createCounter(
  'cut_on_eight.resilience.events',
);
