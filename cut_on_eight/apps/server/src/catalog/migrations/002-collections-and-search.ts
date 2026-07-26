import { sql, type Kysely } from 'kysely';
import type { Migration } from 'kysely/migration';

export const collectionsAndSearchMigration: Migration = {
  async up(database: Kysely<unknown>): Promise<void> {
    await sql`
      create table search_projection_state (
        fragment_id uuid primary key references fragments(id) on delete cascade,
        projection_revision integer not null default 1 check (projection_revision >= 1),
        projection_version integer not null default 1 check (projection_version >= 1),
        status text not null check (status in ('pending', 'ready', 'failed')),
        last_failure_code text check (
          last_failure_code is null or last_failure_code ~ '^[a-z][a-z0-9_]*$'
        ),
        updated_at timestamptz not null default now()
      )
    `.execute(database);
  },

  async down(database: Kysely<unknown>): Promise<void> {
    await sql`drop table if exists search_projection_state cascade`.execute(
      database,
    );
  },
};
