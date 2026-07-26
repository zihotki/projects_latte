import { sql, type Kysely } from 'kysely';
import { Client } from 'pg';
import type { CatalogDatabase } from '../src/catalog/database-types.js';

const suiteLock = 'cut-on-eight-phase4-integration-tests';

export async function acquireDatabaseSuiteLock(
  databaseUrl: string,
): Promise<() => Promise<void>> {
  const client = new Client({ connectionString: databaseUrl });
  await client.connect();
  await client.query('select pg_advisory_lock(hashtextextended($1, 0))', [
    suiteLock,
  ]);
  return async () => {
    await client
      .query('select pg_advisory_unlock(hashtextextended($1, 0))', [suiteLock])
      .finally(() => client.end());
  };
}

export async function resetCatalogTestState(
  database: Kysely<CatalogDatabase>,
): Promise<void> {
  await sql`
    truncate table
      worker_heartbeats,
      editor_state,
      workspace_videos,
      workspace_state,
      fragment_previews,
      fragment_tags,
      video_tags,
      tags,
      fragments,
      videos,
      assets
    cascade
  `.execute(database);
  await sql`insert into workspace_state (id) values (true)`.execute(database);
  await sql`
    do $$
    declare table_name text;
    begin
      foreach table_name in array array[
        'job',
        'archive',
        'schedule',
        'subscription'
      ]
      loop
        if to_regclass('pgboss.' || table_name) is not null then
          execute format('delete from pgboss.%I', table_name);
        end if;
      end loop;
    end
    $$
  `.execute(database);
}
