import type { MigrationProvider } from 'kysely/migration';
import { Migrator } from 'kysely/migration';
import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../database-types.js';
import { coreCatalogMigration } from './001-core-catalog.js';

export const catalogMigrations: MigrationProvider = {
  async getMigrations() {
    return { '001-core-catalog': coreCatalogMigration };
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
