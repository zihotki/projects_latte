import { sql, type Kysely } from 'kysely';
import type { Migration } from 'kysely/migration';

export const eventPipelineAndThumbnailsMigration: Migration = {
  async up(database: Kysely<unknown>): Promise<void> {
    await sql`
      create table integration_events (
        position bigint generated always as identity primary key,
        event_id uuid not null unique,
        event_type text not null check (
          event_type ~ '^[a-z][a-z0-9_.]+v[0-9]+$'
        ),
        schema_version smallint not null check (schema_version = 1),
        aggregate_type text not null check (aggregate_type in ('fragment', 'video')),
        aggregate_id uuid not null,
        aggregate_revision integer not null check (aggregate_revision >= 1),
        occurred_at timestamptz not null default now(),
        correlation_id uuid,
        causation_id uuid,
        payload jsonb not null
      )
    `.execute(database);
    await sql`
      create index integration_events_aggregate_order_idx
      on integration_events (aggregate_type, aggregate_id, aggregate_revision)
    `.execute(database);
    await sql`
      create table event_publications (
        event_id uuid not null references integration_events(event_id) on delete restrict,
        destination text not null check (destination = 'jetstream-primary'),
        status text not null check (status in ('pending', 'leased', 'published', 'failed')),
        attempts integer not null default 0 check (attempts >= 0),
        available_at timestamptz not null default now(),
        locked_until timestamptz,
        published_at timestamptz,
        broker_stream text,
        broker_sequence bigint,
        last_error text,
        primary key (event_id, destination)
      )
    `.execute(database);
    await sql`
      create index event_publications_pending_idx
      on event_publications (destination, status, available_at, event_id)
    `.execute(database);
    await sql`
      create table event_replay_runs (
        id uuid primary key,
        start_position bigint not null check (start_position >= 1),
        end_position bigint not null check (end_position >= start_position),
        destination_stream text not null unique,
        purpose text not null check (length(trim(purpose)) between 1 and 120),
        status text not null check (status in ('running', 'completed', 'failed')),
        published_through_position bigint,
        last_error text,
        created_at timestamptz not null default now(),
        completed_at timestamptz
      )
    `.execute(database);
    await sql`
      create table video_thumbnail_state (
        video_id uuid primary key references videos(id) on delete cascade,
        source_asset_id uuid not null references assets(id) on delete cascade,
        profile_version text not null check (length(trim(profile_version)) between 1 and 120),
        storage_key text,
        status text not null check (status in ('pending', 'generating', 'ready', 'failed')),
        manifest jsonb,
        failure_code text check (
          failure_code is null or failure_code ~ '^[a-z][a-z0-9_]*$'
        ),
        updated_at timestamptz not null default now(),
        check (
          (storage_key is null and manifest is null) or
          (storage_key is not null and manifest is not null)
        )
      )
    `.execute(database);
    await sql`
      alter table search_projection_state
      add column last_event_id uuid,
      add column last_aggregate_revision integer,
      add column last_source_position bigint
    `.execute(database);
  },

  async down(database: Kysely<unknown>): Promise<void> {
    await sql`
      alter table search_projection_state
      drop column if exists last_source_position,
      drop column if exists last_aggregate_revision,
      drop column if exists last_event_id
    `.execute(database);
    await sql`drop table if exists video_thumbnail_state cascade`.execute(
      database,
    );
    await sql`drop table if exists event_replay_runs cascade`.execute(database);
    await sql`drop table if exists event_publications cascade`.execute(
      database,
    );
    await sql`drop table if exists integration_events cascade`.execute(
      database,
    );
  },
};
