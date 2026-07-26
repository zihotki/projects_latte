import { Kysely, PostgresDialect } from 'kysely';
import { Pool } from 'pg';
import type { ServerConfig } from '../config.js';
import type { CatalogDatabase } from './database-types.js';

export function createCatalogDatabase(
  config: Pick<ServerConfig, 'databaseUrl'>,
): Kysely<CatalogDatabase> {
  return new Kysely<CatalogDatabase>({
    dialect: new PostgresDialect({
      pool: new Pool({ connectionString: config.databaseUrl }),
    }),
  });
}

export async function closeCatalogDatabase(
  database: Kysely<CatalogDatabase>,
): Promise<void> {
  await database.destroy();
}
