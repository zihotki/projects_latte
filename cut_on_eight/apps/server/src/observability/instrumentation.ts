import { FastifyOtelInstrumentation } from '@fastify/otel';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-proto';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto';
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { NodeSDK } from '@opentelemetry/sdk-node';

const fastifyInstrumentation = new FastifyOtelInstrumentation({
  registerOnInitialization: true,
  instrumentHooks: false,
});

export const telemetrySdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter(),
  metricReaders: [
    new PeriodicExportingMetricReader({
      exporter: new OTLPMetricExporter(),
    }),
  ],
  instrumentations: [getNodeAutoInstrumentations(), fastifyInstrumentation],
});

telemetrySdk.start();

let shutdown: Promise<void> | undefined;

export function shutdownTelemetry(): Promise<void> {
  shutdown ??= telemetrySdk.shutdown();
  return shutdown;
}
