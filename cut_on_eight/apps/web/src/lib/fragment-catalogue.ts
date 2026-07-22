import type { FragmentSummary } from '@cut-on-eight/contracts';

export interface FragmentFilters {
  readonly query: string;
  readonly projectId: string | null;
  readonly tagIds: ReadonlySet<string>;
}

export function fragmentLabel(fragment: FragmentSummary): string {
  return (
    fragment.segment.title ??
    `Fragment ${fragment.ordinal} · ${fragment.sourceFileName}`
  );
}

export function filterFragments(
  fragments: readonly FragmentSummary[],
  filters: FragmentFilters,
): FragmentSummary[] {
  const query = filters.query.trim().toLowerCase();
  return fragments.filter((fragment) => {
    if (filters.projectId !== null && fragment.projectId !== filters.projectId)
      return false;
    if (
      query !== '' &&
      !`${fragment.segment.title ?? ''}\n${fragment.sourceFileName}`
        .toLowerCase()
        .includes(query)
    )
      return false;
    return [...filters.tagIds].every((tagId) =>
      fragment.segment.tagIds.includes(tagId),
    );
  });
}
