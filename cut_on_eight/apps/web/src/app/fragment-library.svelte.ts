import type {
  DeletedFragment,
  FragmentCatalogue,
  FragmentMutation,
  Segment,
  TagDefinition,
} from '@cut-on-eight/contracts';
import type { WorkspacePort } from './workspace-session.svelte.js';

export interface FragmentApi {
  loadFragments(): Promise<FragmentCatalogue>;
  loadTags(): Promise<TagDefinition[]>;
  createTag(name: string): Promise<TagDefinition>;
  updateFragment(
    projectId: string,
    fragmentId: string,
    mutation: FragmentMutation,
  ): Promise<Segment>;
  deleteFragment(
    projectId: string,
    fragmentId: string,
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

  constructor(
    private readonly api: FragmentApi,
    private readonly workspace: WorkspacePort,
    private readonly jobs: JobRetryPort,
  ) {}

  get retryingJobId(): string | null {
    return this.jobs.retryingJobId;
  }

  async refresh(): Promise<void> {
    this.loading = true;
    this.error = null;
    try {
      this.catalogue = await this.api.loadFragments();
      this.tags = this.catalogue.tags;
    } catch (error) {
      this.error = describeError(error, 'Could not load fragments');
    } finally {
      this.loading = false;
    }
  }

  async refreshTags(): Promise<void> {
    try {
      this.tags = await this.api.loadTags();
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
    const segment = await this.api.updateFragment(
      projectId,
      fragmentId,
      mutation,
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
    const deleted = await this.api.deleteFragment(projectId, fragmentId);
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
    if (this.jobs.retryingJobId !== null) return;
    try {
      await this.jobs.retryJobById(jobId);
      await this.refresh();
    } catch (error) {
      this.error = describeError(error, 'Could not retry thumbnails');
    }
  }

  async removeManagedVideo(projectId: string): Promise<void> {
    await this.workspace.deleteManagedVideo(projectId);
    await this.refresh();
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
