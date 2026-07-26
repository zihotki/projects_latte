import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../../catalog/database-types.js';
import {
  loadProjectionWork,
  markProjectionFailed,
  markProjectionReady,
} from '../../search/fragment-projection.js';
import type { FragmentProjectionStore } from '../../search/qdrant-client.js';
import { tracer } from '../../observability/telemetry.js';

export interface ProjectFragmentJob {
  readonly fragmentId: string;
  readonly expectedProjectionRevision: number;
}

export function createProjectFragmentProcessor(
  database: Kysely<CatalogDatabase>,
  store: FragmentProjectionStore,
) {
  return async (job: ProjectFragmentJob): Promise<void> =>
    tracer.startActiveSpan('fragment.project', async (span) => {
      span.setAttribute('fragment.id', job.fragmentId);
      span.setAttribute('projection.revision', job.expectedProjectionRevision);
      try {
        const work = await loadProjectionWork(
          database,
          job.fragmentId,
          job.expectedProjectionRevision,
        );
        if (work.kind === 'skip') return;
        if (work.kind === 'delete') await store.delete(job.fragmentId);
        else await store.upsert(work.point);
        await markProjectionReady(
          database,
          job.fragmentId,
          job.expectedProjectionRevision,
        );
      } catch (error) {
        await markProjectionFailed(
          database,
          job.fragmentId,
          job.expectedProjectionRevision,
        );
        throw error;
      } finally {
        span.end();
      }
    });
}
