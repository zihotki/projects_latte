import { createHash, randomBytes } from 'node:crypto';
import {
  type EditorSaveRequest,
  type EditorVideoDto,
  type FragmentDto,
  type FragmentPatchRequest,
  type TagDto,
} from '@cut-on-eight/api-contracts';
import { fromKysely, type PgBoss } from 'pg-boss';
import { sql, type Kysely, type Transaction } from 'kysely';
import { v7 as uuidv7 } from 'uuid';
import type { CatalogDatabase } from '../catalog/database-types.js';
import { safeMicroseconds } from '../catalog/database-types.js';
import {
  CatalogNotFound,
  DomainConflict,
  StaleRevision,
} from '../domain/models.js';
import { validateFragmentSet } from '../domain/fragment-timing.js';
import { envelope } from '../jobs/job-envelope.js';
import { jobNames } from '../jobs/job-contracts.js';
import { queueAssetDeletion } from '../jobs/processors/asset-deletion.js';
import { toFragmentDto, toTagDto } from '../api/public-mappers.js';
import { VideoRepository } from '../videos/video-repository.js';
import { WorkspaceService } from '../workspace/workspace-service.js';
import { FragmentRepository } from './fragment-repository.js';

export class FragmentRestoreExpired extends DomainConflict {
  constructor() {
    super('fragment_restore_expired', 'The Undo window has expired.');
  }
}

export class FragmentService {
  constructor(
    private readonly database: Kysely<CatalogDatabase>,
    private readonly boss: PgBoss,
    private readonly workspace: WorkspaceService,
  ) {}

  async list(): Promise<FragmentDto[]> {
    return this.mapMany(new FragmentRepository(this.database));
  }

  async createTag(rawName: string): Promise<TagDto> {
    const name = rawName.trim().toLowerCase();
    if (name.length === 0 || name.length > 80) {
      throw new DomainConflict('validation_failed', 'Tag name is invalid.');
    }
    const row = await this.database
      .insertInto('tags')
      .values({ id: uuidv7(), name })
      .onConflict((conflict) =>
        conflict.column('name').doUpdateSet({ name: sql`excluded.name` }),
      )
      .returning(['id', 'name'])
      .executeTakeFirstOrThrow();
    return toTagDto(row);
  }

  async listTags(): Promise<TagDto[]> {
    const rows = await this.database
      .selectFrom('tags')
      .select(['id', 'name'])
      .orderBy('name')
      .execute();
    return rows.map(toTagDto);
  }

  async saveEditor(
    videoId: string,
    request: EditorSaveRequest,
  ): Promise<EditorVideoDto> {
    await this.database.transaction().execute(async (transaction) => {
      const videos = new VideoRepository(transaction);
      const video = await videos.find(videoId, true);
      if (video === null) throw new CatalogNotFound();
      if (video.revision !== request.expectedVideoRevision)
        throw new StaleRevision();
      await this.assertTags(transaction, request.tagIds);
      for (const fragment of request.fragments)
        await this.assertTags(transaction, fragment.tagIds);

      const existing = await new FragmentRepository(transaction).list(videoId);
      const existingById = new Map(
        existing.map((fragment) => [fragment.id, fragment]),
      );
      const merged = new Map(existingById);
      for (const mutation of request.fragments) {
        const prior = existingById.get(mutation.id);
        if (mutation.expectedRevision === null) {
          if (prior !== undefined) throw new StaleRevision();
          merged.set(mutation.id, {
            id: mutation.id,
            videoId,
            startUs: mutation.startUs,
            endUs: mutation.endUs,
            title: mutation.title,
            description: mutation.description,
            exportSelected: mutation.exportSelected,
            revision: 1,
          });
        } else {
          if (prior === undefined) throw new CatalogNotFound();
          if (prior.revision !== mutation.expectedRevision)
            throw new StaleRevision();
          merged.set(mutation.id, {
            ...prior,
            ...mutation,
            videoId,
            revision: prior.revision + 1,
          });
        }
      }
      validateFragmentSet([...merged.values()], video.durationUs);
      if (
        request.editor.selectedFragmentId !== null &&
        !merged.has(request.editor.selectedFragmentId)
      ) {
        throw new DomainConflict(
          'validation_failed',
          'The selected fragment does not belong to this video.',
        );
      }

      await transaction
        .updateTable('videos')
        .set({
          title: request.title,
          description: request.description,
          revision: video.revision + 1,
          updated_at: new Date(),
        })
        .where('id', '=', videoId)
        .execute();
      await replaceVideoTags(transaction, videoId, request.tagIds);
      await transaction
        .updateTable('workspace_videos')
        .set({ playback_position_us: request.playbackPositionUs })
        .where('video_id', '=', videoId)
        .execute();
      for (const mutation of request.fragments) {
        const prior = existingById.get(mutation.id);
        const timingChanged =
          prior === undefined ||
          prior.startUs !== mutation.startUs ||
          prior.endUs !== mutation.endUs;
        const revision = prior === undefined ? 1 : prior.revision + 1;
        if (prior === undefined) {
          await transaction
            .insertInto('fragments')
            .values({
              id: mutation.id,
              video_id: videoId,
              start_us: mutation.startUs,
              end_us: mutation.endUs,
              title: mutation.title,
              description: mutation.description,
              export_selected: mutation.exportSelected,
            })
            .execute();
        } else {
          await transaction
            .updateTable('fragments')
            .set({
              start_us: mutation.startUs,
              end_us: mutation.endUs,
              title: mutation.title,
              description: mutation.description,
              export_selected: mutation.exportSelected,
              revision,
              updated_at: new Date(),
            })
            .where('id', '=', mutation.id)
            .execute();
        }
        await replaceFragmentTags(transaction, mutation.id, mutation.tagIds);
        if (timingChanged) {
          await upsertPendingPreview(
            transaction,
            this.boss,
            mutation.id,
            revision,
          );
          await this.boss.send(
            jobNames.generateFragmentPreview,
            envelope({
              videoId,
              fragmentId: mutation.id,
              expectedRevision: revision,
            }),
            {
              db: fromKysely(transaction),
              singletonKey: `${mutation.id}:${revision}`,
            },
          );
        }
      }
      await transaction
        .insertInto('editor_state')
        .values({
          video_id: videoId,
          selected_fragment_id: request.editor.selectedFragmentId,
          pause_after_creation: request.editor.pauseAfterCreation,
          timeline_zoom: request.editor.timelineZoom,
          timeline_offset_us: request.editor.timelineOffsetUs,
          updated_at: new Date(),
        })
        .onConflict((conflict) =>
          conflict.column('video_id').doUpdateSet({
            selected_fragment_id: request.editor.selectedFragmentId,
            pause_after_creation: request.editor.pauseAfterCreation,
            timeline_zoom: request.editor.timelineZoom,
            timeline_offset_us: request.editor.timelineOffsetUs,
            updated_at: new Date(),
          }),
        )
        .execute();
    });
    const snapshot = await this.workspace.snapshot();
    const editor = snapshot.openVideos.find(
      ({ video }) => video.id === videoId,
    );
    if (editor === undefined) throw new CatalogNotFound();
    return editor;
  }

