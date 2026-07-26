import { sql, type Kysely } from 'kysely';
import type { Migration } from 'kysely/migration';

export const coreCatalogMigration: Migration = {
  async up(database: Kysely<unknown>): Promise<void> {
    await sql`
      create table assets (
        id uuid primary key,
        storage_key text not null unique,
        owner_kind text not null check (owner_kind in ('video', 'fragment')),
        owner_id uuid not null,
        kind text not null check (kind in ('source', 'fragment_preview')),
        mime_type text not null,
        size_bytes bigint not null check (size_bytes >= 0),
        sha256 text not null check (length(sha256) = 64),
        revision integer not null default 1 check (revision >= 1),
        state text not null check (state in ('pending', 'ready', 'failed', 'deleting')),
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now()
      )
    `.execute(database);

    await sql`
      create table videos (
        id uuid primary key,
        source_asset_id uuid references assets(id),
        title text not null check (length(trim(title)) between 1 and 240),
        description text check (description is null or length(description) <= 4000),
        original_file_name text not null check (length(original_file_name) > 0),
        duration_us bigint check (duration_us is null or duration_us >= 0),
        width integer check (width is null or width > 0),
        height integer check (height is null or height > 0),
        has_audio boolean,
        status text not null check (
          status in ('receiving', 'queued', 'processing', 'ready', 'failed', 'deleting')
        ),
        revision integer not null default 1 check (revision >= 1),
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now()
      )
    `.execute(database);

    await sql`
      create table fragments (
        id uuid primary key,
        video_id uuid not null references videos(id) on delete cascade,
        start_us bigint not null check (start_us >= 0),
        end_us bigint not null,
        title text check (title is null or length(title) <= 240),
        description text check (description is null or length(description) <= 4000),
        export_selected boolean not null default false,
        revision integer not null default 1 check (revision >= 1),
        deleted_at timestamptz,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now(),
        check (end_us > start_us)
      )
    `.execute(database);

    await sql`
      create table tags (
        id uuid primary key,
        name text not null unique check (
          length(name) between 1 and 80 and name = lower(trim(name))
        ),
        created_at timestamptz not null default now()
      )
    `.execute(database);

    await sql`
      create table video_tags (
        video_id uuid not null references videos(id) on delete cascade,
        tag_id uuid not null references tags(id) on delete cascade,
        primary key (video_id, tag_id)
      )
    `.execute(database);

    await sql`
      create table fragment_tags (
        fragment_id uuid not null references fragments(id) on delete cascade,
        tag_id uuid not null references tags(id) on delete cascade,
        primary key (fragment_id, tag_id)
      )
    `.execute(database);

    await sql`
      create table fragment_previews (
        fragment_id uuid primary key references fragments(id) on delete cascade,
        fragment_revision integer not null check (fragment_revision >= 1),
        asset_id uuid references assets(id),
        status text not null check (status in ('pending', 'ready', 'failed')),
        sample_us bigint[] not null default '{}',
        columns integer not null check (columns > 0),
        rows integer not null check (rows > 0),
        frame_width integer not null check (frame_width > 0),
        frame_height integer not null check (frame_height > 0),
        failure_code text,
        updated_at timestamptz not null default now(),
        check (columns * rows >= cardinality(sample_us))
      )
    `.execute(database);

    await sql`
      create table workspace_state (
        id boolean primary key default true check (id),
        active_video_id uuid references videos(id) on delete set null,
        updated_at timestamptz not null default now()
      )
    `.execute(database);
    await sql`insert into workspace_state (id) values (true)`.execute(database);

    await sql`
      create table workspace_videos (
        video_id uuid primary key references videos(id) on delete cascade,
        position integer not null unique check (position >= 0),
        playback_position_us bigint not null default 0 check (playback_position_us >= 0),
        opened_at timestamptz not null default now()
      )
    `.execute(database);

    await sql`
      create table editor_state (
        video_id uuid primary key references videos(id) on delete cascade,
        selected_fragment_id uuid references fragments(id) on delete set null,
        pause_after_creation boolean not null default false,
        timeline_zoom double precision not null default 1 check (timeline_zoom >= 1),
        timeline_offset_us bigint not null default 0 check (timeline_offset_us >= 0),
        updated_at timestamptz not null default now()
      )
    `.execute(database);

    await sql`
      create table worker_heartbeats (
        worker_id text primary key,
        last_seen_at timestamptz not null
      )
    `.execute(database);

    await sql`create index fragments_video_id_idx on fragments(video_id)`.execute(
      database,
    );
    await sql`create index assets_owner_idx on assets(owner_kind, owner_id)`.execute(
      database,
    );
  },

  async down(database: Kysely<unknown>): Promise<void> {
    for (const table of [
      'worker_heartbeats',
      'editor_state',
      'workspace_videos',
      'workspace_state',
      'fragment_previews',
      'fragment_tags',
      'video_tags',
      'tags',
      'fragments',
      'videos',
      'assets',
    ]) {
      await sql.raw(`drop table if exists ${table} cascade`).execute(database);
    }
  },
};
