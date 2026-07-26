import {
  healthLiveSchema,
  problemDetailsSchema,
} from '@cut-on-eight/api-contracts';
import { QdrantClient } from '@qdrant/js-client-rest';
import { sql, type Kysely } from 'kysely';
import type { FastifyInstance, FastifyReply } from 'fastify';
import type { CatalogDatabase } from '../catalog/database-types.js';
import type { ServerConfig } from '../config.js';
import { toReadyDto } from './public-mappers.js';

export interface HealthProbes {
  postgres(): Promise<void>;
  qdrant: (() => Promise<void>) | null;
  worker(): Promise<boolean>;
}

export function createHealthProbes(
  database: Kysely<CatalogDatabase>,
  config: Pick<ServerConfig, 'qdrantHttpUrl' | 'qdrantApiKey'>,
  qdrantProbe?: () => Promise<void>,
): HealthProbes {
  const qdrant =
    qdrantProbe ??
    (config.qdrantHttpUrl === null
      ? null
      : async () => {
          const client = new QdrantClient({
            url: config.qdrantHttpUrl!,
            apiKey: config.qdrantApiKey ?? undefined,
          });
          await client.getCollections();
        });

  return {
    async postgres() {
      await sql`select 1`.execute(database);
    },
    qdrant,
    async worker() {
      const result = await sql<{ ready: boolean }>`
        select exists (
          select 1
          from worker_heartbeats
          where last_seen_at > now() - interval '15 seconds'
        ) as ready
      `.execute(database);
      return result.rows[0]?.ready ?? false;
    },
  };
}

export function registerHealthRoutes(
  app: FastifyInstance,
  probes?: HealthProbes,
): void {
  app.get('/api/health/live', async () =>
    healthLiveSchema.parse({
      status: 'live',
      service: 'cut-on-eight-server',
    }),
  );

  app.get('/api/health/ready', async (request, reply) => {
    if (probes === undefined) {
      return unavailable(reply, request.url);
    }

    try {
      await probes.postgres();
    } catch {
      return unavailable(reply, request.url);
    }

    const [qdrant, worker] = await Promise.all([
      checkQdrant(probes.qdrant),
      probes.worker().catch(() => false),
    ]);

    return toReadyDto({
      postgres: 'ready',
      qdrant,
      worker: worker ? 'ready' : 'unavailable',
    });
  });
}

async function checkQdrant(
  probe: (() => Promise<void>) | null,
): Promise<'ready' | 'degraded' | 'not-configured'> {
  if (probe === null) {
    return 'not-configured';
  }
  try {
    await probe();
    return 'ready';
  } catch {
    return 'degraded';
  }
}

function unavailable(reply: FastifyReply, instance: string) {
  const body = problemDetailsSchema.parse({
    type: 'https://cut-on-eight.local/problems/dependency-unavailable',
    title: 'Required dependency unavailable',
    status: 503,
    detail: 'The catalog database is unavailable.',
    code: 'catalog_unavailable',
    instance,
  });
  return reply.code(503).type('application/problem+json').send(body);
}