  async patch(
    fragmentId: string,
    request: FragmentPatchRequest,
  ): Promise<FragmentDto> {
    await this.database.transaction().execute(async (transaction) => {
      await this.assertTags(transaction, request.tagIds);
      const current = await transaction
        .selectFrom('fragments')
        .selectAll()
        .where('id', '=', fragmentId)
        .where('deleted_at', 'is', null)
        .forUpdate()
        .executeTakeFirst();
      if (current === undefined) throw new CatalogNotFound();
      if (current.revision !== request.expectedRevision)
        throw new StaleRevision();
      const all = await new FragmentRepository(transaction).list(
        current.video_id,
      );
      validateFragmentSet(
        all.map((fragment) =>
          fragment.id === fragmentId
            ? { id: fragmentId, startUs: request.startUs, endUs: request.endUs }
            : fragment,
        ),
        (await new VideoRepository(transaction).find(current.video_id))
          ?.durationUs ?? null,
      );
      const changed =
        safeMicroseconds(current.start_us) !== request.startUs ||
        safeMicroseconds(current.end_us) !== request.endUs;
      const revision = current.revision + 1;
      await transaction
        .updateTable('fragments')
        .set({
          start_us: request.startUs,
          end_us: request.endUs,
          title: request.title,
          description: request.description,
          export_selected: request.exportSelected,
          revision,
          updated_at: new Date(),
        })
        .where('id', '=', fragmentId)
        .execute();
      await replaceFragmentTags(transaction, fragmentId, request.tagIds);
      if (changed) {
        await upsertPendingPreview(
          transaction,
          this.boss,
          fragmentId,
          revision,
        );
        await this.boss.send(
          jobNames.generateFragmentPreview,
          envelope({
            videoId: current.video_id,
            fragmentId,
            expectedRevision: revision,
          }),
          {
            db: fromKysely(transaction),
            singletonKey: `${fragmentId}:${revision}`,
          },
        );
      }
    });
    return this.get(fragmentId);
  }

  async delete(fragmentId: string, expectedRevision: number) {
    const token = randomBytes(32).toString('base64url');
    const undoUntil = new Date(Date.now() + 8_000);
    let deleted: FragmentDto | undefined;
    await this.database.transaction().execute(async (transaction) => {
      deleted = await this.get(fragmentId, transaction);
      const row = await transaction
        .selectFrom('fragments')
        .select(['revision'])
        .where('id', '=', fragmentId)
        .where('deleted_at', 'is', null)
        .forUpdate()
        .executeTakeFirst();
      if (row === undefined) throw new CatalogNotFound();
      if (row.revision !== expectedRevision) throw new StaleRevision();
      await transaction
        .updateTable('fragments')
        .set({
          deleted_at: new Date(),
          purge_after: undoUntil,
          undo_token_hash: tokenHash(token),
          updated_at: new Date(),
        })
        .where('id', '=', fragmentId)
        .execute();
      await this.boss.send(jobNames.purgeFragment, envelope({ fragmentId }), {
        db: fromKysely(transaction),
        startAfter: 8,
        singletonKey: fragmentId,
      });
    });
    return {
      fragment: deleted!,
      undoToken: token,
      undoUntil: undoUntil.toISOString(),
    };
  }

