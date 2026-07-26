import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';
import {
  loadProjectionWork,
  markProjectionReady,
  projectionVersion,
} from './fragment-projection.js';
import type { FragmentProjectionStore } from './qdrant-client.js';

export async function rebuildFragmentProjection(
  database: Kysely<CatalogDatabase>,
  store: FragmentProjectionStore,
): Promise<number> {
  await store.recreate();
  const states = await database
    .selectFrom('fragments')
    .leftJoin(
      'search_projection_state',
      'search_projection_state.fragment_id',
      'fragments.id',
    )
    .innerJoin('videos', 'videos.id', 'fragments.video_id')
    .select(['fragments.id', 'search_projection_state.projection_revision'])
    .where('fragments.deleted_at', 'is', null)
    .where('videos.status', '!=', 'deleting')
    .orderBy('fragments.id')
    .execute();

  const projected: Array<{ fragmentId: string; revision: number }> = [];
  for (const state of states) {
    const revision = state.projection_revision ?? 1;
    if (state.projection_revision === null) {
      await database
        .insertInto('search_projection_state')
        .values({
          fragment_id: state.id,
          projection_revision: revision,
          projection_version: projectionVersion,
          status: 'pending',
          last_failure_code: null,
        })
        .execute();
    }
    const work = await loadProjectionWork(database, state.id, revision);
    if (work.kind !== 'upsert') continue;
    await store.upsert(work.point);
    projected.push({ fragmentId: state.id, revision });
  }

  const count = await store.count();
  if (count !== projected.length) {
    throw new Error('Qdrant projection count does not match the catalog.');
  }
  await Promise.all(
    projected.map(({ fragmentId, revision }) =>
      markProjectionReady(database, fragmentId, revision),
    ),
  );
  return count;
}
