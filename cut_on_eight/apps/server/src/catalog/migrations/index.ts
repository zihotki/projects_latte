import type { MigrationProvider } from 'kysely/migration';
import { Migrator } from 'kysely/migration';
import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../database-types.js';
import { coreCatalogMigration } from './001-core-catalog.js';
import { collectionsAndSearchMigration } from './002-collections-and-search.js';
import { eventPipelineAndThumbnailsMigration } from './003-event-pipeline-and-thumbnails.js';
import { semanticSearchMigration } from './004-semantic-search.js';

export const catalogMigrations: MigrationProvider = {
  async getMigrations() {
    return {
      '001-core-catalog': coreCatalogMigration,
      '002-collections-and-search': collectionsAndSearchMigration,
      '003-event-pipeline-and-thumbnails': eventPipelineAndThumbnailsMigration,
      '004-semantic-search': semanticSearchMigration,
    };
  },
};

export async function migrateCatalog(
  database: Kysely<CatalogDatabase>,
): Promise<void> {
  const { error, results } = await new Migrator({
    db: database,
    provider: catalogMigrations,
  }).migrateToLatest();

  for (const result of results ?? []) {
    console.info(`catalog migration ${result.migrationName}: ${result.status}`);
  }
  if (error !== undefined) {
    throw error;
  }
}