  async restore(fragmentId: string, token: string): Promise<FragmentDto> {
    await this.database.transaction().execute(async (transaction) => {
      const row = await transaction
        .selectFrom('fragments')
        .select(['undo_token_hash', 'purge_after', 'revision'])
        .where('id', '=', fragmentId)
        .forUpdate()
        .executeTakeFirst();
      if (
        row?.undo_token_hash !== tokenHash(token) ||
        row.purge_after === null ||
        row.purge_after.getTime() <= Date.now()
      ) {
        throw new FragmentRestoreExpired();
      }
      await transaction
        .updateTable('fragments')
        .set({
          deleted_at: null,
          purge_after: null,
          undo_token_hash: null,
          revision: row.revision + 1,
          updated_at: new Date(),
        })
        .where('id', '=', fragmentId)
        .execute();
    });
    return this.get(fragmentId);
  }

  private async get(
    fragmentId: string,
    database: Kysely<CatalogDatabase> | Transaction<CatalogDatabase> = this
      .database,
  ): Promise<FragmentDto> {
    const repository = new FragmentRepository(database);
    const fragment = (await repository.list()).find(
      ({ id }) => id === fragmentId,
    );
    if (fragment === undefined) throw new CatalogNotFound();
    return toFragmentDto({
      fragment,
      tags: await repository.tags(fragmentId),
      preview: await repository.preview(fragmentId),
    });
  }

  private async mapMany(
    repository: FragmentRepository,
  ): Promise<FragmentDto[]> {
    const records = await repository.list();
    return Promise.all(
      records.map(async (fragment) =>
        toFragmentDto({
          fragment,
          tags: await repository.tags(fragment.id),
          preview: await repository.preview(fragment.id),
        }),
      ),
    );
  }

  private async assertTags(
    transaction: Transaction<CatalogDatabase>,
    ids: readonly string[],
  ): Promise<void> {
    const unique = [...new Set(ids)];
    if (unique.length !== ids.length) {
      throw new DomainConflict('validation_failed', 'Tag IDs must be unique.');
    }
    if (unique.length === 0) return;
    const rows = await transaction
      .selectFrom('tags')
      .select('id')
      .where('id', 'in', unique)
      .execute();
    if (rows.length !== unique.length) throw new CatalogNotFound();
  }
}

async function replaceVideoTags(
  transaction: Transaction<CatalogDatabase>,
  videoId: string,
  tagIds: readonly string[],
): Promise<void> {
  await transaction
    .deleteFrom('video_tags')
    .where('video_id', '=', videoId)
    .execute();
  if (tagIds.length > 0) {
    await transaction
      .insertInto('video_tags')
      .values(tagIds.map((tagId) => ({ video_id: videoId, tag_id: tagId })))
      .execute();
  }
}

async function replaceFragmentTags(
  transaction: Transaction<CatalogDatabase>,
  fragmentId: string,
  tagIds: readonly string[],
): Promise<void> {
  await transaction
    .deleteFrom('fragment_tags')
    .where('fragment_id', '=', fragmentId)
    .execute();
  if (tagIds.length > 0) {
    await transaction
      .insertInto('fragment_tags')
      .values(
        tagIds.map((tagId) => ({ fragment_id: fragmentId, tag_id: tagId })),
      )
      .execute();
  }
}

async function upsertPendingPreview(
  transaction: Transaction<CatalogDatabase>,
  boss: Pick<PgBoss, 'send'>,
  fragmentId: string,
  revision: number,
): Promise<void> {
  const current = await transaction
    .selectFrom('fragment_previews')
    .select('asset_id')
    .where('fragment_id', '=', fragmentId)
    .executeTakeFirst();
  await queueAssetDeletion(transaction, boss, current?.asset_id ?? null);
  await transaction
    .insertInto('fragment_previews')
    .values({
      fragment_id: fragmentId,
      fragment_revision: revision,
      asset_id: null,
      status: 'pending',
      sample_us: [],
      columns: 1,
      rows: 1,
      frame_width: 320,
      frame_height: 180,
      failure_code: null,
    })
    .onConflict((conflict) =>
      conflict.column('fragment_id').doUpdateSet({
        fragment_revision: revision,
        asset_id: null,
        status: 'pending',
        sample_us: [],
        columns: 1,
        rows: 1,
        failure_code: null,
        updated_at: new Date(),
      }),
    )
    .execute();
}

function tokenHash(token: string): string {
  return createHash('sha256').update(token).digest('hex');
}
