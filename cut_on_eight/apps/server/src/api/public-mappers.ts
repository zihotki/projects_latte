import {
  healthReadySchema,
  type HealthReadyDto,
} from '@cut-on-eight/api-contracts';

export function toReadyDto(input: {
  postgres: 'ready' | 'unavailable';
  qdrant: 'ready' | 'degraded' | 'not-configured';
  worker: 'ready' | 'unavailable';
}): HealthReadyDto {
  return healthReadySchema.parse({
    status: input.postgres === 'ready' ? 'ready' : 'unavailable',
    dependencies: input,
  });
}
