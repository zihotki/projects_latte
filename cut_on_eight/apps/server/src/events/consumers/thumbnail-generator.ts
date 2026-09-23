import { jetstream, type JsMsg } from '@nats-io/jetstream';
import type { Kysely } from 'kysely';
import { blobKey } from '../../blobs/blob-key.js';
import type { LocalMediaFiles } from '../../blobs/blob-store.js';
import type { CatalogDatabase } from '../../catalog/database-types.js';
import type { ThumbnailRequestedEvent } from '../contracts.js';
import {
  pipelineStream,
  thumbnailGeneratorConsumer,
  type JetStreamRuntime,
} from '../jetstream.js';
import { ThumbnailBundleStore } from '../../thumbnails/thumbnail-bundle-store.js';
import { VideoThumbnailGenerator } from '../../thumbnails/video-thumbnail-generator.js';
import {
  isVideoThumbnailManifest,
  videoThumbnailProfileVersion,
} from '../../thumbnails/video-thumbnail-manifest.js';

const decoder = new TextDecoder();

export async function runThumbnailGenerator(input: {
  database: Kysely<CatalogDatabase>;
  runtime: JetStreamRuntime;
  files: LocalMediaFiles;
  generator: VideoThumbnailGenerator;
  bundles: ThumbnailBundleStore;
  stopping: () => boolean;
}): Promise<void> {
  const consumer = await jetstream(input.runtime.connection).consumers.get(
    pipelineStream,
    thumbnailGeneratorConsumer,
  );
  while (!input.stopping()) {
    const message = await consumer.next({ expires: 1_000 });
    if (message === null) continue;
    try {
      await processThumbnailMessage(input, message);
    } catch (error) {
      console.error('Thumbnail event could not be processed', error);
      if (message.info.deliveryCount >= 5)
        message.term('thumbnail_unexpected_failure');
      else message.nak(30_000);
    }
  }
}

async function processThumbnailMessage(
  input: Omit<Parameters<typeof runThumbnailGenerator>[0], 'stopping'>,
  message: JsMsg,
): Promise<void> {
  const event = parseThumbnailEvent(message);
  const source = await input.database
    .selectFrom('videos')
    .innerJoin('assets', 'assets.id', 'videos.source_asset_id')
    .select(['videos.duration_us', 'assets.storage_key'])
    .where('videos.id', '=', event.payload.videoId)
    .where('videos.source_asset_id', '=', event.payload.sourceAssetId)
    .where('videos.status', '=', 'ready')
    .where('assets.state', '=', 'ready')
    .executeTakeFirst();
  if (source === undefined || source.duration_us === null) {
    await message.ackAck();
    return;
  }
  const durationSeconds = Number(source.duration_us) / 1_000_000;
  if (!Number.isFinite(durationSeconds) || durationSeconds <= 0) {
    await message.ackAck();
    return;
  }

  const previous = await input.database
    .selectFrom('video_thumbnail_state')
    .select([
      'source_asset_id',
      'profile_version',
      'storage_key',
      'status',
      'manifest',
    ])
    .where('video_id', '=', event.payload.videoId)
    .executeTakeFirst();
  if (
    previous?.status === 'ready' &&
    previous.source_asset_id === event.payload.sourceAssetId &&
    previous.profile_version === event.payload.thumbnailProfileVersion
  ) {
    await message.ackAck();
    return;
  }

  await input.database
    .insertInto('video_thumbnail_state')
    .values({
      video_id: event.payload.videoId,
      source_asset_id: event.payload.sourceAssetId,
      profile_version: event.payload.thumbnailProfileVersion,
      storage_key: previous?.storage_key ?? null,
      status: 'generating',
      manifest: previous?.manifest ?? null,
      failure_code: null,
      updated_at: new Date(),
    })
    .onConflict((conflict) =>
      conflict.column('video_id').doUpdateSet({
        source_asset_id: event.payload.sourceAssetId,
        profile_version: event.payload.thumbnailProfileVersion,
        status: 'generating',
        failure_code: null,
        updated_at: new Date(),
      }),
    )
    .execute();

  const heartbeat = setInterval(() => message.working(), 30_000);
  heartbeat.unref();
  let generatedStorageKey: string | undefined;
  let stored = false;
  try {
    const generated = await input.files.withLocalPath(
      blobKey(source.storage_key),
      (sourcePath) => input.generator.generate({ durationSeconds, sourcePath }),
    );
    generatedStorageKey = generated.storageKey;
    await input.database
      .updateTable('video_thumbnail_state')
      .set({
        source_asset_id: event.payload.sourceAssetId,
        profile_version: event.payload.thumbnailProfileVersion,
        storage_key: generated.storageKey,
        status: 'ready',
        manifest: generated.manifest as unknown as Record<string, unknown>,
        failure_code: null,
        updated_at: new Date(),
      })
      .where('video_id', '=', event.payload.videoId)
      .execute();
    stored = true;
    if (
      previous?.storage_key !== null &&
      previous?.storage_key !== undefined &&
      previous.storage_key !== generated.storageKey
    ) {
      input.bundles.deleteLater(previous.storage_key);
    }
    await message.ackAck();
  } catch (error) {
    if (stored) {
      message.nak(5_000);
      return;
    }
    const failureCode = thumbnailFailureCode(error);
    await input.database
      .updateTable('video_thumbnail_state')
      .set({
        status: 'failed',
        failure_code: failureCode,
        updated_at: new Date(),
      })
      .where('video_id', '=', event.payload.videoId)
      .execute();
    if (generatedStorageKey !== undefined) {
      input.bundles.deleteLater(generatedStorageKey, 0);
    }
    if (message.info.deliveryCount >= 5) message.term(failureCode);
    else message.nak(30_000);
  } finally {
    clearInterval(heartbeat);
  }
}

function parseThumbnailEvent(message: JsMsg): ThumbnailRequestedEvent {
  const event = JSON.parse(decoder.decode(message.data)) as unknown;
  if (
    typeof event !== 'object' ||
    event === null ||
    Array.isArray(event) ||
    (event as { type?: unknown }).type !== 'video.thumbnails.requested.v1'
  ) {
    throw new Error('Invalid thumbnail request event');
  }
  const candidate = event as ThumbnailRequestedEvent;
  if (
    candidate.schemaVersion !== 1 ||
    candidate.aggregate.type !== 'video' ||
    candidate.payload.videoId !== candidate.aggregate.id ||
    typeof candidate.payload.sourceAssetId !== 'string' ||
    candidate.payload.thumbnailProfileVersion !== videoThumbnailProfileVersion
  ) {
    throw new Error('Invalid thumbnail request event');
  }
  return candidate;
}

function thumbnailFailureCode(error: unknown): string {
  if (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string' &&
    /^[a-z][a-z0-9_]*$/.test(error.code)
  ) {
    return error.code;
  }
  return 'thumbnail_generation_failed';
}

export { isVideoThumbnailManifest };
