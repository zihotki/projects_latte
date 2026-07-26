export const jobNames = {
  inspectVideo: 'video.inspect.v1',
  generateFragmentPreview: 'fragment.preview.v1',
  projectFragment: 'fragment.project.v1',
  purgeFragment: 'fragment.purge.v1',
  deleteVideo: 'video.delete.v1',
  deleteAsset: 'asset.delete.v1',
} as const;

export type Phase4JobName = (typeof jobNames)[keyof typeof jobNames];

export interface JobTraceContext {
  readonly traceparent?: string;
  readonly tracestate?: string;
}

export interface RevisionedEntityJob {
  readonly entityId: string;
  readonly expectedRevision: number;
  readonly trace?: JobTraceContext;
}
