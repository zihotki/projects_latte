import { createHash } from 'node:crypto';
import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';
import { safeMicroseconds } from '../catalog/database-types.js';

export interface SearchDocument {
  readonly text: string;
  readonly hash: string;
}

export interface SearchDocumentInput {
  readonly fragmentTitle: string | null;
  readonly fragmentDescription: string | null;
  readonly fragmentTags: readonly string[];
  readonly sourceTitle: string | null;
  readonly sourceDescription: string | null;
  readonly sourceTags: readonly string[];
}

export interface SearchTag {
  readonly id: string;
  readonly name: string;
}

export interface CurrentFragmentSearchDocument {
  readonly fragmentId: string;
  readonly fragmentRevision: number;
  readonly videoId: string;
  readonly startUs: number;
  readonly endUs: number;
  readonly title: string | null;
  readonly description: string | null;
  readonly fragmentTags: readonly SearchTag[];
  readonly sourceTitle: string;
  readonly sourceDescription: string | null;
  readonly sourceTags: readonly SearchTag[];
  readonly fragmentTagIds: readonly string[];
  readonly sourceTagIds: readonly string[];
  readonly collectionIds: readonly string[];
  readonly document: SearchDocument;
}

export function buildSearchDocument(
  input: SearchDocumentInput,
): SearchDocument {
  const text = [
    textField(input.fragmentTitle),
    textField(input.fragmentDescription),
    ...tagFields(input.fragmentTags),
    textField(input.sourceTitle),
    textField(input.sourceDescription),
    ...tagFields(input.sourceTags),
  ]
    .filter((field): field is string => field !== null)
    .join('\n');

  return {
    text,
    hash: createHash('sha256').update(text, 'utf8').digest('hex'),
  };
}

export async function loadSearchDocument(
  database: Kysely<CatalogDatabase>,
  fragmentId: string,
): Promise<CurrentFragmentSearchDocument | null> {
  const fragment = await database
    .selectFrom('fragments')
    .innerJoin('videos', 'videos.id', 'fragments.video_id')
    .select([
      'fragments.id',
      'fragments.revision',
      'fragments.video_id',
      'fragments.start_us',
      'fragments.end_us',
      'fragments.title',
      'fragments.description',
      'videos.title as source_title',
      'videos.description as source_description',
    ])
    .where('fragments.id', '=', fragmentId)
    .where('fragments.deleted_at', 'is', null)
    .where('videos.status', '!=', 'deleting')
    .executeTakeFirst();
  if (fragment === undefined) return null;

  const [fragmentTags, sourceTags] = await Promise.all([
    tagsForFragment(database, fragment.id),
    tagsForVideo(database, fragment.video_id),
  ]);

  return {
    fragmentId: fragment.id,
    fragmentRevision: fragment.revision,
    videoId: fragment.video_id,
    startUs: safeMicroseconds(fragment.start_us),
    endUs: safeMicroseconds(fragment.end_us),
    title: fragment.title,
    description: fragment.description,
    fragmentTags,
    sourceTitle: fragment.source_title,
    sourceDescription: fragment.source_description,
    sourceTags,
    fragmentTagIds: fragmentTags.map(({ id }) => id),
    sourceTagIds: sourceTags.map(({ id }) => id),
    // Collections do not have catalog tables yet. Keep the public search
    // shape stable until the collection slice adds membership rows.
    collectionIds: [],
    document: buildSearchDocument({
      fragmentTitle: fragment.title,
      fragmentDescription: fragment.description,
      fragmentTags: fragmentTags.map(({ name }) => name),
      sourceTitle: fragment.source_title,
      sourceDescription: fragment.source_description,
      sourceTags: sourceTags.map(({ name }) => name),
    }),
  };
}

function textField(value: string | null): string | null {
  if (value === null) return null;
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

function tagFields(tags: readonly string[]): string[] {
  return [
    ...new Set(tags.map((tag) => tag.trim().toLowerCase()).filter(Boolean)),
  ].sort(compareCodeUnits);
}

function compareCodeUnits(left: string, right: string): number {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

async function tagsForFragment(
  database: Kysely<CatalogDatabase>,
  fragmentId: string,
): Promise<SearchTag[]> {
  return database
    .selectFrom('fragment_tags')
    .innerJoin('tags', 'tags.id', 'fragment_tags.tag_id')
    .select(['tags.id', 'tags.name'])
    .where('fragment_tags.fragment_id', '=', fragmentId)
    .orderBy('tags.name')
    .orderBy('tags.id')
    .execute();
}

async function tagsForVideo(
  database: Kysely<CatalogDatabase>,
  videoId: string,
): Promise<SearchTag[]> {
  return database
    .selectFrom('video_tags')
    .innerJoin('tags', 'tags.id', 'video_tags.tag_id')
    .select(['tags.id', 'tags.name'])
    .where('video_tags.video_id', '=', videoId)
    .orderBy('tags.name')
    .orderBy('tags.id')
    .execute();
}
