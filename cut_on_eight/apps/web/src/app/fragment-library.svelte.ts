import type {
  DeletedFragment,
  FragmentCatalogue,
  FragmentMutation,
  TagDefinition,
} from '../domain/catalogue-model.js';
import type { Segment } from '../domain/editor-model.js';
import type { WorkspacePort } from './workspace-session.svelte.js';

export interface FragmentApi {
  loadFragments(): Promise<FragmentCatalogue>;
  loadTags(): Promise<TagDefinition[]>;
  createTag(name: string): Promise<TagDefinition>;
  updateFragment(
    projectId: string,
    fragmentId: string,
    mutation: FragmentMutation,
    expectedRevision: number,
  ): Promise<Segment>;
  deleteFragment(
    projectId: string,
    fragment: Segment,
    index: number,
  ): Promise<DeletedFragment>;
  restoreFragment(deleted: DeletedFragment): Promise<Segment>;
}

export interface JobRetryPort {
  readonly retryingJobId: string | null;
  retryJobById(jobId: string): Promise<void>;
}

export class FragmentLibrary {
  catalogue = $state.raw<FragmentCatalogue | null>(null);
  tags = $state.raw<TagDefinition[]>([]);
  loading = $state(false);
  error = $state<string | null>(null);
  retryingJobId = $state<string | null>(null);

  private requestRevision = 0;
  private previewPollTimer: ReturnType<typeof setTimeout> | null = null;
  private disposed = false;

  constructor(
    private readonly api: FragmentApi,
    private readonly workspace: WorkspacePort,
    private readonly jobs: JobRetryPort,
  ) {}

  async refresh(): Promise<void> {
    if (this.disposed) return;
    this.clearPreviewPoll();
    const revision = ++this.requestRevision;
    this.loading = true;
    this.error = null;
    try {
      const catalogue = await this.api.loadFragments();
      if (!this.isCurrent(revision)) return;
      this.catalogue = catalogue;
      this.tags = catalogue.tags;
      this.schedulePreviewPoll(catalogue);
    } catch (error) {
      if (!this.isCurrent(revision)) return;
      this.error = describeError(error, 'Could not load fragments');
    } finally {
      if (this.isCurrent(revision)) this.loading = false;
    }
  }

  async refreshTags(): Promise<void> {
    if (this.disposed) return;
    const revision = ++this.requestRevision;
    try {
      const tags = await this.api.loadTags();
      if (this.isCurrent(revision)) this.tags = tags;
    } catch {
      // Opening the fragment catalogue performs a full tag refresh later.
    }
  }

  async createTag(name: string): Promise<TagDefinition> {
    const tag = await this.api.createTag(name);
    this.tags = addSortedTag(this.tags, tag);
    if (this.catalogue !== null) {
      this.catalogue = {
        ...this.catalogue,
        tags: addSortedTag(this.catalogue.tags, tag),
      };
    }
    return tag;
  }

  async mutateFragment(
    projectId: string,
    fragmentId: string,
    mutation: FragmentMutation,
  ): Promise<Segment> {
    await this.workspace.flushProject(projectId);
    const current = this.catalogue?.fragments.find(
      ({ segment }) => segment.id === fragmentId,
    )?.segment;
    const segment = await this.api.updateFragment(
      projectId,
      fragmentId,
      mutation,
      current?.revision ?? 0,
    );
    this.workspace.patchSegment(projectId, segment);
    this.replaceCatalogueSegment(projectId, segment);
    return segment;
  }

  async removeFragment(
    projectId: string,
    fragmentId: string,
  ): Promise<DeletedFragment> {
    await this.workspace.flushProject(projectId);
    const index =
      this.catalogue?.fragments.findIndex(
        ({ segment }) => segment.id === fragmentId,
      ) ?? -1;
    const fragment = this.catalogue?.fragments[index]?.segment;
    if (fragment === undefined) throw new Error('Fragment is unavailable.');
    const deleted = await this.api.deleteFragment(
      projectId,
      fragment,
      Math.max(0, index),
    );
    this.workspace.removeSegment(projectId, fragmentId);
    if (this.catalogue !== null) {
      this.catalogue = {
        ...this.catalogue,
        fragments: this.catalogue.fragments.filter(
          (fragment) => fragment.segment.id !== fragmentId,
        ),
      };
    }
    return deleted;
  }

  async restoreDeletedFragment(deleted: DeletedFragment): Promise<void> {
    const segment = await this.api.restoreFragment(deleted);
    this.workspace.restoreSegment(deleted.projectId, segment, deleted.index);
    await this.refresh();
    this.replaceCatalogueSegment(deleted.projectId, segment);
  }

  async retryThumbnail(jobId: string): Promise<void> {
    if (this.retryingJobId !== null || this.jobs.retryingJobId !== null) return;
    this.retryingJobId = jobId;
    try {
      await this.jobs.retryJobById(jobId);
      await this.refresh();
    } catch (error) {
      this.error = describeError(error, 'Could not retry thumbnails');
    } finally {
      this.retryingJobId = null;
    }
  }

  async removeManagedVideo(projectId: string): Promise<void> {
    await this.workspace.deleteManagedVideo(projectId);
    await this.refresh();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.requestRevision += 1;
    this.clearPreviewPoll();
  }

  private replaceCatalogueSegment(projectId: string, segment: Segment): void {
    if (this.catalogue === null) return;
    this.catalogue = {
      ...this.catalogue,
      fragments: this.catalogue.fragments.map((fragment) =>
        fragment.projectId === projectId && fragment.segment.id === segment.id
          ? { ...fragment, segment }
          : fragment,
      ),
    };
  }

  private isCurrent(revision: number): boolean {
    return !this.disposed && revision === this.requestRevision;
  }

  private schedulePreviewPoll(catalogue: FragmentCatalogue): void {
    if (
      !catalogue.fragments.some(
        ({ thumbnailState }) => thumbnailState === 'generating',
      )
    ) {
      return;
    }
    this.previewPollTimer = setTimeout(() => {
      this.previewPollTimer = null;
      void this.refresh();
    }, 1_000);
  }

  private clearPreviewPoll(): void {
    if (this.previewPollTimer === null) return;
    clearTimeout(this.previewPollTimer);
    this.previewPollTimer = null;
  }
}

function addSortedTag(
  tags: readonly TagDefinition[],
  tag: TagDefinition,
): TagDefinition[] {
  return tags.some((item) => item.id === tag.id)
    ? [...tags]
    : [...tags, tag].sort((left, right) => left.name.localeCompare(right.name));
}

function describeError(error: unknown, action: string): string {
  return error instanceof Error
    ? `${action}: ${error.message}`
    : `${action}: unknown error`;
}
