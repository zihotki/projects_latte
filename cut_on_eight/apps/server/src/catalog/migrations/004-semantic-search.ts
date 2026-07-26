import { sql, type Kysely } from 'kysely';
import type { Migration } from 'kysely/migration';

export const semanticSearchMigration: Migration = {
  async up(database: Kysely<unknown>): Promise<void> {
    await sql`
      create table semantic_search_index_state (
        profile_id text not null,
        fragment_id uuid not null references fragments(id) on delete cascade,
        collection_name text not null,
        fragment_revision integer not null check (fragment_revision >= 1),
        text_hash char(64) not null,
        status text not null check (status in ('pending', 'ready', 'failed')),
        last_event_id uuid,
        last_source_position bigint,
        failure_code text,
        updated_at timestamptz not null default now(),
        primary key (profile_id, fragment_id)
      )
    `.execute(database);
    await sql`
      create index semantic_search_index_state_position_idx
      on semantic_search_index_state (profile_id, last_source_position)
    `.execute(database);
    await sql`
      create table semantic_search_rebuilds (
        id uuid primary key,
        profile_id text not null,
        target_collection_name text not null unique,
        snapshot_high_water_position bigint not null check (
          snapshot_high_water_position >= 0
        ),
        status text not null check (status in ('running', 'ready', 'failed')),
        error_text text,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now()
      )
    `.execute(database);
  },

  async down(database: Kysely<unknown>): Promise<void> {
    await sql`drop table if exists semantic_search_rebuilds cascade`.execute(
      database,
    );
    await sql`drop table if exists semantic_search_index_state cascade`.execute(
      database,
    );
  },
};
